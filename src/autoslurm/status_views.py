from __future__ import annotations

import re
from datetime import datetime
from typing import Callable, Optional

from .save_load_jobs import load_bundle
from . import status as status_core


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
) -> tuple[datetime, list[dict]]:
    jobs, _, bundle_date = load_bundle(bundle_name, desired_date)
    statuses = status_core.job_status_texts(jobs)
    remaining = status_core._job_remaining_times(jobs, statuses)
    compiled_regex = None
    if name_regex:
        flags = re.IGNORECASE if ignore_case else 0
        compiled_regex = re.compile(name_regex, flags=flags)

    rows: list[dict] = []
    for index, job in enumerate(jobs, start=1):
        job_name = str(job["name"])
        raw_status = statuses.get(job_name)
        if raw_status is None:
            raw_status = status_core.job_status_text(job)
        status_key = raw_status.upper()
        if status_predicate and not status_predicate(status_key):
            continue
        if name_contains:
            haystack = job_name.lower() if ignore_case else job_name
            needle = name_contains.lower() if ignore_case else name_contains
            if needle not in haystack:
                continue
        if compiled_regex and not compiled_regex.search(job_name):
            continue
        job_id = job.get("id")
        rows.append(
            {
                "index": str(index),
                "job_id": str(job_id) if job_id is not None else "-",
                "job_id_raw": None if job_id is None else str(job_id),
                "name": job_name,
                "time": _requested_time(job),
                "gpus": _requested_gpus(job),
                "dependencies": _dependencies_text(job),
                "remaining": remaining.get(job_name, "-"),
                "raw_status": raw_status,
                "status_key": status_key,
                "status": _colorize_state_text(status_core.display_state(raw_status)),
                "machine_name": job.get("machine"),
                "machine": str(job.get("machine") or "local"),
            }
        )
    return bundle_date, rows


def bundle_jobs_context(
    bundle_name: str,
    desired_date: Optional[datetime] = None,
    *,
    name_contains: Optional[str] = None,
    name_regex: Optional[str] = None,
    ignore_case: bool = False,
    status_predicate: Optional[Callable[[str], bool]] = None,
) -> str:
    bundle_date, rows = bundle_job_rows(
        bundle_name,
        desired_date,
        name_contains=name_contains,
        name_regex=name_regex,
        ignore_case=ignore_case,
        status_predicate=status_predicate,
    )
    lines = [f"{bundle_name} {bundle_date.isoformat()}"]
    if not rows:
        lines.append("No jobs matched filters.")
        return "\n".join(lines)

    idx_width = max(len("idx"), max(len(row["index"]) for row in rows))
    id_width = max(len("id"), max(len(row["job_id"]) for row in rows))
    name_width = max(len("name"), max(len(row["name"]) for row in rows))
    time_width = max(len("time"), max(len(row["time"]) for row in rows))
    gpus_width = max(len("gpus"), max(len(row["gpus"]) for row in rows))
    deps_width = max(len("dependencies"), max(len(row["dependencies"]) for row in rows))
    remaining_width = max(len("remaining"), max(len(row["remaining"]) for row in rows))
    status_width = max(len("status"), max(status_core._visible_len(row["status"]) for row in rows))
    lines.append(
        f"{'idx'.center(idx_width)}  "
        f"{'id'.center(id_width)}  "
        f"{'name'.center(name_width)}  "
        f"{'time'.center(time_width)}  "
        f"{'gpus'.center(gpus_width)}  "
        f"{'dependencies'.center(deps_width)}  "
        f"{'remaining'.center(remaining_width)}  "
        f"{'status'.center(status_width)}"
    )
    for row in rows:
        deps_rendered = (
            row["dependencies"].center(deps_width)
            if row["dependencies"] == "-"
            else row["dependencies"].ljust(deps_width)
        )
        remaining_rendered = (
            row["remaining"].center(remaining_width)
            if row["remaining"] == "-"
            else row["remaining"].ljust(remaining_width)
        )
        row_text = (
            f"{row['index'].ljust(idx_width)}  "
            f"{row['job_id'].ljust(id_width)}  "
            f"{row['name'].ljust(name_width)}  "
            f"{row['time'].ljust(time_width)}  "
            f"{row['gpus'].ljust(gpus_width)}  "
            f"{deps_rendered}  "
            f"{remaining_rendered}  "
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
