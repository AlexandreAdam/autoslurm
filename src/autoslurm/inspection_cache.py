"""Observation/excerpt cache I/O. Unavailable caches never erase live evidence."""

import copy
import hashlib
from pathlib import Path

from .record_files import atomic_json, read_json, _read_error, _write_error
from .errors import SelectionError, RecordWriteError


def _errors_valid(errors):
    return isinstance(errors, list) and all(isinstance(error, dict)
        and isinstance(error.get("source"), str) and isinstance(error.get("message"), str) for error in errors)


def _observation_valid(view):
    if not isinstance(view, dict):
        return False
    if not all(key in view for key in ("bundle_path", "saved_at", "observed_at", "state", "freshness", "jobs", "submissions", "errors")):
        return False
    if not all(isinstance(view[key], str) for key in ("state", "bundle_path", "saved_at")) or not _errors_valid(view["errors"]):
        return False
    if not isinstance(view["freshness"], str) or view["freshness"] not in {"fresh", "partial", "failed", "stale", "never"} or not isinstance(view["submissions"], list) or not isinstance(view["jobs"], list):
        return False
    if view["observed_at"] is not None and not isinstance(view["observed_at"], str):
        return False
    previous = view.get("last_observed")
    if previous is not None and (not isinstance(previous, dict)
            or not isinstance(previous.get("state"), str) or "observed_at" not in previous):
        return False
    if previous and previous.get('jobs') is not None:
        if not _observation_valid({**view, 'jobs': previous['jobs'], 'last_observed': None}):
            return False
    for job in view["jobs"]:
        if not isinstance(job, dict) or not all(key in job for key in ("name", "id", "state", "machine", "is_array", "counts", "tasks", "errors")):
            return False
        if not isinstance(job["name"], str) or not isinstance(job["state"], str) or not _errors_valid(job["errors"]):
            return False
        if (job["id"] is not None and not isinstance(job["id"], str)) or not isinstance(job["is_array"], bool):
            return False
        if job["machine"] is not None and not isinstance(job["machine"], str):
            return False
        if not isinstance(job["tasks"], list) or not isinstance(job["counts"], dict):
            return False
        if not all(type(job["counts"].get(key)) is int and 0 <= job['counts'][key] <= len(job['tasks']) for key in ("completed", "failed", "cancelled", "running", "pending", "unknown", "not_submitted")):
            return False
        if sum(job['counts'][key] for key in ('completed','failed','cancelled','running','pending','unknown','not_submitted')) != len(job['tasks']):
            return False
        for task in job["tasks"]:
            if not isinstance(task, dict) or not all(key in task for key in ("job_id", "parent_id", "task_index", "state", "scheduler_state", "source")):
                return False
            if not isinstance(task["state"], str) or (task["task_index"] is not None and type(task["task_index"]) is not int):
                return False
            if any(task[key] is not None and not isinstance(task[key], str) for key in ("job_id", "parent_id", "scheduler_state", "source")):
                return False
    return True


def _excerpt_valid(entry):
    return (isinstance(entry, dict) and entry.get("state") == "available"
        and isinstance(entry.get("text"), str) and isinstance(entry.get("path"), str)
        and type(entry.get("size_bytes")) is int and entry["size_bytes"] >= 0
        and isinstance(entry.get("truncated"), bool) and isinstance(entry.get("observed_at"), str)
        and isinstance(entry.get("job_name"), str) and isinstance(entry.get("job_id"), str)
        and "task_index" in entry and (entry["task_index"] is None or type(entry["task_index"]) is int))


class InspectionCache:
    def __init__(self, root):
        self.root = Path(root) / "observations"

    def observation_path(self, bundle_path):
        digest = hashlib.sha256(str(Path(bundle_path).resolve()).encode()).hexdigest()
        return self.root / (digest + ".json")

    def excerpt_path(self, machine_key, path):
        digest = hashlib.sha256((machine_key + path).encode()).hexdigest()
        return self.root / "logs" / (digest + ".json")

    def _read(self, path, validator):
        try:
            value = read_json(path, context={"resource": "inspection_cache"})
            if not validator(value):
                raise _read_error(path, code="record_invalid", stage="validate_cache",
                    context={"resource": "inspection_cache"}, summary="Invalid cached evidence structure.")
            return value, None
        except SelectionError as error:
            if error.diagnostic.code == "resource_missing":
                return None, None
            return None, self._error_entry(path, error)

    def _error_entry(self, path, error):
        return {"source": "cache", "message": str(error), "path": str(path), "diagnostic": error.diagnostic.to_dict()}

    def load_observation(self, run):
        if run.fingerprint is None:
            return None, None
        view, error = self._read(self.observation_path(run.path), _observation_valid)
        if view is None:
            return None, error
        if view.get("definition_sha256") != run.fingerprint:
            return None, None
        if view["bundle_path"] != str(run.path):
            path = self.observation_path(run.path)
            return None, self._error_entry(path, _read_error(path, code="record_invalid", stage="validate_cache",
                context={"resource": "inspection_cache", "bundle_path": str(run.path)},
                summary="Cached run identity disagrees with its selected path."))
        expected = {(job["name"], str(job["id"]) if job.get("id") is not None else None) for job in run.jobs}
        actual = {(job["name"], job["id"]) for job in view["jobs"]}
        if expected != actual:
            return None, None
        # Older sidecars may contain artifacts; keep them out of status evidence.
        view["logs"] = []
        view.pop("scripts", None)
        view["errors"] = [error for error in view["errors"] if error["source"] not in {"log", "script"}]
        return view, None

    def save_observation(self, view):
        core = copy.deepcopy(view)
        core["logs"] = []
        core.pop("scripts", None)
        return self._write(self.observation_path(view["bundle_path"]), core, bundle_path=view["bundle_path"])

    def load_excerpt(self, machine_key, path):
        entry, error = self._read(self.excerpt_path(machine_key, path), _excerpt_valid)
        if entry is not None and entry["path"] != path:
            selected = self.excerpt_path(machine_key, path)
            return None, self._error_entry(selected, _read_error(selected, code="record_invalid", stage="validate_cache",
                context={"resource": "inspection_cache", "logical_path": path},
                summary="Cached log path disagrees with the requested path."))
        return entry, error

    def save_excerpt(self, machine_key, path, entry):
        return self._write(self.excerpt_path(machine_key, path), entry)

    def _write(self, path, value, *, bundle_path=None):
        try:
            atomic_json(path, value)
            return None
        except OSError as error:
            if not isinstance(error, RecordWriteError):
                native = error
                error = _write_error(native, path, "cache_write",
                    {"record_publication": "unknown", "record_durability": "unknown"})
                error.__cause__ = native
            error.diagnostic = error.diagnostic.with_context(resource="inspection_cache", bundle_path=bundle_path)
            return self._error_entry(path, error)
