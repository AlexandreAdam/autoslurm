"""Bounded log retrieval: select references, read transport, decode, cache."""

import base64
from datetime import datetime, timezone
from pathlib import Path
import re
import shlex
import subprocess

from .execution import EXECUTION_METADATA_KEY, producing_machine, is_remote_machine
from .inspection_cache import InspectionCache
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


def _references(job, task, root):
    execution = job.get(EXECUTION_METADATA_KEY, {})
    root = execution.get("storage_root", str(root))
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


def validate_log_bounds(tail, max_bytes, max_logs):
    if (type(tail) is not int or tail < 0 or type(max_bytes) is not int
            or not 1 <= max_bytes <= 1048576 or type(max_logs) is not int
            or not 1 <= max_logs <= 100):
        raise ValueError("Log bounds require nonnegative tail, 1..1048576 bytes and 1..100 files.")


def select_log_references(jobs, resolved_jobs, *, profiles, root, job_name=None, task_index=None):
    """Pure producing-path selection; no profile discovery, file reads or queries."""
    by_name = {job["name"]: job for job in jobs}
    references = []
    for resolved in resolved_jobs:
        if job_name is not None and resolved["name"] != job_name:
            continue
        job = by_name[resolved["name"]]
        for task in resolved["tasks"]:
            if task_index is not None and task["task_index"] != task_index:
                continue
            if task["parent_id"] is None:
                continue
            try:
                key, config = producing_machine(job, profiles)
                if is_remote_machine(config) and EXECUTION_METADATA_KEY not in job:
                    raise ValueError("Remote log locations lack recorded producing metadata; no path guessing.")
                references.extend({**ref, "key": key, "config": config} for ref in _references(job, task, root))
            except (ValueError, TypeError, KeyError) as error:
                references.append({"job_name": job["name"], "task_index": task["task_index"],
                                   "state": "error", "error": str(error)})
    return references


def _public_reference(reference):
    return {key: value for key, value in reference.items() if key not in {"key", "config"}}


def _finish(reference, data, size, tail, max_bytes, observed_at):
    lines = data.decode("utf-8", errors="replace").splitlines()
    return {**reference, "state": "available", "text": "\n".join(lines[-tail:]) if tail else "",
            "size_bytes": size, "truncated": size > len(data) or len(lines) > tail,
            "max_bytes": max_bytes, "observed_at": observed_at}


def _read_local_reference(reference, tail, max_bytes):
    public = _public_reference(reference)
    for candidate in reference["paths"]:
        try:
            with Path(candidate).open("rb") as stream:
                size = stream.seek(0, 2)
                stream.seek(max(0, size - max_bytes))
                data = stream.read(max_bytes)
            return _finish({**public, "path": candidate}, data, size, tail, max_bytes,
                           datetime.now(timezone.utc).isoformat())
        except FileNotFoundError:
            continue
        except OSError as error:
            return {**public, "path": candidate, "state": "error", "error": str(error)}
    return {**public, "state": "missing", "path": reference["paths"][0]}


def _query_remote_tails(config, paths, max_bytes):
    chunks = ["set -o pipefail"]
    for index, candidate in enumerate(paths):
        path = shlex.quote(candidate)
        chunks.append(f"if test -f {path}; then size=$(wc -c < {path}) && data=$(tail -c {max_bytes} -- {path} | base64 | tr -d '\\n') && printf '{index}|ok|%s|%s\\n' \"$size\" \"$data\" || printf '{index}|error||\\n'; else printf '{index}|missing||\\n'; fi")
    try:
        host = ssh_host_from_config(config)
        result = subprocess.run(["ssh", *shlex.split(host), "bash -lc " + shlex.quote("\n".join(chunks))],
                                capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "Remote log query failed.")
        snapshots = {}
        for line in result.stdout.splitlines():
            fields = line.split("|", 3)
            if len(fields) == 4 and fields[0].isdigit():
                snapshots[int(fields[0])] = fields[1:]
        return snapshots, None
    except Exception as error:
        return {}, str(error)


def _decode_remote_entry(reference, candidate, fields, *, tail, max_bytes, observed_at, cache):
    public = {**_public_reference(reference), "path": candidate}
    if fields is None:
        return {**public, "state": "error", "error": "Incomplete remote log response."}
    if fields[0] == "missing":
        return {**public, "state": "missing"}
    if fields[0] != "ok":
        return {**public, "state": "error", "error": "Remote log read failed."}
    try:
        data = base64.b64decode(fields[2], validate=True)
        size = int(fields[1])
        if len(data) > max_bytes or size < 0:
            raise ValueError("Remote log exceeded the requested bound or reported an invalid size.")
        entry = _finish(public, data, size, tail, max_bytes, observed_at)
    except (ValueError, TypeError) as error:
        return {**public, "state": "error", "error": str(error)}
    error = cache.save_excerpt(reference["key"], candidate, entry)
    if error:
        entry["cache_error"] = error
    return entry


def _choose_reference(reference, candidates, missing_state):
    for state in ("available", "error"):
        match = next((entry for entry in candidates if entry["state"] == state), None)
        if match is not None:
            return match
    return {**_public_reference(reference), "path": reference["paths"][0], "state": missing_state}


def _read_cached_reference(reference, tail, max_bytes, cache):
    candidates = []
    for candidate in reference["paths"]:
        entry, error = cache.load_excerpt(reference["key"], candidate)
        if error:
            candidates.append({**_public_reference(reference), "path": candidate,
                               "state": "error", "error": error["message"]})
        elif entry is not None:
            if any(entry.get(key) != reference.get(key) for key in ("job_name", "job_id", "task_index")):
                continue
            previous = entry["text"].encode()
            bounded = previous[-max_bytes:]
            entry["text"] = "\n".join(bounded.decode("utf-8", errors="replace").splitlines()[-tail:]) if tail else ""
            entry["truncated"] = entry["truncated"] or len(entry["text"].encode()) < len(previous)
            entry.update(max_bytes=max_bytes, freshness="stale")
            candidates.append(entry)
    return _choose_reference(reference, candidates, "not_cached")


def _read_remote_references(references, *, tail, max_bytes, refresh, cache):
    if not refresh:
        return [_read_cached_reference(ref, tail, max_bytes, cache) for ref in references]
    paths = [candidate for ref in references for candidate in ref["paths"]]
    snapshots, error = _query_remote_tails(references[0]["config"], paths, max_bytes)
    if error:
        return [{**_public_reference(ref), "path": ref["paths"][0], "state": "error", "error": error} for ref in references]
    observed_at = datetime.now(timezone.utc).isoformat()
    output, offset = [], 0
    for reference in references:
        candidates = []
        for candidate in reference["paths"]:
            candidates.append(_decode_remote_entry(reference, candidate, snapshots.get(offset),
                tail=tail, max_bytes=max_bytes, observed_at=observed_at, cache=cache))
            offset += 1
        output.append(_choose_reference(reference, candidates, "missing"))
    return output


def read_job_logs(jobs, resolved_jobs, *, job_name=None, task_index=None, tail=40,
                  max_bytes=65536, max_logs=20, refresh=True, profiles=None, root=None, cache=None):
    validate_log_bounds(tail, max_bytes, max_logs)
    root = storage_root() if root is None else root
    cache = InspectionCache(root) if cache is None else cache
    references = select_log_references(jobs, resolved_jobs, profiles=profiles or {}, root=root,
                                      job_name=job_name, task_index=task_index)
    output, remote_groups = {}, {}
    for index, ref in enumerate(references[:max_logs]):
        if ref.get("state") == "error":
            output[index] = ref
        elif is_remote_machine(ref["config"]):
            remote_groups.setdefault(ref["key"], []).append((index, ref))
        else:
            output[index] = _read_local_reference(ref, tail, max_bytes)
    for group in remote_groups.values():
        entries = _read_remote_references([ref for _, ref in group], tail=tail, max_bytes=max_bytes,
                                         refresh=refresh, cache=cache)
        output.update((index, entry) for (index, _), entry in zip(group, entries))
    ordered = [output[index] for index in sorted(output)]
    if len(references) > max_logs:
        ordered.append({"state": "omitted", "count": len(references) - max_logs,
                        "reason": "Requested log-file bound reached."})
    return ordered
