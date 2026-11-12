"""Shared exact-run observations for terminal, agents and Python clients."""

import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from .array_status import declared_array_indices, aggregate_states, status_for_job_id, FAILED_STATES, RUNNING_LIKE_STATES
from .execution import EXECUTION_METADATA_KEY
from .save_load_jobs import load_bundle_from_path, list_saved_bundles
from .scheduler import query_scheduler
from .storage import storage_root
from .submission import load_submission, SUBMISSION_METADATA_KEY, atomic_json
from .utils import load_config

__all__ = ["inspect_bundle", "inspect_bundles", "list_runs"]


def _profiles(jobs):
    if all(EXECUTION_METADATA_KEY in job or job.get("machine") is None for job in jobs):
        return {}, None
    try:
        return load_config().get("machines", {}), None
    except EnvironmentError as exc:
        return {}, str(exc)


def producing_machine(job, profiles=None):
    execution = job.get(EXECUTION_METADATA_KEY)
    name = job.get("machine")
    if execution is not None:
        config = execution["transport"] if execution["is_remote"] else {}
    elif name is None:
        config = {}
    else:
        profiles = profiles if profiles is not None else _profiles([job])[0]
        if name not in profiles:
            raise ValueError(f"Producing machine {name!r} is unavailable; no local fallback.")
        config = profiles[name]
    key = json.dumps({"machine": name, "transport": {key: config[key] for key in ("hostname", "hosturl", "username", "key_path") if key in config}}, sort_keys=True)
    return key, config


def observe_jobs(jobs):
    profiles, profile_error = _profiles(jobs)
    groups = {}
    for job in jobs:
        if job.get("id") is None:
            continue
        try:
            key, config = producing_machine(job, profiles)
        except ValueError:
            continue
        group = groups.setdefault(key, {"ids": [], "config": config, "machine": job.get("machine")})
        group["ids"].append(str(job["id"]))
    observations = {}
    for key, group in groups.items():
        try:
            observations[key] = query_scheduler(group["ids"], group["config"], group["machine"])
        except ValueError as exc:
            observations[key] = {"records": {}, "observed_at": None,
                                 "errors": [{"source": "definition", "message": str(exc)}]}
    return observations


def resolve_jobs(jobs, observations=None):
    """One identity/state policy; optional observations make rendering query-free."""
    observations = observe_jobs(jobs) if observations is None else observations
    profiles, _ = _profiles(jobs)
    output = []
    for job in jobs:
        identity = str(job["id"]) if job.get("id") is not None else None
        submission = job.get(SUBMISSION_METADATA_KEY, {})
        submission_state = submission.get("state", "accepted" if identity else "not_submitted")
        errors = []
        observation = {"records": {}, "errors": [], "observed_at": None}
        if identity:
            try:
                key, _ = producing_machine(job, profiles)
                observation = observations.get(key, observation)
            except ValueError as exc:
                errors.append({"source": "configuration", "message": str(exc)})
        errors.extend(observation["errors"])
        records = observation["records"]
        parent = records.get(identity, {})
        spec = (job.get("slurm") or {}).get("array")
        indices = declared_array_indices(spec)
        if spec is not None and indices is None:
            errors.append({"source": "definition", "message": "Invalid declared array indices."})
        if indices is None and identity:
            observed_indices = [int(key.split("_")[1]) for key in records if key.startswith(identity + "_")]
            indices = sorted(set(observed_indices)) or None

        def task(index):
            logical = identity + "_" + str(index) if identity and index is not None else identity
            record = records.get(logical, {})
            state = record.get("state", "UNKNOWN") if identity else submission_state.upper()
            return {"job_name": job["name"], "job_id": logical, "parent_id": identity,
                    "task_index": index, "raw_id": record.get("raw_id"),
                    "state": state, "scheduler_state": record.get("state"),
                    "submission_state": submission_state, "source": record.get("source", "none"),
                    "observed_at": observation["observed_at"], "reason": record.get("reason"),
                    "exit_code": record.get("exit_code"), "time_remaining": record.get("time_remaining")}

        tasks = [task(index) for index in indices] if indices is not None else [task(None)]
        if not identity:
            state = submission_state.upper()
        elif indices is not None:
            statuses = {item["job_id"]: item["state"] for item in tasks}
            if parent.get("state"):
                statuses[identity] = parent["state"]
            state = status_for_job_id(identity, statuses, declared_total=len(indices))
        else:
            state = tasks[0]["state"]
            if spec is not None and state == "COMPLETED":
                state = "UNKNOWN"
        counts = {"completed": 0, "failed": 0, "cancelled": 0, "running": 0, "pending": 0, "unknown": 0, "not_submitted": 0}
        for item in tasks:
            value = item["state"]
            category = "completed" if value == "COMPLETED" else "cancelled" if value == "CANCELLED" else "failed" if value in FAILED_STATES else "running" if value in RUNNING_LIKE_STATES else "pending" if value == "PENDING" else "not_submitted" if not identity and value == "NOT_SUBMITTED" else "unknown"
            counts[category] += 1
        output.append({"name": job["name"], "id": identity, "machine": job.get("machine"),
                       "submission_state": submission_state, "submission_error": submission.get("error"),
                       "state": state, "scheduler_state": parent.get("state"),
                       "is_array": indices is not None, "tasks": tasks, "counts": counts,
                       "reason": parent.get("reason"), "exit_code": parent.get("exit_code"),
                       "time_remaining": parent.get("time_remaining"),
                       "observed_at": observation["observed_at"], "errors": errors})
    return output


def bundle_state(jobs):
    if not jobs:
        return "unknown"
    states = [job["state"] for job in jobs]
    if "UNCERTAIN" in states:
        return "uncertain"
    if any(state in {"REJECTED", "BLOCKED"} for state in states):
        return "partial" if any(job["id"] for job in jobs) else "rejected"
    if all(state == "NOT_SUBMITTED" for state in states):
        return "ready_to_go"
    return aggregate_states(states).lower()


def _cache_path(path):
    digest = hashlib.sha256(str(Path(path).resolve()).encode()).hexdigest()
    return storage_root() / "observations" / (digest + ".json")


def _load_selected(path):
    jobs, _, date = load_bundle_from_path(path)
    jobs = copy.deepcopy(jobs)
    receipt_refs = {job[SUBMISSION_METADATA_KEY]["receipt_path"] for job in jobs if job.get(SUBMISSION_METADATA_KEY)}
    errors = []
    receipts = []
    for reference in receipt_refs:
        try:
            receipt = load_submission(reference)
            if set(receipt["jobs"]) != {job["name"] for job in jobs}:
                raise ValueError("Receipt and selected bundle jobs disagree.")
            for job in jobs:
                if job.get(SUBMISSION_METADATA_KEY, {}).get("submission_id") != receipt["submission_id"]:
                    raise ValueError("Receipt and selected bundle identity disagree.")
            for job in jobs:
                outcome = receipt["jobs"][job["name"]]
                if job.get("id") and outcome.get("id") != str(job["id"]):
                    raise ValueError("Receipt would discard a known scheduler ID.")
            for job in jobs:
                outcome = receipt["jobs"][job["name"]]
                if outcome.get("id"):
                    job["id"] = outcome["id"]
                job[SUBMISSION_METADATA_KEY] = {**job[SUBMISSION_METADATA_KEY], **outcome}
            receipts.append({"submission_id": receipt["submission_id"], "state": receipt["state"], "receipt_path": reference})
        except (OSError, ValueError, KeyError) as exc:
            errors.append({"source": "receipt", "message": str(exc), "path": reference})
    return jobs, date, receipts, errors


def _safe_selected(path):
    try:
        return _load_selected(path)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return [], None, [], [{"source": "definition", "message": str(exc), "path": str(path)}]


def inspect_bundles(bundle_paths, *, refresh=True, include_logs=False, job_name=None, task_index=None, tail=40, max_log_bytes=65536, max_logs=20, include_script=False, refresh_logs=None):
    paths = [Path(path).resolve() for path in bundle_paths]
    def attach(view, jobs, date):
        if job_name is not None and job_name not in {job["name"] for job in jobs}:
            raise ValueError("Selected job is absent from this exact snapshot.")
        if task_index is not None and not any(task["task_index"] == int(task_index) for job in view["jobs"] if job_name is None or job["name"] == job_name for task in job["tasks"]):
            raise ValueError("Selected task is absent from the declared/observed indices.")
        if include_logs:
            from .log_files import read_job_logs
            view["logs"] = read_job_logs(jobs, view["jobs"], job_name=job_name, task_index=task_index,
                tail=tail, max_bytes=max_log_bytes, max_logs=max_logs,
                refresh=refresh and refresh_logs is not False)
        if include_script:
            from .utils import name_slurm_script
            from .storage import slurm_dir
            view["scripts"] = []
            for job in jobs:
                if job_name is None or job["name"] == job_name:
                    script_path = slurm_dir() / name_slurm_script(job, date)
                    try:
                        content = script_path.read_text()
                    except OSError as exc:
                        content = None
                        view["errors"].append({"source": "script", "message": str(exc), "path": str(script_path)})
                    view["scripts"].append({"job_name": job["name"], "path": str(script_path), "content": content})
        for entry in view["logs"]:
            if entry["state"] == "error":
                view["errors"].append({"source": "log", "message": entry["error"], "path": entry.get("path")})
        if view["errors"] and view["freshness"] == "fresh":
            view["freshness"] = "partial"
        return view
    if not refresh:
        cached = []
        for path in paths:
            cache = _cache_path(path)
            try:
                view = json.loads(cache.read_text())
            except (OSError, ValueError):
                view = None
            if isinstance(view, dict) and path.is_file() and view.get("definition_sha256") == hashlib.sha256(path.read_bytes()).hexdigest():
                view["freshness"] = "stale"
                view["logs"] = []
                view.pop("scripts", None)
                cached.append(view)
            else:
                cached.append(_inspect_without_queries(path))
        for path, view in zip(paths, cached):
            jobs, date, _, _ = _safe_selected(path)
            attach(view, jobs, date)
        return cached
    selected = [_safe_selected(path) for path in paths]
    observations = observe_jobs([job for jobs, _, _, _ in selected for job in jobs])
    views = []
    for path, (jobs, date, receipts, errors) in zip(paths, selected):
        resolved = resolve_jobs(jobs, observations)
        for job in resolved:
            errors.extend(job["errors"])
        failed = bool(errors) and not any(task["scheduler_state"] for job in resolved for task in job["tasks"])
        view = {"bundle_path": str(path), "saved_at": date.isoformat() if date else "unknown", "observed_at": datetime.now(timezone.utc).isoformat(),
                "freshness": "failed" if failed else "partial" if errors else "fresh", "state": bundle_state(resolved) if date else "broken",
                "jobs": resolved, "submissions": receipts, "errors": errors, "logs": []}
        view["definition_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        previous_path = _cache_path(path)
        if errors and previous_path.exists():
            try:
                previous = json.loads(previous_path.read_text())
                if previous.get("definition_sha256") != view["definition_sha256"]:
                    raise ValueError("Cached observation belongs to a different definition.")
                view["last_observed"] = previous.get("last_observed") if previous["freshness"] == "failed" and previous.get("last_observed") else {"observed_at": previous["observed_at"], "state": previous["state"], "freshness": "stale"}
            except (OSError, ValueError, KeyError):
                pass
        attach(view, jobs, date)
        try:
            atomic_json(previous_path, view)
        except OSError as exc:
            view["errors"].append({"source": "cache", "message": str(exc)})
            if view["freshness"] == "fresh":
                view["freshness"] = "partial"
        views.append(view)
    return views


def _inspect_without_queries(path):
    jobs, date, receipts, errors = _safe_selected(path)
    resolved = resolve_jobs(jobs, {})
    for job in resolved:
        errors.extend(job["errors"])
    return {"bundle_path": str(path), "saved_at": date.isoformat() if date else "unknown", "observed_at": None, "freshness": "never",
            "state": bundle_state(resolved) if date else "broken", "jobs": resolved, "submissions": receipts, "errors": errors, "logs": []}


def inspect_bundle(bundle_path=None, *, receipt_path=None, **kwargs):
    if (bundle_path is None) == (receipt_path is None):
        raise ValueError("Select one exact bundle_path or receipt_path.")
    if receipt_path is not None:
        bundle_path = load_submission(receipt_path)["bundle_path"]
    return inspect_bundles([bundle_path], **kwargs)[0]


def list_runs(bundle_name=None):
    return [{"bundle": entry["bundle"], "bundle_path": str(entry["path"]), "saved_at": entry["date"].isoformat()}
            for entry in list_saved_bundles(bundle_name=bundle_name)]
