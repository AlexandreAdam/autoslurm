"""Pure projection of supplied definitions and observations into task evidence."""

import copy

from .array_status import (
    declared_array_indices, aggregate_states, status_for_job_id,
    parent_job_id, _array_task_index, FAILED_STATES, RUNNING_LIKE_STATES,
)
from .execution import producing_machine
from .submission import SUBMISSION_METADATA_KEY


def _task_indices(job, identity, records, errors):
    specification = (job.get("slurm") or {}).get("array")
    indices = declared_array_indices(specification)
    if specification is not None and indices is None:
        errors.append({"source": "definition", "message": "Invalid declared array indices."})
    if indices is None and identity:
        indices = sorted({index for key in records
                          if (index := _array_task_index(identity, key)) is not None}) or None
    return indices


def _project_task(job, identity, index, observation, submission_state):
    logical = identity + "_" + str(index) if identity and index is not None else identity
    record = observation["records"].get(logical, {})
    return {
        "job_name": job["name"], "job_id": logical, "parent_id": identity,
        "task_index": index, "raw_id": record.get("raw_id"),
        "state": record.get("state", "UNKNOWN") if identity else submission_state.upper(),
        "scheduler_state": record.get("state"), "submission_state": submission_state,
        "source": record.get("source", "none"), "observed_at": observation["observed_at"],
        "reason": record.get("reason"), "exit_code": record.get("exit_code"),
        "time_remaining": record.get("time_remaining"),
    }


def _task_counts(tasks, identity):
    counts = dict.fromkeys(("completed", "failed", "cancelled", "running", "pending", "unknown", "not_submitted"), 0)
    categories = {"COMPLETED": "completed", "CANCELLED": "cancelled", "PENDING": "pending"}
    for task in tasks:
        state = task["state"]
        if state in FAILED_STATES and state != "CANCELLED":
            category = "failed"
        elif state in RUNNING_LIKE_STATES:
            category = "running"
        elif not identity and state == "NOT_SUBMITTED":
            category = "not_submitted"
        else:
            category = categories.get(state, "unknown")
        counts[category] += 1
    return counts


def _project_job(job, observations, profiles, profile_error):
    identity = str(job["id"]) if job.get("id") is not None else None
    submission = job.get(SUBMISSION_METADATA_KEY, {})
    submission_state = submission.get("state", "accepted" if identity else "not_submitted")
    observation = {"records": {}, "errors": [], "observed_at": None}
    errors = []
    if identity:
        if parent_job_id(identity) is None:
            errors.append({"source": "definition", "message": f"Invalid scheduler parent ID: {identity!r}."})
        else:
            try:
                key, _ = producing_machine(job, profiles)
                observation = observations.get(key, observation)
            except ValueError as error:
                message = str(error) + (f" Profile read failed: {profile_error}" if profile_error else "")
                errors.append({"source": "configuration", "message": message})
    errors.extend(copy.deepcopy(observation["errors"]))
    parent = observation["records"].get(identity, {})
    indices = _task_indices(job, identity, observation["records"], errors)
    tasks = [_project_task(job, identity, index, observation, submission_state)
             for index in (indices if indices is not None else [None])]
    if not identity:
        state = submission_state.upper()
    elif indices is not None:
        statuses = {task["job_id"]: task["state"] for task in tasks}
        if parent.get("state"):
            statuses[identity] = parent["state"]
        state = status_for_job_id(identity, statuses, declared_total=len(indices))
    else:
        state = tasks[0]["state"]
        if (job.get("slurm") or {}).get("array") is not None and state == "COMPLETED":
            state = "UNKNOWN"
    return {
        "name": job["name"], "id": identity, "machine": job.get("machine"),
        "submission_state": submission_state, "submission_error": submission.get("error"),
        "state": state, "scheduler_state": parent.get("state"), "is_array": indices is not None,
        "tasks": tasks, "counts": _task_counts(tasks, identity),
        "reason": parent.get("reason"), "exit_code": parent.get("exit_code"),
        "time_remaining": parent.get("time_remaining"),
        "observed_at": observation["observed_at"], "errors": errors,
    }


def resolve_jobs(jobs, observations, *, profiles=None, profile_error=None):
    """Project provided data only; callers explicitly collect observations first."""
    return [_project_job(job, observations, profiles or {}, profile_error) for job in jobs]


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


def project_run(run, observations, *, profiles, profile_error=None, observed_at=None, fresh=True):
    """Assemble a run observation from supplied data and an explicit timestamp."""
    resolved = resolve_jobs(run.jobs, observations, profiles=profiles, profile_error=profile_error)
    errors = copy.deepcopy(run.errors)
    errors.extend(error for job in resolved for error in job["errors"])
    has_evidence = any(job["scheduler_state"] or any(task["scheduler_state"] for task in job["tasks"]) for job in resolved)
    freshness = "never" if not fresh else "failed" if errors and not has_evidence else "partial" if errors else "fresh"
    return {
        "bundle_path": str(run.path), "saved_at": run.date.isoformat() if run.date else "unknown",
        "observed_at": observed_at, "freshness": freshness,
        "state": bundle_state(resolved) if run.date else "broken",
        "jobs": resolved, "submissions": copy.deepcopy(run.submissions), "errors": errors,
        "logs": [], "definition_sha256": run.fingerprint,
    }
