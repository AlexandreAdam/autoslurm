from __future__ import annotations

import re
from datetime import datetime
from typing import Callable, Optional

from .save_load_jobs import load_bundle
from . import status as status_core
from .execution import EXECUTION_METADATA_KEY
from .status_explanations import explain_jobs
from .status_table import table, plain


TERMINAL_STATES = {"COMPLETED", "CANCELLED", *status_core.FAILED_STATES}


def _requested_time(job: dict) -> str:
    slurm = job.get("slurm") or {}
    value = slurm.get("time")
    return str(value) if value else "-"


def _requested_gpus(job: dict) -> str:
    slurm = job.get("slurm") or {}
    gres = slurm.get("gres")
    if not gres:
        return "0"
    text = str(gres)
    match = re.search(r"gpu(?::[^:,]+)?:(\d+)", text)
    if match:
        return match.group(1)
    if "gpu" in text.lower():
        return "1"
    return "0"


def _dependencies_text(job: dict) -> str:
    deps = job.get("dependencies")
    if not deps:
        return "-"
    if isinstance(deps, (list, tuple)):
        return ",".join(str(dep) for dep in deps)
    return str(deps)


def _center_visible(text: str, width: int) -> str:
    pad = max(0, width - status_core._visible_len(text))
    left = pad // 2
    right = pad - left
    return (" " * left) + text + (" " * right)


def bundle_job_rows(
    bundle_name: str,
    desired_date: Optional[datetime] = None,
    *,
    name_contains: Optional[str] = None,
    name_regex: Optional[str] = None,
    ignore_case: bool = False,
    status_predicate: Optional[Callable[[str], bool]] = None,
    show_array_tasks: bool = False,
    array_tasks: Optional[set[int]] = None,
) -> tuple[datetime, list[dict]]:
    jobs, _, bundle_date = load_bundle(bundle_name, desired_date)
    return bundle_job_rows_from_jobs(
        jobs,
        bundle_date,
        name_contains=name_contains,
        name_regex=name_regex,
        ignore_case=ignore_case,
        status_predicate=status_predicate,
        show_array_tasks=show_array_tasks,
        array_tasks=array_tasks,
    )


def rows_from_resolved(jobs, resolved, *, name_contains=None, name_regex=None, ignore_case=False,
                       status_predicate=None, show_array_tasks=False, array_tasks=None):
    # Compatibility paths can supply raw projections. Public inspection already
    # supplies explanations carrying the correct cached/failed freshness.
    if any("explanation" not in job for job in resolved):
        explain_jobs(jobs, resolved)
    by_name = {job["name"]: job for job in jobs}
    compiled = re.compile(name_regex, re.I if ignore_case else 0) if name_regex else None
    rows = []
    for view in resolved:
        name = view["name"]
        if name_contains and (name_contains.lower() if ignore_case else name_contains) not in (name.lower() if ignore_case else name):
            continue
        if compiled and not compiled.search(name):
            continue
        original = by_name[name]
        items = view["tasks"] if show_array_tasks and view["is_array"] else [{"job_id": view["id"], "state": view["state"], "task_index": None, "time_remaining": view.get("time_remaining")}]
        for task in items:
            if array_tasks is not None and view["is_array"] and show_array_tasks and task["task_index"] not in array_tasks:
                continue
            state = task["state"]
            if status_predicate and not status_predicate(state.upper()):
                continue
            rows.append({"index": str(len(rows) + 1), "job_id": task["job_id"] or "-", "job_id_raw": task["job_id"],
                         "name": name, "task_index": task["task_index"], "array": f"{view['counts']['completed']}/{len(view['tasks'])}" if view["is_array"] else "-",
                         "gpus": _requested_gpus(original), "dependencies": _dependencies_text(original),
                         "time_remaining": (task.get("time_remaining") or "-") if state != "PENDING" else "-",
                         "walltime_limit": _requested_time(original),
                         "progress": (f"{view['counts']['completed']}/{len(view['tasks'])} done" +
                             "".join(f" · {count} {key}" for key, count in view["counts"].items()
                                     if count and key != "completed")) if view["is_array"] else "-",
                         "explanation": (task if show_array_tasks and view["is_array"] else view).get("explanation", {}),
                         "raw_status": state, "status_key": state.upper(),
                         "status": status_core._colorize_state_text(status_core.display_state(state)),
                         "machine_name": view["machine"], "machine": str(view["machine"] or "local"),
                         "reason": task.get("reason") if show_array_tasks and view["is_array"] else view.get("reason"), "exit_code": task.get("exit_code") if show_array_tasks and view["is_array"] else view.get("exit_code")})
            if EXECUTION_METADATA_KEY in original:
                rows[-1][EXECUTION_METADATA_KEY] = original[EXECUTION_METADATA_KEY]
    return rows


def bundle_job_rows_from_jobs(jobs, bundle_date, *, name_contains=None, name_regex=None, ignore_case=False,
                              status_predicate=None, show_array_tasks=False, array_tasks=None,
                              machine_statuses_by_machine=None, machine_time_left_by_machine=None):
    from .inspection import observe_job_statuses
    from .inspection_state import resolve_jobs
    from .inspection_collection import load_machine_profiles
    from .execution import producing_machine
    resolved = None
    if machine_statuses_by_machine is not None:
        observations = {}
        profiles, profile_error = load_machine_profiles(jobs)
        for job in jobs:
            try:
                key, _ = producing_machine(job, profiles)
            except ValueError:
                continue
            states = machine_statuses_by_machine.get(job.get("machine"), {})
            times = (machine_time_left_by_machine or {}).get(job.get("machine"), {})
            from .array_status import canonical_job_id
            observations[key] = {"observed_at": None, "errors": [], "records": {
                canonical_job_id(identity): {"state": state, "time_remaining": times.get(identity)}
                for identity, state in states.items() if canonical_job_id(identity)}}
        resolved = resolve_jobs(jobs, observations, profiles=profiles, profile_error=profile_error)
    if resolved is None:
        resolved = observe_job_statuses(jobs)
    return bundle_date, rows_from_resolved(jobs, resolved, name_contains=name_contains,
        name_regex=name_regex, ignore_case=ignore_case, status_predicate=status_predicate,
        show_array_tasks=show_array_tasks, array_tasks=array_tasks)


def bundle_jobs_context(
    bundle_name: str,
    desired_date: Optional[datetime] = None,
    *,
    name_contains: Optional[str] = None,
    name_regex: Optional[str] = None,
    ignore_case: bool = False,
    status_predicate: Optional[Callable[[str], bool]] = None,
    show_array_tasks: bool = False,
    array_tasks: Optional[set[int]] = None,
) -> str:
    bundle_date, rows = bundle_job_rows(
        bundle_name,
        desired_date,
        name_contains=name_contains,
        name_regex=name_regex,
        ignore_case=ignore_case,
        status_predicate=status_predicate,
        show_array_tasks=show_array_tasks,
        array_tasks=array_tasks,
    )
    return bundle_jobs_context_from_rows(
        bundle_name,
        bundle_date,
        rows,
        show_array_tasks=show_array_tasks,
    )


def bundle_jobs_context_from_rows(
    bundle_name: str, bundle_date: datetime, rows: list[dict], *,
    show_array_tasks: bool = False, details: bool = False, width: int | None = None, color="auto",
) -> str:
    lines = [f"{plain(bundle_name)} {bundle_date.isoformat()}"]
    if not rows:
        return "\n".join([*lines, "No jobs matched filters."])
    headers = ["idx", "id", "job", "status", "tasks", "reason"]
    values = []
    for row in rows:
        values.append({"idx": row["index"], "id": row["job_id"], "job": row["name"],
            "status": _state_label(row["raw_status"]),
            "tasks": row.get("progress", "-") if not show_array_tasks else "-",
            "reason": row.get("explanation", {}).get("message") or "-"})
    lines.append(table(headers, values, width=width, optional=("id",),
        maximums={"job": 32, "reason": 70, "tasks": 70}, color=color))
    if details:
        for row in rows:
            lines.append(f"{plain(row['name'])} [{plain(row['job_id'])}] "
                f"reason={plain(row.get('reason') or '-')} exit={plain(row.get('exit_code') or '-')} "
                f"limit={plain(row.get('walltime_limit', '-'))} "
                f"gpus={plain(row['gpus'])} dependencies={plain(row['dependencies'])} "
                f"time remaining={plain(row['time_remaining'])} array={plain(row.get('array', '-'))}")
            if row.get("explanation", {}).get("message"):
                lines.append("  " + plain(row["explanation"]["message"]))
    return "\n".join(lines)


def _task_summary(counts):
    labels = {"failed": "failed", "unknown": "unknown", "running": "running", "pending": "waiting",
              "completed": "done", "cancelled": "cancelled", "not_submitted": "not submitted"}
    return " · ".join(f"{counts.get(key, 0)} {label}" for key, label in labels.items() if counts.get(key)) or "No task data"


def _state_label(state):
    return {"READY_TO_GO": "UNSUBMITTED", "NOT_SUBMITTED": "UNSUBMITTED"}.get(state.upper(), state.upper())


def _run_label(view):
    return "QUEUED" if view["state"] == "pending" else _state_label(view["state"])


def _data_label(view):
    return {"fresh": "checked", "stale": "cached", "partial": "partially checked",
            "failed": "unavailable", "never": "not checked"}[view["freshness"]]


def _check_text(views):
    def timestamp(value):
        try:
            return datetime.fromisoformat(value).isoformat(sep=" ", timespec="seconds").replace("+00:00", " UTC")
        except ValueError:
            return plain(value)
    fresh = [timestamp(view["observed_at"]) for view in views if view["freshness"] == "fresh" and view.get("observed_at")]
    previous = [timestamp(view["observed_at"]) for view in views if view["freshness"] != "fresh" and view.get("observed_at")]
    if fresh:
        # Keep recorded timezone; timestamps describe data collection, not job start.
        span = sorted(set(fresh))
        return "Checked: " + (span[0] if len(span) == 1 else span[0] + " to " + span[-1])
    if any(view["freshness"] == "partial" for view in views):
        return "Partially checked: " + (max(previous) if previous else "time unavailable")
    if any(view["freshness"] == "failed" for view in views):
        return "Status check failed: " + (max(previous) if previous else "time unavailable")
    if previous:
        return "Last saved check: " + max(previous) + " (not refreshed)"
    return "Not checked: no successful scheduler check is available."


def summary_text(entries, views, *, details=False, width=None, color="auto"):
    if not views:
        return "No saved bundles found."
    headers = ["idx", "run", "status", "tasks"]
    if any(view["freshness"] != "fresh" for view in views):
        headers.append("data")
    rows = []
    for index, (entry, view) in enumerate(zip(entries, views), 1):
        counts = {key: sum(job["counts"][key] for job in view["jobs"])
                  for key in ("pending", "running", "completed", "failed", "cancelled", "unknown", "not_submitted")}
        rows.append({"idx": str(index), "run": str(entry["bundle"]), "status": _run_label(view),
                     "tasks": _task_summary(counts), "data": _data_label(view)})
    lines = [table(headers, rows, width=width, color=color, maximums={"run": 42, "tasks": 100}), _check_text(views),
             "Tasks include supporting jobs; done means scheduler completion."]
    if "data" in headers:
        lines.append("cached = last saved data; partially checked = incomplete refresh; unavailable = check failed.")
    if details:
        for index, (entry, view) in enumerate(zip(entries, views), 1):
            lines.append(f"{index}. {plain(entry['bundle'])} saved={plain(view['saved_at'])} "
                         f"data={_data_label(view)} checked={plain(view.get('observed_at') or 'never')}")
            lines.append("   " + rows[index - 1]["tasks"])
            lines.append("   " + plain(view["bundle_path"]))
    lines.extend(f"{plain(entry['bundle'])}: {plain(error['source'])}: {plain(error['message'])}"
                 for entry, view in zip(entries, views) for error in view["errors"])
    return "\n".join(lines)


def observation_text(view, *, details=False):
    lines = [f"Run: {_run_label(view)}", _check_text([view])]
    if view["freshness"] != "fresh":
        lines.append("Status data: " + _data_label(view))
    for job in view["jobs"]:
        if details and job["is_array"] and (job.get("reason") or job.get("exit_code")):
            lines.append(f"Parent {plain(job['id'])}: {plain(job['scheduler_state'])} "
                         f"reason={plain(job.get('reason') or '-')} exit={plain(job.get('exit_code') or '-')}")
    lines.extend(f"Status check error: {plain(error['source'])}: {plain(error['message'])}" for error in view["errors"])
    return "\n".join(lines)
