"""Bounded log retrieval: select references, read transport, decode, cache."""

import base64
from datetime import datetime, timezone
from pathlib import Path
import re
import subprocess

from .execution import EXECUTION_METADATA_KEY, producing_machine, is_remote_machine
from .inspection_cache import InspectionCache
from .storage import storage_root
from .transport import ssh_command
from .log_probe import read_log


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
        streams = [stream]
        if stream == "stdout" and (not slurm.get("error") or patterns.get("stderr") == pattern):
            streams = ["stdout", "stderr"]
        if stream == "stderr" and refs and paths == refs[0]['paths']:
            refs[0]['streams'] = ['stdout', 'stderr']
            continue
        refs.append({"job_name": job["name"], "machine": job.get("machine"), "task_index": task["task_index"], "job_id": task["job_id"],
                     "stream": stream, "streams": streams, "paths": paths})
    return refs


def validate_log_bounds(tail, max_bytes, max_logs):
    if (type(tail) is not int or tail < 0 or type(max_bytes) is not int
            or not 1 <= max_bytes <= 1048576 or type(max_logs) is not int
            or not 1 <= max_logs <= 100):
        raise ValueError("Log bounds require nonnegative tail, 1..1048576 bytes and 1..100 files.")


def select_log_references(jobs, resolved_jobs, *, profiles, root, job_name=None, task_index=None, stream="both"):
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
                references.extend({**ref, "key": key, "config": config} for ref in _references(job, task, root)
                                  if stream == "both" or stream in ref["streams"])
            except (ValueError, TypeError, KeyError) as error:
                references.append({"job_name": job["name"], "task_index": task["task_index"],
                                   "state": "error", "error": str(error)})
    return references


def _public_reference(reference):
    return {key: value for key, value in reference.items() if key not in {"key", "config"}}


def _finish(reference, data, size, tail, max_bytes, observed_at, *, changed=False):
    lines = data.decode("utf-8", errors="replace").splitlines()
    text = "\n".join(lines[-tail:]) if tail else ""
    return {**reference, "state": "available", "text": text, "bytes_returned": len(text.encode()),
            "size_bytes": size, "truncated": size > len(data) or len(lines) > tail,
            "max_bytes": max_bytes, "observed_at": observed_at, "freshness": "fresh",
            "bytes_read": len(data), "empty": size == 0, "changed_during_read": changed}


def _read_local_reference(reference, tail, max_bytes, cache):
    for candidate in reference["paths"]:
        result = read_log(candidate, max_bytes)
        if result['state'] == 'missing':
            continue
        fields = [result['state'], str(result.get('size', result.get('kind', ''))),
                  base64.b64encode(result.get('data', b'')).decode()]
        return _decode_remote_entry(reference, candidate, fields, tail=tail, max_bytes=max_bytes,
                                    observed_at=datetime.now(timezone.utc).isoformat(), cache=cache)
    return {**_public_reference(reference), "state": "missing", "path": reference["paths"][0],
            "freshness": "fresh", "observed_at": datetime.now(timezone.utc).isoformat()}


def _query_remote_tails(config, paths, max_bytes):
    script = Path(__file__).with_name('log_probe.py').read_text()
    script += '\nquery_log_paths(' + repr(paths) + ', ' + repr(max_bytes) + ')\n'
    try:
        result = subprocess.run(ssh_command(config, remote_command="python3 -B -"), input=script,
                                capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            raise RuntimeError("Remote log query failed; verify SSH access and python3 availability.")
        if len(result.stdout) > len(paths) * (4 * ((max_bytes + 2) // 3) + 128):
            raise ValueError('Remote log response exceeded the requested bounds.')
        snapshots = {}
        for line in result.stdout.splitlines():
            fields = line.split("|", 3)
            if (len(fields) != 4 or not fields[0].isdigit() or not 0 <= int(fields[0]) < len(paths)
                    or int(fields[0]) in snapshots or fields[1] not in {'ok', 'ok_changed', 'missing', 'error'}):
                raise ValueError('Malformed remote log response.')
            snapshots[int(fields[0])] = fields[1:]
        return snapshots, None
    except Exception as error:
        return {}, str(error)


def _decode_remote_entry(reference, candidate, fields, *, tail, max_bytes, observed_at, cache):
    public = {**_public_reference(reference), "path": candidate, "observed_at": observed_at, "freshness": "fresh"}
    if fields is None:
        return {**public, "state": "error", "error": "Incomplete remote log response."}
    if fields[0] == "missing":
        return {**public, "state": "missing"}
    if fields[0] not in {"ok", "ok_changed"}:
        messages = {'unreadable': 'Log cannot be read (permission denied); availability is unknown.',
                    'not_regular': 'Log path is not a regular file.', 'read_failed': 'Log read failed.'}
        return {**public, "state": "error", "error_kind": fields[1] or 'read_failed',
                "error": messages.get(fields[1], 'Log read failed.')}
    try:
        if len(fields[2]) > 4 * ((max_bytes + 2) // 3):
            raise ValueError('Remote log exceeded the requested byte bound.')
        data = base64.b64decode(fields[2], validate=True)
        size = int(fields[1])
        if len(data) > max_bytes or size < len(data):
            raise ValueError("Remote log exceeded the requested bound or reported an invalid size.")
        entry = _finish(public, data, size, tail, max_bytes, observed_at, changed=fields[0] == 'ok_changed')
    except (ValueError, TypeError) as error:
        return {**public, "state": "error", "error": str(error)}
    error = cache.save_excerpt(reference["key"], candidate, entry)
    if error:
        entry["cache_error"] = error
    return entry


def _choose_reference(reference, candidates, missing_state):
    for state in ("available", "error", missing_state):
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
            entry['bytes_returned'] = len(entry['text'].encode())
            entry.update(max_bytes=max_bytes, freshness="stale")
            entry.update(_public_reference(reference), path=candidate)
            candidates.append(entry)
    return _choose_reference(reference, candidates, "not_cached")


def _read_remote_references(references, *, tail, max_bytes, refresh, cache):
    if not refresh:
        return [_read_cached_reference(ref, tail, max_bytes, cache) for ref in references]
    paths = list(dict.fromkeys(candidate for ref in references for candidate in ref["paths"]))
    indices = {path: index for index, path in enumerate(paths)}
    snapshots, error = _query_remote_tails(references[0]["config"], paths, max_bytes)
    if error:
        return [{**_public_reference(ref), "path": ref["paths"][0], "state": "error", "error": error} for ref in references]
    observed_at = datetime.now(timezone.utc).isoformat()
    output = []
    for reference in references:
        candidates = []
        for candidate in reference["paths"]:
            candidates.append(_decode_remote_entry(reference, candidate, snapshots.get(indices[candidate]),
                tail=tail, max_bytes=max_bytes, observed_at=observed_at, cache=cache))
        output.append(_choose_reference(reference, candidates, "missing"))
    return output


def read_job_logs(jobs, resolved_jobs, *, job_name=None, task_index=None, tail=40,
                  max_bytes=65536, max_logs=20, refresh=True, profiles=None, root=None, cache=None, stream="both"):
    validate_log_bounds(tail, max_bytes, max_logs)
    if not isinstance(stream, str) or stream not in {'both', 'stdout', 'stderr'}:
        raise ValueError('Log stream must be both, stdout or stderr.')
    root = storage_root() if root is None else root
    cache = InspectionCache(root) if cache is None else cache
    references = select_log_references(jobs, resolved_jobs, profiles=profiles or {}, root=root,
                                      job_name=job_name, task_index=task_index, stream=stream)
    output, remote_groups = {}, {}
    for index, ref in enumerate(references[:max_logs]):
        if ref.get("state") == "error":
            output[index] = ref
        elif not refresh:
            output[index] = _read_cached_reference(ref, tail, max_bytes, cache)
        elif is_remote_machine(ref["config"]):
            remote_groups.setdefault(ref["key"], []).append((index, ref))
        else:
            output[index] = _read_local_reference(ref, tail, max_bytes, cache)
    for group in remote_groups.values():
        entries = _read_remote_references([ref for _, ref in group], tail=tail, max_bytes=max_bytes,
                                         refresh=refresh, cache=cache)
        output.update((index, entry) for (index, _), entry in zip(group, entries))
    ordered = [output[index] for index in sorted(output)]
    if len(references) > max_logs:
        ordered.append({"state": "omitted", "count": len(references) - max_logs,
                        "reason": "Requested log-file bound reached."})
    return ordered
