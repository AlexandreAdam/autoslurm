from __future__ import annotations

import re
from datetime import datetime
from typing import Callable, Optional

from .save_load_jobs import load_bundle
from . import status as status_core


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
                         "time_remaining": task.get("time_remaining") or (_requested_time(original) if state == "PENDING" else "-"),
                         "raw_status": state, "status_key": state.upper(),
                         "status": status_core._colorize_state_text(status_core.display_state(state)),
                         "machine_name": view["machine"], "machine": str(view["machine"] or "local"),
                         "reason": task.get("reason") if show_array_tasks and view["is_array"] else view.get("reason"), "exit_code": task.get("exit_code") if show_array_tasks and view["is_array"] else view.get("exit_code")})
    return rows


def bundle_job_rows_from_jobs(jobs, bundle_date, *, name_contains=None, name_regex=None, ignore_case=False,
                              status_predicate=None, show_array_tasks=False, array_tasks=None,
                              machine_statuses_by_machine=None, machine_time_left_by_machine=None):
    from .inspection import resolve_jobs, producing_machine, _profiles
    observations = None
    if machine_statuses_by_machine is not None:
        observations = {}
        profiles, _ = _profiles(jobs)
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
    return bundle_date, rows_from_resolved(jobs, resolve_jobs(jobs, observations), name_contains=name_contains,
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
    bundle_name: str,
    bundle_date: datetime,
    rows: list[dict],
    *,
    show_array_tasks: bool = False,
) -> str:
    lines = [f"{bundle_name} {bundle_date.isoformat()}"]
    if not rows:
        lines.append("No jobs matched filters.")
        return "\n".join(lines)

    idx_width = max(len("idx"), max(len(row["index"]) for row in rows))
    id_width = max(len("id"), max(len(row["job_id"]) for row in rows))
    name_width = max(len("name"), max(len(row["name"]) for row in rows))
    time_remaining_width = max(len("time remaining"), max(len(row["time_remaining"]) for row in rows))
    gpus_width = max(len("gpus"), max(len(row["gpus"]) for row in rows))
    deps_width = max(len("dependencies"), max(len(row["dependencies"]) for row in rows))
    status_width = max(len("status"), max(status_core._visible_len(row["status"]) for row in rows))
    if show_array_tasks:
        lines.append(
            f"{'idx'.center(idx_width)}  "
            f"{'id'.center(id_width)}  "
            f"{'name'.center(name_width)}  "
            f"{'gpus'.center(gpus_width)}  "
            f"{'dependencies'.center(deps_width)}  "
            f"{'time remaining'.center(time_remaining_width)}  "
            f"{'status'.center(status_width)}"
        )
    else:
        array_width = max(len("array"), max(len(row["array"]) for row in rows))
        lines.append(
            f"{'idx'.center(idx_width)}  "
            f"{'id'.center(id_width)}  "
            f"{'name'.center(name_width)}  "
            f"{'array'.center(array_width)}  "
            f"{'gpus'.center(gpus_width)}  "
            f"{'dependencies'.center(deps_width)}  "
            f"{'time remaining'.center(time_remaining_width)}  "
            f"{'status'.center(status_width)}"
        )
    for row in rows:
        deps_rendered = (
            row["dependencies"].center(deps_width)
            if row["dependencies"] == "-"
            else row["dependencies"].ljust(deps_width)
        )
        time_remaining_rendered = (
            row["time_remaining"].center(time_remaining_width)
            if row["time_remaining"] == "-"
            else row["time_remaining"].ljust(time_remaining_width)
        )
        if show_array_tasks:
            row_text = (
                f"{row['index'].ljust(idx_width)}  "
                f"{row['job_id'].ljust(id_width)}  "
                f"{row['name'].ljust(name_width)}  "
                f"{row['gpus'].ljust(gpus_width)}  "
                f"{deps_rendered}  "
                f"{time_remaining_rendered}  "
                f"{_center_visible(row['status'], status_width)}"
            )
        else:
            row_text = (
                f"{row['index'].ljust(idx_width)}  "
                f"{row['job_id'].ljust(id_width)}  "
                f"{row['name'].ljust(name_width)}  "
                f"{row['array'].ljust(array_width)}  "
                f"{row['gpus'].ljust(gpus_width)}  "
                f"{deps_rendered}  "
                f"{time_remaining_rendered}  "
                f"{_center_visible(row['status'], status_width)}"
            )
        if row["status_key"] == "RUNNING":
            row_text = f"{status_core.ANSI_YELLOW}{row_text}{status_core.ANSI_RESET}"
        elif row["status_key"] == "COMPLETED":
            row_text = f"{status_core.ANSI_GREEN}{row_text}{status_core.ANSI_RESET}"
        elif row["status_key"] == "CANCELLED" or row["status_key"] in status_core.FAILED_STATES:
            row_text = f"{status_core.ANSI_RED}{row_text}{status_core.ANSI_RESET}"
        lines.append(row_text)
        if row.get("reason") or row.get("exit_code"):
            lines.append(f"  {row['job_id']} reason={row.get('reason') or '-'} exit={row.get('exit_code') or '-'}")
    return "\n".join(lines)


def summary_text(entries, views):
    if not views:
        return "No saved bundles found."
    headers = ["idx", "bundle", "status", "saved", "jobs", "array", "pending", "running", "completed", "failed", "cancelled", "unknown", "observation"]
    rows = []
    for index, (entry, view) in enumerate(zip(entries, views), 1):
        counts = {key: sum(job["counts"][key] for job in view["jobs"]) for key in ("pending", "running", "completed", "failed", "cancelled", "unknown")}
        rows.append([str(index), str(entry["bundle"]), view["state"], view["saved_at"].replace("T", " "), str(len(view["jobs"])),
                     str(sum(len(job["tasks"]) for job in view["jobs"] if job["is_array"])),
                     *[str(counts[key]) for key in ("pending", "running", "completed", "failed", "cancelled", "unknown")], view["freshness"]])
    widths = [max(len(header), *(len(row[index]) for row in rows)) for index, header in enumerate(headers)]
    text = "\n".join("  ".join(value.ljust(width) for value, width in zip(row, widths)) for row in [headers, *rows])
    errors = [f"{entry['bundle']}: {error['source']}: {error['message']}" for entry, view in zip(entries, views) for error in view["errors"]]
    return "\n".join([text, *errors])


def observation_text(view):
    lines = [f"Run: {view['state']}", f"Observation: {view['freshness']} at {view['observed_at']}"]
    for job in view["jobs"]:
        if job["is_array"] and (job.get("reason") or job.get("exit_code")):
            lines.append(f"Parent {job['id']}: {job['scheduler_state']} reason={job.get('reason') or '-'} exit={job.get('exit_code') or '-'}")
    lines.extend(f"Observation error: {error['source']}: {error['message']}" for error in view["errors"])
    return "\n".join(lines)
