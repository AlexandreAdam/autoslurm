from __future__ import annotations

import argparse
import re
import shlex
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..save_load_jobs import bundle_snapshots, load_bundle, load_bundle_from_path
from ..status import is_cancellable_state, job_status_texts
from ..status_views import bundle_job_rows, bundle_jobs_context
from ..utils import load_config, ssh_host_from_config

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


def _resolve_bundle_name(target: str, reference_date: Optional[datetime]) -> tuple[str, datetime]:
    rows = list(bundle_snapshots(reference_date))
    if target.isdigit():
        idx = int(target)
        if idx < 1 or idx > len(rows):
            raise SystemExit(f"Bundle index '{target}' is out of range.")
        row = rows[idx - 1]
        return str(row["bundle"]), row["date"]
    if not rows:
        raise SystemExit("No saved bundles found.")
    jobs, _, saved_date = load_bundle(target, reference_date)
    if jobs is None:  # pragma: no cover
        raise SystemExit(f"Could not load bundle '{target}'.")
    return target, saved_date


def _state_matches(status: str, status_filter: str) -> bool:
    state = (status or "UNKNOWN").upper()
    if status_filter == "all":
        return is_cancellable_state(state)
    if status_filter == "submitted":
        return state not in {"NOT_SUBMITTED"}
    if status_filter == "pending":
        return state in {"PENDING", "CONFIGURING"}
    if status_filter == "running":
        return state == "RUNNING"
    return False


def _cancel_local(job_ids: list[str]) -> None:
    if not job_ids:
        return
    command = ["scancel", *job_ids]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"Local cancel failed: {message}")


def _cancel_remote(machine_name: str, machine_cfg: dict, job_ids: list[str]) -> None:
    if not job_ids:
        return
    hostname = ssh_host_from_config(machine_cfg, machine_name)
    payload = "scancel " + " ".join(shlex.quote(job_id) for job_id in job_ids)
    result = subprocess.run(
        ["ssh", *shlex.split(hostname), f"bash -lc {shlex.quote(payload)}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"Remote cancel failed on '{machine_name}': {message}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Preview and cancel jobs in a saved AutoSlurm bundle. "
            "Default is preview-only; pass --yes to execute cancellation."
        )
    )
    parser.add_argument(
        "target",
        nargs="?",
        help="Bundle name or bundle index (1-based from `autoslurm status`).",
    )
    parser.add_argument(
        "--bundle-file",
        type=Path,
        help="Explicit path to a bundle JSON file (bypasses bundle name lookup).",
    )
    parser.add_argument(
        "--date",
        help="Optional reference date for selecting bundle snapshot.",
    )
    parser.add_argument(
        "--status-filter",
        choices=("all", "submitted", "pending", "running"),
        default="all",
        help=(
            "Which jobs are eligible for cancellation. "
            "'all' means in-flight states only; "
            "'submitted' means all submitted jobs with an ID. Default: all."
        ),
    )
    parser.add_argument(
        "--name-contains",
        help="Only include jobs whose name contains this substring.",
    )
    parser.add_argument(
        "--name-regex",
        help="Only include jobs whose name matches this regex pattern.",
    )
    parser.add_argument(
        "--ignore-case",
        action="store_true",
        help="Apply --name-contains/--name-regex with case-insensitive matching.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Execute cancellation. Without this flag, only preview is shown.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    if argv is not None and len(argv) == 0:
        parser.print_help()
        return
    args = parser.parse_args(argv)

    if args.bundle_file is None and not args.target:
        parser.error("Provide either a bundle target or --bundle-file.")
    if args.bundle_file is not None and args.target:
        parser.error("Use either target or --bundle-file, not both.")
    if args.name_contains and args.name_regex:
        parser.error("Use only one of --name-contains or --name-regex.")

    status_predicate = lambda state: _state_matches(state, args.status_filter)

    if args.bundle_file is not None:
        jobs, _, bundle_date = load_bundle_from_path(args.bundle_file)
        status_text = None
        statuses = job_status_texts(jobs)
        raw_rows: list[dict] = []
        name_regex_obj = None
        if args.name_regex:
            flags = re.IGNORECASE if args.ignore_case else 0
            try:
                name_regex_obj = re.compile(args.name_regex, flags=flags)
            except re.error as exc:
                raise SystemExit(f"Invalid --name-regex pattern: {exc}") from exc
        for job in jobs:
            name = str(job["name"])
            if args.name_contains:
                haystack = name.lower() if args.ignore_case else name
                needle = args.name_contains.lower() if args.ignore_case else args.name_contains
                if needle not in haystack:
                    continue
            if name_regex_obj and not name_regex_obj.search(name):
                continue
            state = statuses.get(job["name"], "UNKNOWN")
            if not status_predicate(state):
                continue
            raw_rows.append(
                {
                    "job_id_raw": None if job.get("id") is None else str(job.get("id")),
                    "machine_name": job.get("machine"),
                }
            )
    else:
        reference_date = _parse_date(args.date)
        bundle_name, bundle_date = _resolve_bundle_name(args.target, reference_date)
        status_text = bundle_jobs_context(
            bundle_name,
            bundle_date,
            name_contains=args.name_contains,
            name_regex=args.name_regex,
            ignore_case=args.ignore_case,
            status_predicate=status_predicate,
        )
        _, raw_rows = bundle_job_rows(
            bundle_name,
            bundle_date,
            name_contains=args.name_contains,
            name_regex=args.name_regex,
            ignore_case=args.ignore_case,
            status_predicate=status_predicate,
        )

    if status_text:
        print(status_text)
    candidates = [
        {"id": row["job_id_raw"], "machine_name": row["machine_name"]}
        for row in raw_rows
        if row.get("job_id_raw") is not None
    ]
    if not candidates:
        print("No matching jobs to cancel.")
        return

    if not args.yes:
        print("Preview only. Re-run with --yes to cancel these jobs.")
        return

    by_machine: dict[Optional[str], list[str]] = {}
    for item in candidates:
        by_machine.setdefault(item["machine_name"], []).append(str(item["id"]))

    config = None
    for machine_name, job_ids in by_machine.items():
        if machine_name is None:
            _cancel_local(job_ids)
            continue
        if config is None:
            config = load_config()
        machine_cfg = config["machines"].get(machine_name) or config.get(machine_name)
        if machine_cfg is None:
            raise RuntimeError(f"Machine '{machine_name}' not found in config.")
        _cancel_remote(machine_name, machine_cfg, job_ids)

    print(f"\nCancelled {len(candidates)} job(s).")
