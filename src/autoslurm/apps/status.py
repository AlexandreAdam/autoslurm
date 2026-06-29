from __future__ import annotations

import argparse
import re
from datetime import datetime
from collections import defaultdict
from typing import Optional

from ..status import (
    FAILED_STATES,
    _array_task_index,
    _fetch_statuses_and_time_left_for_job_ids,
    declared_array_size,
    infer_bundle_status,
    job_status_texts as _job_status_texts,
    RUNNING_LIKE_STATES,
    status_for_job_id,
)
from ..status_views import bundle_job_rows_from_jobs, bundle_jobs_context, bundle_jobs_context_from_rows
from ..save_load_jobs import bundle_snapshots, load_bundle

ANSI_RESET = "\033[0m"
ANSI_GREEN = "\033[38;2;0;200;0m"
ANSI_RED = "\033[38;2;220;0;0m"
ANSI_YELLOW = "\033[38;2;220;180;0m"
ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")


DATE_FORMATS = (
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d",
    "%Y%m%d%H%M%S",
    "%Y%m%d",
)


def _parse_date(value: Optional[str]) -> Optional[datetime]:
    if value is None:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "Date must be ISO formatted (e.g. 2023-09-01T12:00:00) or use YYYYMMDDHHMMSS."
        ) from exc


def _build_reference_date(
    date: Optional[str],
    year: Optional[int],
    month: Optional[int],
    day: Optional[int],
    hour: Optional[int],
    minute: Optional[int],
    second: Optional[int],
) -> Optional[datetime]:
    if date is not None:
        return _parse_date(date)

    if any(value is not None for value in (year, month, day, hour, minute, second)):
        now = datetime.now()
        return datetime(
            year=year if year is not None else now.year,
            month=month if month is not None else 1,
            day=day if day is not None else 1,
            hour=hour if hour is not None else 0,
            minute=minute if minute is not None else 0,
            second=second if second is not None else 0,
        )
    return None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Show bundle status summary and inspect a bundle by index."
    )
    parser.add_argument(
        "target",
        nargs="*",
        help="Optional bundle indices/names to inspect. Supports ranges like 1-3.",
    )
    parser.add_argument(
        "--date",
        help="Optional timestamp to target bundles closest to the provided date.",
    )
    parser.add_argument("--year", type=int, help="Reference year, e.g. 2025.")
    parser.add_argument("--month", type=int, help="Reference month, e.g. 1 or 01.")
    parser.add_argument("--day", type=int, help="Reference day of month.")
    parser.add_argument("--hour", type=int, help="Reference hour.")
    parser.add_argument("--minute", type=int, help="Reference minute.")
    parser.add_argument("--second", type=int, help="Reference second.")
    parser.add_argument(
        "--array",
        nargs="*",
        metavar="TASK",
        help="Expand array jobs into per-task rows, optionally filtering by task indices or ranges.",
    )
    return parser


def _parse_array_task_filter(
    tokens: Optional[list[str]], parser: argparse.ArgumentParser
) -> Optional[set[int]]:
    if tokens is None:
        return None
    if not tokens:
        return None

    selected: set[int] = set()
    for token in tokens:
        if token.isdigit():
            selected.add(int(token))
            continue
        if "-" in token:
            left, right = token.split("-", 1)
            if left.isdigit() and right.isdigit():
                start = int(left)
                end = int(right)
                if start > end:
                    parser.error(f"Invalid array range '{token}': start must be <= end.")
                selected.update(range(start, end + 1))
                continue
        parser.error(
            f"Invalid array selector '{token}'. Use integer indices or ranges like 1-3."
        )
    return selected


def _status_rows(reference_date: Optional[datetime]) -> list[dict[str, object]]:
    rows = list(bundle_snapshots(reference_date))
    rows.sort(key=lambda entry: entry["date"], reverse=True)
    return rows


def _status_summary_text(rows: list[dict[str, object]]) -> str:
    if not rows:
        return "No saved bundles found."

    rendered_rows: list[dict[str, str]] = []
    for index, entry in enumerate(rows, start=1):
        bundle_name = str(entry["bundle"])
        saved_date = entry["date"]
        assert isinstance(saved_date, datetime)
        saved_value = saved_date.strftime("%Y-%m-%d %H:%M")

        try:
            jobs, _, _ = load_bundle(bundle_name, saved_date)
            statuses = _job_status_texts(jobs)
            submitted = sum(1 for job in jobs if job.get("id") is not None)
            running = sum(1 for job in jobs if statuses.get(job["name"], "UNKNOWN").upper() == "RUNNING")
            success = sum(1 for job in jobs if statuses.get(job["name"], "UNKNOWN").upper() == "COMPLETED")
            pending = sum(
                1
                for job in jobs
                if statuses.get(job["name"], "UNKNOWN").upper() in {"PENDING", "CONFIGURING"}
            )
            failed = sum(
                1
                for job in jobs
                if statuses.get(job["name"], "UNKNOWN").upper() in FAILED_STATES
                and statuses.get(job["name"], "UNKNOWN").upper() != "CANCELLED"
            )
            job_count = len(jobs)
            bundle_status = infer_bundle_status(
                [statuses.get(job["name"], "UNKNOWN") for job in jobs],
                submitted,
                broken=False,
            )
        except Exception:
            job_count = int(entry.get("job_count", 0))
            submitted = running = success = pending = failed = 0
            bundle_status = infer_bundle_status(
                [],
                submitted,
                broken=str(entry.get("state", "")).lower() == "broken",
            )

        rendered_rows.append(
            {
                "idx": str(index),
                "bundle": bundle_name,
                "status": (
                    f"{ANSI_GREEN}{bundle_status}{ANSI_RESET}"
                    if bundle_status == "completed"
                    else f"{ANSI_YELLOW}{bundle_status}{ANSI_RESET}"
                    if bundle_status == "running"
                    else f"{ANSI_RED}{bundle_status}{ANSI_RESET}"
                    if bundle_status in {"broken", "cancelled", "failed"}
                    else bundle_status
                ),
                "saved": saved_value,
                "jobs": str(job_count),
                "pending": str(pending),
                "running": str(running),
                "success": str(success),
                "failed": str(failed),
            }
        )

    headers = ["idx", "bundle", "status", "saved", "jobs", "pending", "running", "success", "failed"]

    def _visible_len(text: str) -> int:
        return len(ANSI_ESCAPE_RE.sub("", text))

    def _ljust_visible(text: str, width: int) -> str:
        return text + (" " * max(0, width - _visible_len(text)))

    widths = {key: len(key) for key in headers}
    for row in rendered_rows:
        for key in headers:
            widths[key] = max(widths[key], _visible_len(row[key]))

    lines = ["  ".join(key.center(widths[key]) for key in headers)]
    lines.extend("  ".join(_ljust_visible(row[key], widths[key]) for key in headers) for row in rendered_rows)
    return "\n".join(lines)


def _summary_job_metrics(
    job: dict,
    job_status: str,
    machine_statuses: dict[str, str],
) -> tuple[int, int, int, int, int, int]:
    declared_total = declared_array_size((job.get("slurm") or {}).get("array"))
    array_total = declared_total if declared_total is not None else 1
    job_id = job.get("id")
    if job_id is None:
        return array_total, 0, 0, 0, 0, 0

    job_id_text = str(job_id)
    task_states = [
        state.upper()
        for key, state in machine_statuses.items()
        if _array_task_index(job_id_text, key) is not None
    ]
    if task_states:
        running = sum(
            1
            for state in task_states
            if state in {"RUNNING", "COMPLETING", "CONFIGURING", "STAGE_OUT", "RESIZING", "REQUEUED", "SUSPENDED", "SIGNALING"}
        )
        pending = sum(1 for state in task_states if state in {"PENDING"})
        success = sum(1 for state in task_states if state == "COMPLETED")
        failed = sum(1 for state in task_states if state in FAILED_STATES and state != "CANCELLED")
        cancelled = sum(1 for state in task_states if state == "CANCELLED")
        missing = max(0, array_total - len(task_states))
        pending += missing
        return array_total, running, pending, success, failed, cancelled

    upper = job_status.upper()
    if declared_total is not None:
        if upper in RUNNING_LIKE_STATES:
            return array_total, declared_total, 0, 0, 0, 0
        if upper == "PENDING":
            return array_total, 0, declared_total, 0, 0, 0
        if upper == "COMPLETED":
            return array_total, 0, 0, declared_total, 0, 0
        if upper == "CANCELLED":
            return array_total, 0, 0, 0, 0, array_total
        if upper in FAILED_STATES:
            return array_total, 0, 0, 0, 1, 0
        return array_total, 0, 0, 0, 0, 0
    if upper == "RUNNING":
        return array_total, 1, 0, 0, 0, 0
    if upper == "COMPLETED":
        return array_total, 0, 0, 1, 0, 0
    if upper in {"PENDING", "CONFIGURING"}:
        return array_total, 0, 1, 0, 0, 0
    if upper == "CANCELLED":
        return array_total, 0, 0, 0, 0, array_total
    if upper in FAILED_STATES:
        return array_total, 0, 0, 0, 1, 0
    return array_total, 0, 0, 0, 0, 0


def _status_summary_text_batched(rows: list[dict[str, object]]) -> str:
    if not rows:
        return "No saved bundles found."

    bundles: list[tuple[str, datetime, list[dict], str]] = []
    all_jobs: list[dict] = []
    for entry in rows:
        bundle_name = str(entry["bundle"])
        saved_date = entry["date"]
        assert isinstance(saved_date, datetime)
        entry_state = str(entry.get("state", "")).lower()
        try:
            jobs, _, loaded_date = load_bundle(bundle_name, saved_date)
        except Exception:
            bundles.append((bundle_name, saved_date, [], entry_state))
            continue
        bundles.append((bundle_name, loaded_date, jobs, entry_state))
        all_jobs.extend(jobs)

    jobs_by_machine: dict[Optional[str], list[dict]] = defaultdict(list)
    for job in all_jobs:
        jobs_by_machine[job.get("machine")].append(job)

    machine_statuses_by_machine: dict[Optional[str], dict[str, str]] = {}
    for machine_name, machine_jobs in jobs_by_machine.items():
        job_ids = [str(job["id"]) for job in machine_jobs if job.get("id") is not None]
        statuses, _ = _fetch_statuses_and_time_left_for_job_ids(job_ids, machine_name)
        if job_ids:
            machine_statuses_by_machine[machine_name] = statuses

    rendered_rows: list[dict[str, str]] = []
    for index, (bundle_name, saved_date, jobs, entry_state) in enumerate(bundles, start=1):
        saved_value = saved_date.strftime("%Y-%m-%d %H:%M")
        try:
            statuses_by_job_name: dict[str, str] = {}
            submitted = 0
            array_total = 0
            running = 0
            success = 0
            pending = 0
            failed = 0
            cancelled = 0
            for job in jobs:
                job_name = str(job["name"])
                job_id = job.get("id")
                if job_id is None:
                    status = "not_submitted"
                else:
                    machine_name = job.get("machine")
                    machine_statuses = machine_statuses_by_machine.get(machine_name, {})
                    declared_total = declared_array_size((job.get("slurm") or {}).get("array"))
                    status = status_for_job_id(str(job_id), machine_statuses, declared_total=declared_total)
                    submitted += 1
                    job_array_total, job_running, job_pending, job_success, job_failed, job_cancelled = _summary_job_metrics(
                        job,
                        status,
                        machine_statuses,
                    )
                    array_total += job_array_total
                    running += job_running
                    pending += job_pending
                    success += job_success
                    failed += job_failed
                    cancelled += job_cancelled
                    statuses_by_job_name[job_name] = status
                    continue
                statuses_by_job_name[job_name] = status
                job_array_total, job_running, job_pending, job_success, job_failed, job_cancelled = _summary_job_metrics(
                    job,
                    status,
                    {},
                )
                array_total += job_array_total
                running += job_running
                pending += job_pending
                success += job_success
                failed += job_failed
                cancelled += job_cancelled

            job_count = len(jobs)
            status_list = [statuses_by_job_name.get(str(job["name"]), "UNKNOWN") for job in jobs]
            if entry_state == "broken":
                bundle_status = "broken"
            elif any(state.upper() == "CANCELLED" for state in status_list):
                bundle_status = "cancelled"
            else:
                bundle_status = infer_bundle_status(
                    status_list,
                    submitted,
                    broken=False,
                )
        except Exception:
            job_count = int(entry.get("job_count", 0))
            array_total = job_count
            submitted = running = success = pending = failed = cancelled = 0
            bundle_status = infer_bundle_status([], submitted, broken=entry_state == "broken")

        rendered_rows.append(
            {
                "idx": str(index),
                "bundle": bundle_name,
                "status": (
                    f"{ANSI_GREEN}{bundle_status}{ANSI_RESET}"
                    if bundle_status == "completed"
                    else f"{ANSI_YELLOW}{bundle_status}{ANSI_RESET}"
                    if bundle_status == "running"
                    else f"{ANSI_RED}{bundle_status}{ANSI_RESET}"
                    if bundle_status in {"broken", "cancelled", "failed"}
                    else bundle_status
                ),
                "saved": saved_value,
                "jobs": str(job_count),
                "array": str(array_total),
                "pending": str(pending),
                "running": str(running),
                "success": str(success),
                "failed": str(failed),
                "cancelled": str(cancelled),
            }
        )

    headers = [
        "idx",
        "bundle",
        "status",
        "saved",
        "jobs",
        "array",
        "pending",
        "running",
        "success",
        "failed",
        "cancelled",
    ]

    def _visible_len(text: str) -> int:
        return len(ANSI_ESCAPE_RE.sub("", text))

    def _ljust_visible(text: str, width: int) -> str:
        return text + (" " * max(0, width - _visible_len(text)))

    widths = {key: len(key) for key in headers}
    for row in rendered_rows:
        for key in headers:
            widths[key] = max(widths[key], _visible_len(row[key]))

    lines = ["  ".join(key.center(widths[key]) for key in headers)]
    lines.extend("  ".join(_ljust_visible(row[key], widths[key]) for key in headers) for row in rendered_rows)
    return "\n".join(lines)


def _resolve_targets(
    tokens: list[str], rows: list[dict[str, object]], parser: argparse.ArgumentParser
) -> list[tuple[str, Optional[datetime]]]:
    if not tokens:
        return []
    if len(tokens) == 1 and not any(ch in tokens[0] for ch in ("-", ",")) and not tokens[0].isdigit():
        return [(tokens[0], None)]

    resolved: list[tuple[str, Optional[datetime]]] = []
    for token in tokens:
        if token.isdigit():
            index = int(token)
            if index < 1 or index > len(rows):
                parser.error(f"Bundle index '{token}' is out of range.")
            row = rows[index - 1]
            resolved.append((str(row["bundle"]), row["date"]))
            continue
        if "-" in token:
            left, right = token.split("-", 1)
            if left.isdigit() and right.isdigit():
                start, end = int(left), int(right)
                if start > end:
                    parser.error(f"Invalid range '{token}': start must be <= end.")
                for index in range(start, end + 1):
                    if index < 1 or index > len(rows):
                        parser.error(f"Bundle index '{index}' from range '{token}' is out of range.")
                    row = rows[index - 1]
                    resolved.append((str(row["bundle"]), row["date"]))
                continue
        resolved.append((token, None))
    return resolved


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    reference_date = _build_reference_date(
        args.date,
        args.year,
        args.month,
        args.day,
        args.hour,
        args.minute,
        args.second,
    )
    rows = _status_rows(reference_date)
    array_tasks = _parse_array_task_filter(args.array, parser)

    if not args.target:
        if args.array is not None:
            parser.error("--array requires a bundle target.")
        print(_status_summary_text_batched(rows))
        return

    targets = _resolve_targets(args.target, rows, parser)
    detailed_targets: list[tuple[str, datetime, list[dict]]] = []
    all_jobs: list[dict] = []
    for bundle_name, bundle_date in targets:
        detail_date = reference_date if bundle_date is None else bundle_date
        jobs, _, loaded_date = load_bundle(bundle_name, detail_date)
        detailed_targets.append((bundle_name, loaded_date, jobs))
        all_jobs.extend(jobs)

    machine_statuses_by_machine: dict[Optional[str], dict[str, str]] = {}
    machine_time_left_by_machine: dict[Optional[str], dict[str, str]] = {}
    jobs_by_machine: dict[Optional[str], list[dict]] = defaultdict(list)
    for job in all_jobs:
        jobs_by_machine[job.get("machine")].append(job)
    for machine_name, machine_jobs in jobs_by_machine.items():
        job_ids = [str(job["id"]) for job in machine_jobs if job.get("id") is not None]
        statuses, time_left = _fetch_statuses_and_time_left_for_job_ids(job_ids, machine_name)
        if job_ids:
            machine_statuses_by_machine[machine_name] = statuses
            machine_time_left_by_machine[machine_name] = time_left

    sections: list[str] = []
    for bundle_name, bundle_date, jobs in detailed_targets:
        _, rows = bundle_job_rows_from_jobs(
            jobs,
            bundle_date,
            show_array_tasks=args.array is not None,
            array_tasks=array_tasks,
            machine_statuses_by_machine=machine_statuses_by_machine,
            machine_time_left_by_machine=machine_time_left_by_machine,
        )
        sections.append(f"Bundle: {bundle_name}")
        sections.append(
            bundle_jobs_context_from_rows(
                bundle_name,
                bundle_date,
                rows,
                show_array_tasks=args.array is not None,
            )
        )
    print("\n\n".join(sections))
