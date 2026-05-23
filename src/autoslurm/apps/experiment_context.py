from __future__ import annotations

import argparse
import sys
from datetime import datetime
from typing import Optional

from ..save_load_jobs import list_saved_bundles
from ..experiment_context import experiment_context


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
    except ValueError:
        raise argparse.ArgumentTypeError(
            "Date must be ISO formatted (e.g. 2023-09-01T12:00:00) or use YYYYMMDDHHMMSS."
        )


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


def _add_date_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--date",
        help="Optional timestamp to target the bundle closest to the provided date.",
    )
    parser.add_argument("--year", type=int, help="Reference year, e.g. 2025.")
    parser.add_argument("--month", type=int, help="Reference month, e.g. 1 or 01.")
    parser.add_argument("--day", type=int, help="Reference day of month.")
    parser.add_argument("--hour", type=int, help="Reference hour.")
    parser.add_argument("--minute", type=int, help="Reference minute.")
    parser.add_argument("--second", type=int, help="Reference second.")


def _resolve_reference_date(args: argparse.Namespace) -> Optional[datetime]:
    return _build_reference_date(
        args.date,
        args.year,
        args.month,
        args.day,
        args.hour,
        args.minute,
        args.second,
    )


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "bundle",
        nargs="?",
        help="Bundle name to inspect (e.g., the name passed to autoslurm-schedule).",
    )
    _add_date_arguments(parser)
    parser.add_argument(
        "--list",
        action="store_true",
        help="List saved bundles instead of printing a single bundle context.",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Dump the context for a job or bundle."
    )
    _add_common_arguments(parser)
    return parser


def main(argv=None) -> None:
    if argv is None:
        argv = sys.argv[1:]
    parser = _build_parser()
    if not argv:
        parser.print_help()
        return
    args = parser.parse_args(argv)

    reference_date = _resolve_reference_date(args)

    if args.list:
        entries = list_saved_bundles(
            desired_date=reference_date, bundle_name=args.bundle
        )
        if not entries:
            print("No saved bundles found.")
            return
        for entry in entries:
            print(
                f"{entry['date'].isoformat()}  {entry['bundle']}  jobs={', '.join(entry['jobs']) or '[]'}  path={entry['path']}"
            )
        return

    if not args.bundle:
        parser.print_help()
        return

    context = experiment_context(args.bundle, reference_date)
    print(context)
