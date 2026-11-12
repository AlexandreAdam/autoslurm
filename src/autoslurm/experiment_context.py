"""Human renderers over the shared exact-run inspection result."""

from pathlib import Path
from .inspection import inspect_bundle
from .save_load_jobs import select_bundle_snapshot

__all__ = ["experiment_context", "latest_log_context", "job_context"]


def _selected(name, date=None):
    return select_bundle_snapshot(name, desired_date=date, prefer_draft=False)["path"]


def _job_name(path, selector):
    from .save_load_jobs import load_bundle_from_path
    jobs, _, _ = load_bundle_from_path(path)
    if str(selector).isdigit():
        if not 1 <= int(selector) <= len(jobs):
            raise KeyError("Job index is out of range.")
        return jobs[int(selector) - 1]["name"]
    if selector not in {job["name"] for job in jobs}:
        raise KeyError("Job is absent from this exact snapshot.")
    return selector


def job_context(bundle_name, job_name, desired_date=None, include_script=False, include_logs=False, include_status=True):
    path = _selected(bundle_name, desired_date)
    name = _job_name(path, job_name)
    view = inspect_bundle(path, refresh=include_status, include_script=include_script,
                          include_logs=include_logs, job_name=name)
    lines = [f"{bundle_name} {view['saved_at']}", name]
    if include_status:
        job = next(job for job in view["jobs"] if job["name"] == name)
        lines.append(f"status={job['state']} id={job['id']} observation={view['freshness']}")
    if include_script:
        lines.extend(item["content"] or f"script missing: {item['path']}" for item in view.get("scripts", []))
    if include_logs:
        lines.extend(item.get("text", f"Log {item['state']}: {item.get('error', '')}") for item in view["logs"])
    lines.extend(f"Observation error: {item['message']}" for item in view["errors"])
    return "\n".join(lines)


def latest_log_context(bundle_name=None, desired_date=None, job_name=None, array_task=None):
    if bundle_name is None:
        raise ValueError("Select an exact run before reading logs.")
    path = _selected(bundle_name, desired_date)
    name = _job_name(path, job_name) if job_name is not None else None
    view = inspect_bundle(path, include_logs=True, job_name=name, task_index=array_task)
    available = [entry for entry in view["logs"] if entry["state"] == "available"]
    if available:
        return "\n".join(entry["text"] for entry in available)
    return "No logs found for this submitted identity. Select the task and refresh its observation explicitly."


def experiment_context(bundle_name, desired_date=None):
    path = _selected(bundle_name, desired_date)
    view = inspect_bundle(path, include_logs=True, include_script=True)
    lines = [f"## Job or bundle '{bundle_name}'", f"path: {path}",
             f"saved: {view['saved_at']}", f"observation: {view['freshness']} at {view['observed_at']}"]
    for job in view["jobs"]:
        lines.append(f"### Job '{job['name']}' status={job['state']} id={job['id']}")
        if job["id"] is None:
            lines.append(f"job '{job['name']}' has not been submitted yet (submission={job['submission_state']})")
    lines.extend(item["content"] or f"script missing: {item['path']}" for item in view.get("scripts", []))
    lines.extend(f"{item.get('path', '')}\n{item.get('text', item.get('error', item['state']))}" for item in view["logs"])
    lines.extend(f"Observation error: {error['message']}" for error in view["errors"])
    return "\n".join(lines)
