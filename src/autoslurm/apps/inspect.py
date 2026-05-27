from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..experiment_context import job_context, latest_log_context
from ..save_load_jobs import bundle_snapshots, latest_bundle_summaries, load_bundle
from ..status_views import bundle_jobs_context
from ..storage import out_dir
from ..sync import sync_machine


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


def _copy_to_clipboard(text: str) -> None:
    if shutil.which("pbcopy") is not None:
        subprocess.run(["pbcopy"], input=text, text=True, check=True)
        return
    if shutil.which("wl-copy") is not None:
        subprocess.run(["wl-copy"], input=text, text=True, check=True)
        return
    if shutil.which("xclip") is not None:
        subprocess.run(["xclip", "-selection", "clipboard"], input=text, text=True, check=True)
        return
    if shutil.which("xsel") is not None:
        subprocess.run(["xsel", "--clipboard", "--input"], input=text, text=True, check=True)
        return
    raise RuntimeError(
        "No clipboard utility found. Install pbcopy, wl-copy, xclip, or xsel to use --clipboard."
    )


def _emit(text: str, copy_to_clipboard: bool = False) -> None:
    print(text)
    if copy_to_clipboard:
        _copy_to_clipboard(text)


def _resolve_job_selector(bundle_name: str, selector: str, reference_date: Optional[datetime]) -> str:
    jobs, _, _ = load_bundle(bundle_name, reference_date)
    if selector.isdigit():
        index = int(selector)
        if 1 <= index <= len(jobs):
            return jobs[index - 1]["name"]
        raise KeyError(f"Job index '{selector}' is out of range.")
    job = next((item for item in jobs if item["name"] == selector), None)
    if job is None:
        raise KeyError(f"Job '{selector}' not found.")
    return job["name"]


def _resolve_bundle_target(
    bundle_arg: Optional[str], latest: bool, reference_date: Optional[datetime]
) -> str:
    rows = list(bundle_snapshots(reference_date))
    rows.sort(key=lambda entry: entry["date"], reverse=True)

    if latest:
        if not rows:
            raise LookupError("No saved bundles found.")
        return rows[0]["bundle"]

    assert bundle_arg is not None
    if bundle_arg.isdigit():
        if not rows:
            raise LookupError("No saved bundles found.")
        index = int(bundle_arg)
        if index < 1 or index > len(rows):
            raise KeyError(f"Bundle index '{bundle_arg}' is out of range.")
        return rows[index - 1]["bundle"]
    return bundle_arg


def _strip_status_instruction(text: str) -> str:
    lines = text.splitlines()
    filtered = [line for line in lines if line.strip() != "Use --job <number|name> to inspect a job."]
    return "\n".join(filtered) if filtered else text


def _tail_text(text: str, lines: int) -> str:
    parts = text.splitlines()
    return "\n".join(parts[-lines:]) if parts else text


def _list_job_log_files(bundle_name: str, job_selector: str, reference_date: Optional[datetime]) -> str:
    job_name = _resolve_job_selector(bundle_name, job_selector, reference_date)
    files = sorted(out_dir().glob(f"{job_name}-*.out"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not files:
        return f"No local log files found for job '{job_name}'. Try `asl sync` or `asl logs --refresh`."
    return "\n".join(str(path) for path in files)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect job output logs.")
    parser.add_argument("bundle", nargs="*", help="Bundle name/index to inspect. Supports ranges like 1-3.")
    parser.add_argument("--latest", "-l", action="store_true", help="Use the latest saved bundle.")
    parser.add_argument("--job", help="Select a job by index or name.")
    parser.add_argument("--script", action="store_true", help="Print the rendered SLURM script for --job.")
    parser.add_argument("--log", action="store_true", help="Print latest .out content (bundle or selected job).")
    parser.add_argument("--tail", type=int, help="Print only the last N lines of the selected log output.")
    parser.add_argument("--list-files", action="store_true", help="List local .out files for the selected job.")
    parser.add_argument("--refresh", action="store_true", help="Sync the configured default machine before reading logs.")
    parser.add_argument("--clipboard", "--clip", action="store_true", help="Copy output to clipboard.")
    parser.add_argument("--date", help="Optional timestamp to target the bundle closest to the provided date.")
    parser.add_argument("--year", type=int, help="Reference year, e.g. 2025.")
    parser.add_argument("--month", type=int, help="Reference month, e.g. 1 or 01.")
    parser.add_argument("--day", type=int, help="Reference day of month.")
    parser.add_argument("--hour", type=int, help="Reference hour.")
    parser.add_argument("--minute", type=int, help="Reference minute.")
    parser.add_argument("--second", type=int, help="Reference second.")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else list(argv)
    parser = _build_parser()
    if not args:
        parser.print_help()
        return
    parsed = parser.parse_args(args)

    if parsed.latest and parsed.bundle:
        parser.error("Specify either a bundle name or --latest, not both.")
    if not parsed.latest and not parsed.bundle:
        parser.error("Provide a bundle name or --latest.")
    if parsed.tail is not None and parsed.tail <= 0:
        parser.error("--tail must be a positive integer.")
    if parsed.list_files and not parsed.job:
        parser.error("--list-files requires --job.")
    if parsed.script and not parsed.job:
        parser.error("--script requires --job.")
    if len(parsed.bundle) > 1 and any((parsed.job, parsed.script, parsed.list_files, parsed.log, parsed.tail is not None)):
        parser.error("Multi-bundle selection only supports status-style output (no --job/--script/--log/--tail/--list-files).")

    reference_date = _build_reference_date(
        parsed.date,
        parsed.year,
        parsed.month,
        parsed.day,
        parsed.hour,
        parsed.minute,
        parsed.second,
    )

    if parsed.refresh:
        sync_machine()

    rows = list(bundle_snapshots(reference_date))
    rows.sort(key=lambda entry: entry["date"], reverse=True)
    try:
        if parsed.latest:
            if not rows:
                raise LookupError("No saved bundles found.")
            targets: list[tuple[str, Optional[datetime]]] = [(str(rows[0]["bundle"]), rows[0]["date"])]
        else:
            targets = []
            for token in parsed.bundle:
                if token.isdigit():
                    index = int(token)
                    if index < 1 or index > len(rows):
                        raise KeyError(f"Bundle index '{token}' is out of range.")
                    row = rows[index - 1]
                    targets.append((str(row["bundle"]), row["date"]))
                    continue
                if "-" in token:
                    left, right = token.split("-", 1)
                    if left.isdigit() and right.isdigit():
                        start, end = int(left), int(right)
                        if start > end:
                            raise KeyError(f"Invalid range '{token}': start must be <= end.")
                        for index in range(start, end + 1):
                            if index < 1 or index > len(rows):
                                raise KeyError(f"Bundle index '{index}' from range '{token}' is out of range.")
                            row = rows[index - 1]
                            targets.append((str(row["bundle"]), row["date"]))
                        continue
                targets.append((token, reference_date))
    except LookupError as exc:
        _emit(str(exc), parsed.clipboard)
        return
    except KeyError as exc:
        parser.error(str(exc))

    if parsed.list_files:
        bundle_name, bundle_date = targets[0]
        _emit(_list_job_log_files(bundle_name, parsed.job, bundle_date), parsed.clipboard)
        return

    if parsed.script:
        bundle_name, bundle_date = targets[0]
        _emit(
            job_context(
                bundle_name,
                parsed.job,
                bundle_date,
                include_script=True,
                include_logs=False,
                include_status=False,
            ),
            parsed.clipboard,
        )
        return

    wants_log_output = parsed.log or parsed.job is not None or parsed.tail is not None
    if not wants_log_output:
        sections: list[str] = []
        for bundle_name, bundle_date in targets:
            status_text = bundle_jobs_context(bundle_name, bundle_date)
            sections.append(f"Bundle: {bundle_name}")
            sections.append(_strip_status_instruction(status_text))
        _emit("\n\n".join(sections), parsed.clipboard)
        return

    bundle_name, bundle_date = targets[0]
    content = latest_log_context(bundle_name, bundle_date, parsed.job)
    if parsed.tail is not None:
        content = _tail_text(content, parsed.tail)
    _emit(content, parsed.clipboard)
