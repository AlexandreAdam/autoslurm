"""Bounded stdout/stderr reads using producing paths and canonical task identity."""

import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess

from .execution import EXECUTION_METADATA_KEY
from .storage import storage_root
from .utils import ssh_host_from_config


def _expand(pattern, name, parent, index, job_id):
    values = {"x": name, "A": parent, "a": str(index) if index is not None else None, "j": job_id, "%": "%"}
    def replace(match):
        value = values.get(match[1])
        if value is None:
            raise ValueError(f"Cannot resolve log placeholder %{match[1]} for this task.")
        return str(value)
    return re.sub(r"%(.)|%$", replace, pattern)


def _references(job, task):
    execution = job.get(EXECUTION_METADATA_KEY, {})
    root = execution.get("storage_root", str(storage_root()))
    working = execution.get("working_directory")
    slurm = job.get("slurm") or {}
    patterns = {"stdout": execution.get("log_pattern") or slurm.get("output") or str(Path(root) / "out/%x-%j.out")}
    if slurm.get("error"):
        patterns["stderr"] = slurm["error"]
    refs = []
    for stream, pattern in patterns.items():
        if not Path(pattern).is_absolute():
            if not working:
                raise ValueError("Relative custom log path has no recorded producing working directory.")
            pattern = str(Path(working) / pattern)
        ids = [task.get("raw_id"), task["job_id"]]
        if task["task_index"] is not None:
            ids.append(task["parent_id"] + "." + str(task["task_index"]))
        paths = list(dict.fromkeys(_expand(pattern, job["name"], task["parent_id"], task["task_index"], value) for value in ids if value))
        refs.append({"job_name": job["name"], "task_index": task["task_index"], "job_id": task["job_id"], "stream": stream, "paths": paths})
    return refs


def _finish(reference, data, size, tail, max_bytes):
    text = data.decode("utf-8", errors="replace")
    lines = text.splitlines()
    return {**reference, "state": "available", "text": "\n".join(lines[-tail:]) if tail else "",
            "size_bytes": size, "truncated": size > len(data) or len(lines) > tail,
            "max_bytes": max_bytes, "observed_at": datetime.now(timezone.utc).isoformat()}


def read_job_logs(jobs, resolved_jobs, *, job_name=None, task_index=None, tail=40, max_bytes=65536, max_logs=20, refresh=True):
    if not isinstance(tail, int) or tail < 0 or not 1 <= max_bytes <= 1048576 or not 1 <= max_logs <= 100:
        raise ValueError("Log bounds require nonnegative tail, 1..1048576 bytes and 1..100 files.")
    from .inspection import producing_machine, _profiles
    profiles, _ = _profiles(jobs)
    by_name = {job["name"]: job for job in jobs}
    references = []
    for resolved in resolved_jobs:
        if job_name is not None and resolved["name"] != job_name:
            continue
        job = by_name[resolved["name"]]
        for task in resolved["tasks"]:
            if task_index is not None and task["task_index"] != int(task_index):
                continue
            if task["parent_id"] is None:
                continue
            try:
                key, config = producing_machine(job, profiles)
                if config and EXECUTION_METADATA_KEY not in job:
                    raise ValueError("Remote log locations lack recorded producing metadata; no path guessing.")
                for ref in _references(job, task):
                    references.append({**ref, "key": key, "config": config})
            except ValueError as exc:
                references.append({"job_name": job["name"], "task_index": task["task_index"], "state": "error", "error": str(exc)})
    output = []
    remote_groups = {}
    for ref in references[:max_logs]:
        if ref.get("state") == "error":
            output.append(ref)
            continue
        config = ref.pop("config")
        key = ref.pop("key")
        remote = bool(config.get("hostname") or config.get("hosturl") or config.get("username"))
        if remote:
            remote_groups.setdefault(key, (config, []))[1].append(ref)
        else:
            for candidate in ref["paths"]:
                path = Path(candidate)
                try:
                    with path.open("rb") as stream:
                        size = stream.seek(0, 2)
                        stream.seek(max(0, size - max_bytes))
                        data = stream.read(max_bytes)
                    output.append(_finish({**ref, "path": candidate}, data, size, tail, max_bytes))
                    break
                except FileNotFoundError:
                    continue
                except OSError as exc:
                    output.append({**ref, "path": candidate, "state": "error", "error": str(exc)})
                    break
            else:
                output.append({**ref, "state": "missing", "path": ref["paths"][0]})
    for key, (config, refs) in remote_groups.items():
        requests = [(ref, candidate) for ref in refs for candidate in ref["paths"]]
        snapshots = {}
        if refresh:
            chunks = ["set -o pipefail"]
            for index, (_, candidate) in enumerate(requests):
                path = shlex.quote(candidate)
                chunks.append(f"if test -f {path}; then size=$(wc -c < {path}) && data=$(tail -c {max_bytes} -- {path} | base64 | tr -d '\\n') && printf '{index}|ok|%s|%s\\n' \"$size\" \"$data\" || printf '{index}|error||\\n'; else printf '{index}|missing||\\n'; fi")
            try:
                host = ssh_host_from_config(config)
                result = subprocess.run(["ssh", *shlex.split(host), "bash -lc " + shlex.quote("\n".join(chunks))], capture_output=True, text=True, timeout=30)
                if result.returncode != 0:
                    raise RuntimeError(result.stderr.strip() or "Remote log query failed.")
                for line in result.stdout.splitlines():
                    fields = line.split("|", 3)
                    if len(fields) == 4 and fields[0].isdigit():
                        snapshots[int(fields[0])] = fields[1:]
            except Exception as exc:
                for ref in refs:
                    output.append({**ref, "state": "error", "error": str(exc), "path": ref["paths"][0]})
                continue
        offset = 0
        for ref in refs:
            candidates = []
            for candidate in ref["paths"]:
                cache_key = hashlib.sha256((key + candidate).encode()).hexdigest()
                cache = storage_root() / "observations/logs" / (cache_key + ".json")
                fields = snapshots.get(offset)
                offset += 1
                if not refresh:
                    if cache.exists():
                        try:
                            entry = json.loads(cache.read_text())
                            previous = entry["text"].encode()
                            bounded = previous[-max_bytes:]
                            entry["text"] = "\n".join(bounded.decode("utf-8", errors="replace").splitlines()[-tail:]) if tail else ""
                            entry["truncated"] = entry["truncated"] or len(entry["text"].encode()) < len(previous)
                            entry["max_bytes"] = max_bytes
                            entry["freshness"] = "stale"
                            candidates.append(entry)
                        except (OSError, ValueError, KeyError, TypeError) as exc:
                            candidates.append({**ref, "path": candidate, "state": "error", "error": f"Invalid cached log: {exc}"})
                    continue
                if fields is None:
                    candidates.append({**ref, "path": candidate, "state": "error", "error": "Incomplete remote log response."})
                elif fields[0] == "ok":
                    try:
                        data = base64.b64decode(fields[2], validate=True)
                        if len(data) > max_bytes:
                            raise ValueError("Remote log exceeded the requested bound.")
                        entry = _finish({**ref, "path": candidate}, data, int(fields[1]), tail, max_bytes)
                        from .submission import atomic_json
                        atomic_json(cache, entry)
                        candidates.append(entry)
                    except (ValueError, OSError) as exc:
                        candidates.append({**ref, "path": candidate, "state": "error", "error": str(exc)})
                elif fields[0] == "error":
                    candidates.append({**ref, "path": candidate, "state": "error", "error": "Remote log read failed."})
            output.append(next((entry for entry in candidates if entry["state"] == "available"), candidates[0] if candidates else {**ref, "path": ref["paths"][0], "state": "missing" if refresh else "not_cached"}))
    if len(references) > max_logs:
        output.append({"state": "omitted", "count": len(references) - max_logs, "reason": "Requested log-file bound reached."})
    return output
