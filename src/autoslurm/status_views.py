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


def _colorize_state_text(state_text: str) -> str:
    upper = state_text.upper()
    if upper == "SUCCESS":
        return f"{status_core.ANSI_GREEN}{state_text}{status_core.ANSI_RESET}"
    if upper == "RUNNING":
        return f"{status_core.ANSI_YELLOW}{state_text}{status_core.ANSI_RESET}"
    if upper == "CANCELLED" or upper in status_core.FAILED_STATES:
        return f"{status_core.ANSI_RED}{state_text}{status_core.ANSI_RESET}"
    return state_text


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


def bundle_job_rows_from_jobs(
    jobs: list[dict],
    bundle_date: datetime,
    *,
    name_contains: Optional[str] = None,
    name_regex: Optional[str] = None,
    ignore_case: bool = False,
    status_predicate: Optional[Callable[[str], bool]] = None,
    show_array_tasks: bool = False,
    array_tasks: Optional[set[int]] = None,
    machine_statuses_by_machine: Optional[dict[Optional[str], dict[str, str]]] = None,
    machine_time_left_by_machine: Optional[dict[Optional[str], dict[str, str]]] = None,
) -> tuple[datetime, list[dict]]:
    compiled_regex = None
    if name_regex:
        flags = re.IGNORECASE if ignore_case else 0
        compiled_regex = re.compile(name_regex, flags=flags)

    rows: list[dict] = []
    by_machine: dict[Optional[str], list[dict]] = {}
    for job in jobs:
        by_machine.setdefault(job.get("machine"), []).append(job)

    display_index = 1
    for machine_name, machine_jobs in by_machine.items():
        job_ids = [str(job["id"]) for job in machine_jobs if job.get("id") is not None]
        if machine_statuses_by_machine is not None and machine_name in machine_statuses_by_machine:
            machine_statuses = machine_statuses_by_machine[machine_name]
            raw_time_left = (
                machine_time_left_by_machine[machine_name]
                if machine_time_left_by_machine is not None and machine_name in machine_time_left_by_machine
                else {}
            )
        else:
            machine_statuses = {}
            raw_time_left = {}
            if job_ids:
                try:
                    machine_statuses, raw_time_left = status_core._fetch_statuses_and_time_left_for_job_ids(
                        job_ids, machine_name
                    )
                except Exception:
                    machine_statuses = {}
                    raw_time_left = {}

        machine_parent_statuses: dict[str, str] = {}
        for job in machine_jobs:
            job_id = job.get("id")
            if job_id is None:
                continue
            job_name = str(job["name"])
            job_id_text = str(job_id)
            declared_total = status_core.declared_array_size((job.get("slurm") or {}).get("array"))
            machine_parent_statuses[job_name] = status_core.status_for_job_id(
                job_id_text,
                machine_statuses,
                declared_total=declared_total,
            )
        machine_remaining = {}
        if raw_time_left:
            for job in machine_jobs:
                job_id = job.get("id")
                if job_id is None:
                    continue
                job_name = str(job["name"])
                job_id_text = str(job_id)
                exact = raw_time_left.get(job_id_text)
                if exact is not None:
                    machine_remaining[job_name] = exact
                    continue
                prefix_underscore = f"{job_id_text}_"
                prefix_dot = f"{job_id_text}."
                for key, value in raw_time_left.items():
                    if key.startswith(prefix_underscore) or key.startswith(prefix_dot):
                        machine_remaining[job_name] = value
                        break

        for job in machine_jobs:
            job_name = str(job["name"])
            job_id = job.get("id")
            job_id_text = None if job_id is None else str(job_id)
            declared_total = status_core.declared_array_size((job.get("slurm") or {}).get("array"))

            if job_id_text is None:
                raw_status = "not_submitted"
                status_key = raw_status.upper()
                array_text = f"0/{declared_total}" if declared_total is not None else "-"
                if status_predicate and not status_predicate(status_key):
                    continue
                if name_contains:
                    haystack = job_name.lower() if ignore_case else job_name
                    needle = name_contains.lower() if ignore_case else name_contains
                    if needle not in haystack:
                        continue
                if compiled_regex and not compiled_regex.search(job_name):
                    continue
                rows.append(
                    {
                        "index": str(display_index),
                        "job_id": "-",
                        "job_id_raw": None,
                        "name": job_name,
                        "array": array_text,
                        "gpus": _requested_gpus(job),
                        "dependencies": _dependencies_text(job),
                        "time_remaining": "-",
                        "raw_status": raw_status,
                        "status_key": status_key,
                        "status": _colorize_state_text(raw_status),
                        "machine_name": job.get("machine"),
                        "machine": str(job.get("machine") or "local"),
                    }
                )
                display_index += 1
                continue

            resolved_status = machine_parent_statuses.get(
                job_name,
                status_core.status_for_job_id(
                    job_id_text,
                    machine_statuses,
                    declared_total=declared_total,
                ),
            )
            is_array, array_completed, array_total = status_core.array_progress_for_job_id(
                job_id_text,
                machine_statuses,
                declared_total=declared_total,
            )
            if declared_total is not None:
                is_array = True
                array_total = declared_total
                if resolved_status.upper() == "COMPLETED":
                    array_completed = declared_total
                elif resolved_status.upper() in {"PENDING", "NOT_SUBMITTED"}:
                    array_completed = 0
                else:
                    array_completed = min(array_completed, declared_total)

            if name_contains:
                haystack = job_name.lower() if ignore_case else job_name
                needle = name_contains.lower() if ignore_case else name_contains
                if needle not in haystack:
                    continue
            if compiled_regex and not compiled_regex.search(job_name):
                continue

            if show_array_tasks and (is_array or declared_total is not None):
                task_entries = [
                    (task_id, task_status)
                    for task_id, task_status in machine_statuses.items()
                    if status_core._array_task_index(job_id_text, task_id) is not None
                ]
                task_entries.sort(
                    key=lambda item: (
                        status_core._array_task_index(job_id_text, item[0])
                        if status_core._array_task_index(job_id_text, item[0]) is not None
                        else 10**9,
                        item[0],
                    )
                )
                if array_tasks is not None:
                    task_entries = [
                        item
                        for item in task_entries
                        if status_core._array_task_index(job_id_text, item[0]) in array_tasks
                    ]
                if task_entries:
                    requested_time = _requested_time(job)
                    for task_id, task_status in task_entries:
                        status_key = task_status.upper()
                        if status_predicate and not status_predicate(status_key):
                            continue
                        if status_key in {"PENDING", "NOT_SUBMITTED"}:
                            time_remaining = requested_time
                        elif status_key == "RUNNING":
                            if raw_time_left is not None:
                                time_remaining = raw_time_left.get(task_id, "-")
                            else:
                                time_remaining = status_core._fetch_time_left_for_job_ids(
                                    [task_id], machine_name
                                ).get(task_id, "-")
                        elif status_key in TERMINAL_STATES:
                            time_remaining = "-"
                        else:
                            time_remaining = "-"
                        rows.append(
                            {
                                "index": str(display_index),
                                "job_id": task_id,
                                "job_id_raw": task_id,
                                "name": job_name,
                                "gpus": _requested_gpus(job),
                                "dependencies": _dependencies_text(job),
                                "time_remaining": time_remaining,
                                "raw_status": task_status,
                                "status_key": status_key,
                                "status": _colorize_state_text(status_core.display_state(task_status)),
                                "machine_name": job.get("machine"),
                                "machine": str(job.get("machine") or "local"),
                            }
                        )
                        display_index += 1
                    continue

                if (
                    declared_total is not None
                    and resolved_status.upper() not in status_core.FAILED_STATES
                    and resolved_status.upper() != "CANCELLED"
                ):
                    requested_time = _requested_time(job)
                    declared_indices = status_core.declared_array_indices((job.get("slurm") or {}).get("array"))
                    if declared_indices is None:
                        declared_indices = list(range(1, declared_total + 1))
                    if array_tasks is not None:
                        declared_indices = [index for index in declared_indices if index in array_tasks]
                    for task_index in declared_indices:
                        task_id = f"{job_id_text}_{task_index}"
                        task_status = machine_statuses.get(task_id, resolved_status)
                        status_key = task_status.upper()
                        if status_predicate and not status_predicate(status_key):
                            continue
                        if status_key in {"PENDING", "NOT_SUBMITTED"}:
                            time_remaining = requested_time
                        elif status_key == "RUNNING":
                            if raw_time_left is not None:
                                time_remaining = raw_time_left.get(task_id, machine_remaining.get(job_name, "-"))
                            else:
                                time_remaining = machine_remaining.get(job_name, "-")
                        elif status_key in TERMINAL_STATES:
                            time_remaining = "-"
                        else:
                            time_remaining = "-"
                        rows.append(
                            {
                                "index": str(display_index),
                                "job_id": task_id,
                                "job_id_raw": task_id,
                                "name": job_name,
                                "gpus": _requested_gpus(job),
                                "dependencies": _dependencies_text(job),
                                "time_remaining": time_remaining,
                                "raw_status": task_status,
                                "status_key": status_key,
                                "status": _colorize_state_text(status_core.display_state(task_status)),
                                "machine_name": job.get("machine"),
                                "machine": str(job.get("machine") or "local"),
                            }
                        )
                        display_index += 1
                    continue

            requested_time = _requested_time(job)
            raw_status = resolved_status
            status_key = raw_status.upper()
            if status_predicate and not status_predicate(status_key):
                continue
            if status_key in {"PENDING", "NOT_SUBMITTED"}:
                time_remaining = requested_time
            elif status_key == "RUNNING":
                time_remaining = machine_remaining.get(job_name, "-")
            elif status_key in TERMINAL_STATES:
                time_remaining = "-"
            else:
                time_remaining = "-"

            array_text = f"{array_completed}/{array_total}" if is_array else "-"
            rows.append(
                {
                    "index": str(display_index),
                    "job_id": job_id_text,
                    "job_id_raw": job_id_text,
                    "name": job_name,
                    "array": array_text,
                    "gpus": _requested_gpus(job),
                    "dependencies": _dependencies_text(job),
                    "time_remaining": time_remaining,
                    "raw_status": raw_status,
                    "status_key": status_key,
                    "status": _colorize_state_text(status_core.display_state(raw_status)),
                    "machine_name": job.get("machine"),
                    "machine": str(job.get("machine") or "local"),
                }
            )
            display_index += 1
    return bundle_date, rows


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
    return "\n".join(lines)
