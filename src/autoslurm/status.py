from __future__ import annotations

import json
import re
import shlex
import subprocess
from collections import defaultdict
from datetime import datetime
from typing import Optional

from .array_status import array_progress_for_job_id, declared_array_size, status_for_job_id
from .save_load_jobs import latest_bundle_summaries, load_bundle
from .utils import load_config, ssh_host_from_config

FAILED_STATES = {
    "FAILED",
    "CANCELLED",
    "TIMEOUT",
    "NODE_FAIL",
    "OUT_OF_MEMORY",
    "PREEMPTED",
    "BOOT_FAIL",
    "DEADLINE",
    "REVOKED",
}
CANCELLABLE_STATES = {
    "PENDING",
    "RUNNING",
    "CONFIGURING",
    "COMPLETING",
    "STAGE_OUT",
    "RESIZING",
    "REQUEUED",
    "SUSPENDED",
    "SIGNALING",
}
ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")

ANSI_RESET = "\033[0m"
# Use 24-bit color escapes to avoid terminal theme remapping of base ANSI palette.
ANSI_GREEN = "\033[38;2;0;200;0m"
ANSI_RED = "\033[38;2;220;0;0m"
ANSI_YELLOW = "\033[38;2;220;180;0m"


def display_state(state: str) -> str:
    if state.upper() == "COMPLETED":
        return "SUCCESS"
    return state


def _colorize_state_text(state_text: str) -> str:
    upper = state_text.upper()
    if upper == "SUCCESS":
        return f"{ANSI_GREEN}{state_text}{ANSI_RESET}"
    if upper == "RUNNING":
        return f"{ANSI_YELLOW}{state_text}{ANSI_RESET}"
    if upper == "CANCELLED" or upper in FAILED_STATES:
        return f"{ANSI_RED}{state_text}{ANSI_RESET}"
    return state_text


def is_cancellable_state(state: str) -> bool:
    return (state or "UNKNOWN").upper() in CANCELLABLE_STATES


def _visible_len(text: str) -> int:
    return len(ANSI_ESCAPE_RE.sub("", text))


def _ljust_visible(text: str, width: int) -> str:
    return text + (" " * max(0, width - _visible_len(text)))


def _center_visible(text: str, width: int) -> str:
    pad = max(0, width - _visible_len(text))
    left = pad // 2
    right = pad - left
    return (" " * left) + text + (" " * right)


def _parse_status_lines(text: str) -> dict[str, str]:
    statuses: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or "|" not in line:
            continue
        job_id, state = line.split("|", 1)
        job_id = job_id.strip()
        state = state.strip()
        if not job_id or not state:
            continue
        statuses[job_id] = state.split()[0]
    return statuses


def _parse_job_field_lines(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or "|" not in line:
            continue
        job_id, value = line.split("|", 1)
        job_id = job_id.strip()
        value = value.strip()
        if not job_id or not value:
            continue
        values[job_id] = value
    return values


def _fetch_statuses_locally(job_ids: list[str]) -> dict[str, str]:
    if not job_ids:
        return {}
    query = ",".join(job_ids)
    statuses: dict[str, str] = {}
    commands = (
        ["squeue", "-h", "-j", query, "-o", "%i|%T"],
        ["sacct", "-n", "-X", "-P", "-j", query, "-o", "JobIDRaw,State"],
    )
    for command in commands:
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            continue
        statuses.update(_parse_status_lines(result.stdout or result.stderr or ""))
    return statuses


def _fetch_statuses_remotely(
    job_ids: list[str], machine_name: str, machine_config: dict
) -> dict[str, str]:
    if not job_ids:
        return {}
    query = ",".join(job_ids)
    try:
        hostname = ssh_host_from_config(machine_config, machine_name)
    except AttributeError:
        return {}
    remote_script = "\n".join(
        [
            f"squeue -h -j {shlex.quote(query)} -o '%i|%T' 2>/dev/null || true",
            "printf '__AUTOSLURM_SPLIT__\\n'",
            f"sacct -n -X -P -j {shlex.quote(query)} -o JobIDRaw,State 2>/dev/null || true",
        ]
    )
    result = subprocess.run(
        ["ssh", *shlex.split(hostname), f"bash -lc {shlex.quote(remote_script)}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return {}
    status_lines = (result.stdout or result.stderr or "").split("__AUTOSLURM_SPLIT__")
    statuses: dict[str, str] = {}
    for text in status_lines:
        statuses.update(_parse_status_lines(text))
    return statuses


def _fetch_statuses_for_job_ids(
    job_ids: list[str], machine_name: Optional[str]
) -> dict[str, str]:
    if not job_ids:
        return {}
    if machine_name is None:
        return _fetch_statuses_locally(job_ids)
    try:
        config = load_config()
    except EnvironmentError:
        return {}
    machine_config = config["machines"].get(machine_name) or config.get(machine_name)
    if machine_config is None:
        return {}
    return _fetch_statuses_remotely(job_ids, machine_name, machine_config)


def _fetch_time_left_locally(job_ids: list[str]) -> dict[str, str]:
    if not job_ids:
        return {}
    query = ",".join(job_ids)
    result = subprocess.run(
        ["squeue", "-h", "-j", query, "-o", "%i|%L"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return {}
    return _parse_job_field_lines(result.stdout or result.stderr or "")


def _fetch_time_left_remotely(
    job_ids: list[str], machine_name: str, machine_config: dict
) -> dict[str, str]:
    if not job_ids:
        return {}
    query = ",".join(job_ids)
    try:
        hostname = ssh_host_from_config(machine_config, machine_name)
    except AttributeError:
        return {}
    remote_script = f"squeue -h -j {shlex.quote(query)} -o '%i|%L' 2>/dev/null || true"
    result = subprocess.run(
        ["ssh", *shlex.split(hostname), f"bash -lc {shlex.quote(remote_script)}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return {}
    return _parse_job_field_lines(result.stdout or result.stderr or "")


def _fetch_time_left_for_job_ids(
    job_ids: list[str], machine_name: Optional[str]
) -> dict[str, str]:
    if not job_ids:
        return {}
    if machine_name is None:
        return _fetch_time_left_locally(job_ids)
    try:
        config = load_config()
    except EnvironmentError:
        return {}
    machine_config = config["machines"].get(machine_name) or config.get(machine_name)
    if machine_config is None:
        return {}
    return _fetch_time_left_remotely(job_ids, machine_name, machine_config)


def job_status_text(job: dict) -> str:
    job_id = job.get("id")
    if job_id is None:
        return "not_submitted"
    job_id_text = str(job_id)
    statuses = _fetch_statuses_for_job_ids([job_id_text], job.get("machine"))
    return status_for_job_id(job_id_text, statuses)


def job_status_texts(jobs: list[dict]) -> dict[str, str]:
    statuses: dict[str, str] = {}
    by_machine: dict[Optional[str], list[dict]] = defaultdict(list)
    for job in jobs:
        by_machine[job.get("machine")].append(job)

    for machine_name, machine_jobs in by_machine.items():
        job_ids = [str(job["id"]) for job in machine_jobs if job.get("id") is not None]
        machine_statuses = _fetch_statuses_for_job_ids(job_ids, machine_name)
        for job in machine_jobs:
            job_id = job.get("id")
            if job_id is None:
                statuses[job["name"]] = "not_submitted"
            else:
                job_id_text = str(job_id)
                statuses[job["name"]] = status_for_job_id(job_id_text, machine_statuses)
    return statuses


def job_status_details(jobs: list[dict]) -> dict[str, dict[str, object]]:
    details: dict[str, dict[str, object]] = {}
    by_machine: dict[Optional[str], list[dict]] = defaultdict(list)
    for job in jobs:
        by_machine[job.get("machine")].append(job)

    for machine_name, machine_jobs in by_machine.items():
        job_ids = [str(job["id"]) for job in machine_jobs if job.get("id") is not None]
        machine_statuses = _fetch_statuses_for_job_ids(job_ids, machine_name)
        for job in machine_jobs:
            job_name = str(job["name"])
            job_id = job.get("id")
            if job_id is None:
                declared_total = declared_array_size((job.get("slurm") or {}).get("array"))
                details[job_name] = {
                    "status": "not_submitted",
                    "is_array": declared_total is not None,
                    "array_completed": 0,
                    "array_total": 0 if declared_total is None else declared_total,
                }
                continue
            job_id_text = str(job_id)
            resolved_status = status_for_job_id(job_id_text, machine_statuses)
            is_array, array_completed, array_total = array_progress_for_job_id(job_id_text, machine_statuses)
            declared_total = declared_array_size((job.get("slurm") or {}).get("array"))
            if declared_total is not None:
                is_array = True
                array_total = declared_total
                if resolved_status.upper() == "COMPLETED":
                    array_completed = declared_total
                elif resolved_status.upper() in {"PENDING", "NOT_SUBMITTED"}:
                    array_completed = 0
                else:
                    array_completed = min(array_completed, declared_total)
            details[job_name] = {
                "status": resolved_status,
                "is_array": is_array,
                "array_completed": array_completed,
                "array_total": array_total,
            }
    return details


def _job_remaining_times(jobs: list[dict], statuses: dict[str, str]) -> dict[str, str]:
    def _resolve_job_value(job_id: str, values: dict[str, str]) -> Optional[str]:
        exact = values.get(job_id)
        if exact is not None:
            return exact
        # Slurm can emit array/step-style identifiers (e.g., 12345_7 or 12345.batch).
        prefix_underscore = f"{job_id}_"
        prefix_dot = f"{job_id}."
        for key, value in values.items():
            if key.startswith(prefix_underscore) or key.startswith(prefix_dot):
                return value
        return None

    remaining: dict[str, str] = {job["name"]: "-" for job in jobs}
    by_machine: dict[Optional[str], list[dict]] = defaultdict(list)
    for job in jobs:
        by_machine[job.get("machine")].append(job)

    for machine_name, machine_jobs in by_machine.items():
        running = [
            job
            for job in machine_jobs
            if job.get("id") is not None and statuses.get(job["name"], "UNKNOWN").upper() == "RUNNING"
        ]
        if not running:
            continue
        job_ids = [str(job["id"]) for job in running]
        left = _fetch_time_left_for_job_ids(job_ids, machine_name)
        for job in running:
            resolved = _resolve_job_value(str(job["id"]), left)
            remaining[job["name"]] = resolved if resolved is not None else "UNKNOWN"
    return remaining


def _bundle_summary_lines(desired_date: Optional[datetime] = None) -> list[str]:
    summaries = latest_bundle_summaries(desired_date=desired_date)
    if not summaries:
        return ["No saved bundles found."]
    rows: list[dict[str, str]] = []
    for entry in summaries:
        bundle_name = entry["bundle"]
        saved_value = entry["date"].strftime("%Y-%m-%d %H:%M")

        try:
            jobs, _, _ = load_bundle(bundle_name, entry["date"])
        except (FileNotFoundError, OSError, ValueError, KeyError, json.JSONDecodeError):
            job_count = entry.get("job_count", 0)
            row = {
                "bundle": bundle_name,
                "saved": saved_value,
                "jobs": str(job_count),
                "submitted": "-",
                "running": "-",
                "success": "-",
                "pending": "-",
                "failed": "-",
            }
            rows.append(row)
            continue

        statuses = job_status_texts(jobs)
        submitted = sum(1 for job in jobs if job.get("id") is not None)
        running = 0
        success = 0
        pending = 0
        failed = 0
        for job in jobs:
            state = statuses.get(job["name"], "UNKNOWN").upper()
            if state == "COMPLETED":
                success += 1
            elif state == "RUNNING":
                running += 1
            elif state in {"PENDING", "CONFIGURING"}:
                pending += 1
            elif state in FAILED_STATES:
                failed += 1

        row = {
            "bundle": bundle_name,
            "saved": saved_value,
            "jobs": str(len(jobs)),
            "submitted": str(submitted),
            "running": str(running),
            "success": str(success),
            "pending": str(pending),
            "failed": str(failed),
        }
        rows.append(row)

    headers = ["bundle", "saved", "jobs", "submitted", "running", "success", "pending", "failed"]
    widths = {key: max(len(key), max(len(row[key]) for row in rows)) for key in headers}
    header = "  ".join(key.center(widths[key]) for key in headers)
    lines = [header]
    for row in rows:
        lines.append("  ".join(row[key].ljust(widths[key]) for key in headers))
    return lines


def bundle_index_context(desired_date: Optional[datetime] = None) -> str:
    return "\n".join(_bundle_summary_lines(desired_date=desired_date))


def bundle_jobs_context(
    bundle_name: str,
    desired_date: Optional[datetime] = None,
    *,
    name_contains: Optional[str] = None,
    name_regex: Optional[str] = None,
    ignore_case: bool = False,
    status_predicate=None,
) -> str:
    from .status_views import bundle_jobs_context as _bundle_jobs_context

    return _bundle_jobs_context(
        bundle_name,
        desired_date,
        name_contains=name_contains,
        name_regex=name_regex,
        ignore_case=ignore_case,
        status_predicate=status_predicate,
    )


def latest_bundle_status_context(desired_date: Optional[datetime] = None) -> str:
    summaries = latest_bundle_summaries(desired_date=desired_date)
    if not summaries:
        return "No saved bundles found."
    bundle_name = summaries[0]["bundle"]
    return bundle_jobs_context(bundle_name, desired_date)
