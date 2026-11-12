from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from .array_status import FAILED_STATES
from .save_load_jobs import latest_bundle_summaries
from .utils import load_config

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
    return state


def _colorize_state_text(state_text: str) -> str:
    upper = state_text.upper()
    if upper == "COMPLETED":
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
    from .scheduler import _parse
    return {identity: record["state"] for identity, record in _parse(text, "queue").items()}


def _query_compat(job_ids, machine_name=None, machine_config=None):
    from .scheduler import query_scheduler
    if machine_config is None and machine_name is not None:
        try:
            machine_config = load_config()["machines"][machine_name]
        except (EnvironmentError, KeyError):
            return {}, {}
    observed = query_scheduler(job_ids, machine_config, machine_name)
    return ({key: value["state"] for key, value in observed["records"].items()},
            {key: value["time_remaining"] for key, value in observed["records"].items() if value.get("time_remaining")})


def _fetch_statuses_locally(job_ids):
    return _query_compat(job_ids)[0]


def _fetch_statuses_remotely(job_ids, machine_name, machine_config):
    return _query_compat(job_ids, machine_name, machine_config)[0]


def _fetch_statuses_for_job_ids(job_ids, machine_name):
    return _query_compat(job_ids, machine_name)[0]


def _fetch_time_left_for_job_ids(job_ids, machine_name):
    return _query_compat(job_ids, machine_name)[1]


def _fetch_statuses_and_time_left_for_job_ids(job_ids, machine_name):
    return _query_compat(job_ids, machine_name)


def job_status_text(job):
    return job_status_texts([job])[job["name"]]


def job_status_texts(jobs):
    from .inspection import observe_job_statuses
    return {job["name"]: job["state"].lower() if job["id"] is None else job["state"] for job in observe_job_statuses(jobs)}


def job_status_details(jobs):
    from .inspection import observe_job_statuses
    return {job["name"]: {"status": job["state"], "is_array": job["is_array"],
                         "array_completed": job["counts"]["completed"],
                         "array_total": len(job["tasks"]) if job["is_array"] else 0,
                         "errors": job["errors"], "observed_at": job["observed_at"]} for job in observe_job_statuses(jobs)}


def bundle_index_context(desired_date=None):
    from .inspection import inspect_bundles
    from .save_load_jobs import bundle_snapshots
    from .status_views import summary_text
    entries = bundle_snapshots(desired_date)
    return summary_text(entries, inspect_bundles([entry["path"] for entry in entries]))


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
