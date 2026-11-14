from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from typing import Optional

from ..status_views import bundle_jobs_context_from_rows
from ..bundle_selection import bundle_snapshots
from ..errors import SelectionError, ConfigurationError
from .error_output import exit_with_error


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


def _selected_paths(tokens, entries, parser, reference_date=None):
    from ..save_load_jobs import select_bundle_snapshot
    paths = []
    for token in tokens:
        if token.isdigit():
            indices = [int(token)]
        elif re.fullmatch(r"\d+-\d+", token):
            left, right = map(int, token.split("-"))
            if left > right:
                parser.error("Invalid bundle range.")
            indices = range(left, right + 1)
        else:
            paths.append(select_bundle_snapshot(token, desired_date=reference_date, prefer_draft=False)["path"])
            continue
        for index in indices:
            if not 1 <= index <= len(entries):
                parser.error(f"Bundle index {index} is out of range.")
            paths.append(entries[index - 1]["path"])
    return list(dict.fromkeys(paths))


def _main(argv=None):
    import json
    from pathlib import Path
    from ..inspection import inspect_bundles
    from ..save_load_jobs import load_bundle_from_path
    from ..status_views import summary_text, rows_from_resolved, observation_text
    parser = _build_parser()
    parser.add_argument("--bundle-file", type=Path, help="Inspect one exact saved snapshot.")
    parser.add_argument("--json", action="store_true", help="Return the shared structured observation.")
    parser.add_argument("--cached", action="store_true", help="Read last observations without scheduler queries; marked stale.")
    parser.add_argument('--debug', action='store_true', help='Show original selection/configuration errors.')
    args = parser.parse_args(argv)
    reference = _build_reference_date(args.date, args.year, args.month, args.day, args.hour, args.minute, args.second)
    entries = _status_rows(reference)
    if args.bundle_file and args.target:
        parser.error("Use bundle-file or name/index selectors.")
    paths = [args.bundle_file] if args.bundle_file else _selected_paths(args.target, entries, parser, reference) if args.target else [entry["path"] for entry in entries]
    views = inspect_bundles(paths, refresh=not args.cached)
    if args.json:
        print(json.dumps(views, indent=2))
        return
    if not args.target and args.bundle_file is None:
        print(summary_text(entries, views))
    else:
        array_tasks = _parse_array_task_filter(args.array, parser)
        for path, view in zip(paths, views):
            if view["state"] == "broken":
                print(f"Run: broken ({path})")
                for error in view["errors"]:
                    print(f"Observation error: {error['source']}: {error['message']}")
                continue
            jobs, _, date = load_bundle_from_path(path)
            rows = rows_from_resolved(jobs, view["jobs"], show_array_tasks=args.array is not None, array_tasks=array_tasks)
            print(bundle_jobs_context_from_rows(Path(path).stem.rsplit("_", 1)[0], date, rows, show_array_tasks=args.array is not None))
            print(observation_text(view))


def main(argv=None):
    selected = list(sys.argv[1:] if argv is None else argv)
    try:
        return _main(selected)
    except (SelectionError, ConfigurationError) as error:
        exit_with_error(error, json_output='--json' in selected, debug='--debug' in selected)
