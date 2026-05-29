from __future__ import annotations

import argparse
import re
from datetime import datetime
from typing import Optional

from ..status import FAILED_STATES, job_status_texts as _job_status_texts
from ..status_views import bundle_jobs_context
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
    return parser


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
            )
            job_count = len(jobs)
            queue_like = sum(
                1
                for job in jobs
                if statuses.get(job["name"], "UNKNOWN").upper() in {"RUNNING", "PENDING", "CONFIGURING"}
            )
            bundle_status = "running" if queue_like > 0 else ("completed" if submitted > 0 else "ready_to_go")
        except Exception:
            job_count = int(entry.get("job_count", 0))
            submitted = running = success = pending = failed = 0
            bundle_status = "broken" if str(entry.get("state", "")).lower() == "broken" else "ready_to_go"

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
                    if bundle_status == "broken"
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


def _bundle_detail_text(bundle_name: str, reference_date: Optional[datetime]) -> str:
    text = bundle_jobs_context(bundle_name, reference_date)
    lines = text.splitlines()
    filtered = [
        line
        for line in lines
        if line.strip() != "Use --job <number|name> to inspect a job."
    ]
    if filtered:
        return "\n".join(filtered)
    return text


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

    if not args.target:
        print(_status_summary_text(rows))
        return

    targets = _resolve_targets(args.target, rows, parser)
    sections: list[str] = []
    for bundle_name, bundle_date in targets:
        detail_date = reference_date if bundle_date is None else bundle_date
        sections.append(f"Bundle: {bundle_name}")
        sections.append(_bundle_detail_text(bundle_name, detail_date))
    print("\n\n".join(sections))
