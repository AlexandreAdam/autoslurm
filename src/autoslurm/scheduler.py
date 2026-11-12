"""One bounded scheduler observation per machine; command failures stay evidence."""

from datetime import datetime, timezone
import re
import shlex
import subprocess

from .array_status import canonical_job_id, parent_job_id
from .utils import ssh_host_from_config

QUERY_START_DATE = "2000-01-01"


def _parse(text, source):
    records = {}
    for line in text.splitlines():
        fields = [part.strip() for part in line.split("|")]
        if len(fields) < 2:
            continue
        identity = canonical_job_id(fields[0])
        if identity is None:
            continue
        state = fields[1].split()[0].rstrip("+") if fields[1] else "UNKNOWN"
        get = lambda index: fields[index] if len(fields) > index and fields[index] not in {"", "None", "(null)", "Unknown"} else None
        records[identity] = {"state": state, "source": source,
                             "time_remaining": get(2) if source == "queue" else None,
                             "exit_code": get(2) if source == "accounting" else None,
                             "reason": get(3), "raw_id": get(4) if source == "accounting" else None}
    return records


def query_scheduler(job_ids, config=None, machine_name=None):
    observed_at = datetime.now(timezone.utc).isoformat()
    ids = sorted(set(str(value) for value in job_ids))
    if any(parent_job_id(value) is None for value in ids):
        raise ValueError("Scheduler queries require numeric parent job IDs.")
    observation = {"observed_at": observed_at, "records": {}, "errors": [], "queries": []}
    if not ids:
        return observation
    commands = [
        ["squeue", "--array", "-h", "-j", ",".join(ids), "-o", "%i|%T|%L|%R"],
        ["sacct", "-n", "-P", "-S", QUERY_START_DATE, "-j", ",".join(ids), "-o", "JobID,State,ExitCode,Reason,JobIDRaw"],
    ]
    config = config or {}
    remote = bool(config.get("hostname") or config.get("hosturl") or config.get("username"))
    results = []
    if remote:
        try:
            host = ssh_host_from_config(config, machine_name)
            chunks = []
            for index, command in enumerate(commands):
                chunks.append(f"printf '__AUTOSLURM_QUERY_{index}__\\n'; {shlex.join(command)} 2>&1; printf '\\n__AUTOSLURM_EXIT__%s\\n' \"$?\"")
            result = subprocess.run(["ssh", *shlex.split(host), "bash -lc " + shlex.quote("\n".join(chunks))], capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip() or "Scheduler transport failed.")
            for index in range(2):
                match = re.search(rf"__AUTOSLURM_QUERY_{index}__\n(.*?)\n__AUTOSLURM_EXIT__(\d+)\n", result.stdout, re.S)
                if match is None:
                    raise ValueError("Incomplete scheduler query response.")
                results.append((int(match[2]), match[1], ""))
        except Exception as exc:
            observation["errors"].append({"source": "transport", "message": str(exc)})
            return observation
    else:
        for command in commands:
            try:
                result = subprocess.run(command, capture_output=True, text=True, timeout=30)
                results.append((result.returncode, result.stdout, result.stderr))
            except (OSError, subprocess.TimeoutExpired) as exc:
                results.append((None, "", str(exc)))
    by_source = {}
    for source, (code, stdout, stderr) in zip(("queue", "accounting"), results):
        observation["queries"].append({"source": source, "returncode": code})
        if code != 0:
            observation["errors"].append({"source": source, "message": stderr.strip() or stdout.strip() or "Query failed."})
            by_source[source] = {}
        else:
            by_source[source] = _parse(stdout, source)
    # Queue is current live evidence; accounting supplies raw IDs/exit details.
    observation["records"].update(by_source.get("accounting", {}))
    for identity, queue in by_source.get("queue", {}).items():
        accounting = observation["records"].get(identity, {})
        observation["records"][identity] = {**accounting, **queue, "raw_id": accounting.get("raw_id"), "exit_code": accounting.get("exit_code")}
    return observation
