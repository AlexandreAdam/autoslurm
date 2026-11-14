from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from .inspection_selection import resolve_job_selection
from ..errors import SelectionError, ConfigurationError
from .error_output import exit_with_error


from .status import _build_reference_date


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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect job output logs.")
    parser.add_argument("bundle", nargs="*", help="Bundle name/index to inspect. Supports ranges like 1-3.")
    parser.add_argument("--view", action="store_true", help="List saved runs with shared status observations.")
    parser.add_argument("--list", action="store_true", help="Show selected bundle jobs.")
    parser.add_argument("--full", action="store_true", help="Include scripts and bounded log tails.")
    parser.add_argument("--latest", "-l", action="store_true", help="Use the latest saved bundle.")
    parser.add_argument("--job", help="Select a job by index or name.")
    parser.add_argument(
        "--array",
        nargs="*",
        metavar="TASK",
        help="Expand array jobs into per-task rows, optionally filtering by task indices or ranges.",
    )
    parser.add_argument(
        "--array-task",
        dest="array_task",
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--script", action="store_true", help="Print the rendered SLURM script for --job.")
    parser.add_argument("--status", action="store_true", help="Print SLURM status for --job.")
    parser.add_argument("--log", action="store_true", help="Print bounded stdout/stderr for submitted identities.")
    parser.add_argument("--logs", dest="log", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--tail", type=int, help="Print only the last N lines of the selected log output.")
    parser.add_argument("--list-files", action="store_true", help="List resolved log paths and availability.")
    parser.add_argument("--refresh", action="store_true", help="Refresh selected producing-machine evidence and bounded log tails.")
    parser.add_argument("--clipboard", "--clip", action="store_true", help="Copy output to clipboard.")
    parser.add_argument("--date", help="Optional timestamp to target the bundle closest to the provided date.")
    parser.add_argument("--year", type=int, help="Reference year, e.g. 2025.")
    parser.add_argument("--month", type=int, help="Reference month, e.g. 1 or 01.")
    parser.add_argument("--day", type=int, help="Reference day of month.")
    parser.add_argument("--hour", type=int, help="Reference hour.")
    parser.add_argument("--minute", type=int, help="Reference minute.")
    parser.add_argument("--second", type=int, help="Reference second.")
    return parser


def _main(argv=None):
    import json
    from ..inspection import inspect_bundles
    from ..save_load_jobs import load_bundle_from_path, bundle_snapshots
    from ..status_views import rows_from_resolved, bundle_jobs_context_from_rows, observation_text
    from .status import _selected_paths
    parser = _build_parser()
    parser.add_argument("--bundle-file", type=Path, help="Select an exact saved snapshot.")
    parser.add_argument("--receipt", type=Path, help="Select the exact snapshot referenced by a local receipt.")
    parser.add_argument("--json", action="store_true", help="Return the shared structured observation.")
    parser.add_argument("--cached", action="store_true", help="Read cached scheduler evidence without network calls.")
    parser.add_argument('--debug', action='store_true', help='Show original selection/configuration errors.')
    args = parser.parse_args(argv)
    if args.cached and args.refresh:
        parser.error("Choose cached evidence or an explicit refresh.")
    if args.view:
        from .status import main as status_main
        forwarded = ["--cached"] if args.cached else []
        if args.debug:
            forwarded.append('--debug')
        for field in ("date", "year", "month", "day", "hour", "minute", "second"):
            if getattr(args, field) is not None:
                forwarded.extend(["--" + field, str(getattr(args, field))])
        if args.json:
            forwarded.append("--json")
        status_main(forwarded)
        return
    if args.full:
        args.script = args.log = True
    if argv == [] or (not args.bundle and not args.latest and not args.bundle_file and not args.receipt):
        parser.print_help()
        return
    if sum([bool(args.bundle), args.latest, args.bundle_file is not None, args.receipt is not None]) > 1:
        parser.error("Choose one bundle selector.")
    reference = _build_reference_date(args.date, args.year, args.month, args.day, args.hour, args.minute, args.second)
    entries = sorted(bundle_snapshots(reference), key=lambda item: item["date"], reverse=True)
    if args.receipt:
        from ..submission import load_submission
        paths = [Path(load_submission(args.receipt)["bundle_path"])]
    elif args.bundle_file:
        paths = [args.bundle_file]
    elif args.latest:
        if not entries:
            print("No saved bundles found.")
            return
        paths = [entries[0]["path"]]
    else:
        paths = _selected_paths(args.bundle, entries, parser, reference)
    # Resolve display indices before the observation call; this never queries.
    selected_name, selected_task, array_tasks = resolve_job_selection(
        paths, args.job, args.array, int(args.array_task) if args.array_task is not None else None, parser)
    logs = args.log or args.list_files or (args.job is not None and not args.script and not args.status)
    views = inspect_bundles(paths, refresh=not args.cached, include_logs=logs, job_name=selected_name,
                            task_index=selected_task, tail=40 if args.tail is None else args.tail,
                            include_script=args.script, refresh_logs=not args.cached,
                            task_indices=array_tasks if selected_task is None else None)
    if args.json:
        _emit(json.dumps(views[0] if len(views) == 1 else views, indent=2), args.clipboard)
        return
    parts = []
    for path, view in zip(paths, views):
        if view["state"] == "broken":
            parts.append(f"Run: broken ({path})")
            parts.extend(f"Observation error: {error['source']}: {error['message']}" for error in view["errors"])
            continue
        jobs, _, date = load_bundle_from_path(path)
        parts.append(observation_text(view))
        if args.script:
            parts.extend(item["content"] or f"script missing: {item['path']}" for item in view.get("scripts", []))
        if not logs and not args.script:
            visible = [job for job in jobs if selected_name is None or job["name"] == selected_name]
            rows = rows_from_resolved(visible, [job for job in view["jobs"] if selected_name is None or job["name"] == selected_name], show_array_tasks=args.array is not None, array_tasks=array_tasks)
            parts.append(bundle_jobs_context_from_rows(Path(path).stem.rsplit("_", 1)[0], date, rows, show_array_tasks=args.array is not None))
        if logs:
            for log in view["logs"]:
                parts.append(log.get("path", ""))
                if args.list_files:
                    parts.append(f"Log {log['state']}")
                else:
                    parts.append(log.get("text", f"Log {log['state']}: {log.get('error', '')}"))
            if not view["logs"]:
                parts.append("No logs found for this submitted identity.")
    _emit("\n".join(parts), args.clipboard)


def main(argv=None):
    selected = list(sys.argv[1:] if argv is None else argv)
    try:
        return _main(selected)
    except (SelectionError, ConfigurationError) as error:
        exit_with_error(error, json_output='--json' in selected, debug='--debug' in selected)
