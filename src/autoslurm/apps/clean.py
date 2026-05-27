from __future__ import annotations

import argparse
from pathlib import Path

from ..save_load_jobs import all_bundle_snapshots, bundle_snapshots, inactive_bundle_snapshots, load_bundle_from_path
from ..status import FAILED_STATES, job_status_texts


def _render_table(rows: list[dict[str, str]]) -> str:
    headers = ["idx", "bundle", "state", "saved", "jobs", "submitted", "path"]
    widths = {key: max(len(key), max(len(row[key]) for row in rows)) for key in headers}
    lines = ["  ".join(key.center(widths[key]) for key in headers)]
    lines.extend("  ".join(row[key].ljust(widths[key]) for key in headers) for row in rows)
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Preview/remove inactive bundle snapshots (ready_to_go or broken). "
            "Default is preview-only; pass --yes to delete files."
        )
    )
    parser.add_argument(
        "target",
        nargs="*",
        help="Optional bundle indices/ranges to delete from current `asl status` ordering (e.g. 1 3-5).",
    )
    parser.add_argument(
        "--scope",
        choices=("inactive", "failed", "unsubmitted", "all"),
        default="inactive",
        help=(
            "When no target is provided: "
            "'inactive' cleans stale snapshots (default), "
            "'failed' cleans snapshots where all submitted jobs are terminal failures, "
            "'unsubmitted' cleans snapshots with zero submitted jobs, "
            "'all' combines both."
        ),
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Delete inactive bundle files. Without this flag, only preview is shown.",
    )
    return parser


def _resolve_target_rows(targets: list[str], parser: argparse.ArgumentParser) -> list[dict]:
    rows = list(bundle_snapshots())
    rows.sort(key=lambda entry: entry["date"], reverse=True)
    if not rows:
        return []
    selected: list[dict] = []
    for token in targets:
        if token.isdigit():
            index = int(token)
            if index < 1 or index > len(rows):
                parser.error(f"Bundle index '{token}' is out of range.")
            selected.append(rows[index - 1])
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
                    selected.append(rows[index - 1])
                continue
        parser.error(f"Invalid target '{token}'. Use indices/ranges like 1 2-4.")
    seen: set[str] = set()
    deduped: list[dict] = []
    for row in selected:
        path = str(row["path"])
        if path in seen:
            continue
        seen.add(path)
        deduped.append(row)
    return deduped


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    targets = list(args.target or [])
    if targets:
        selected = _resolve_target_rows(targets, parser)
        if not selected:
            print("No saved bundle snapshots found.")
            return
    else:
        inactive = inactive_bundle_snapshots()
        unsubmitted = [entry for entry in all_bundle_snapshots() if int(entry.get("submitted_count", 0)) == 0]
        failed: list[dict] = []
        if args.scope in {"failed", "all"}:
            for entry in all_bundle_snapshots():
                try:
                    jobs, _, _ = load_bundle_from_path(entry["path"])
                except Exception:
                    continue
                submitted = [job for job in jobs if job.get("id") is not None]
                if not submitted:
                    continue
                statuses = job_status_texts(jobs)
                submitted_states = [statuses.get(str(job["name"]), "UNKNOWN").upper() for job in submitted]
                if submitted_states and all(state in FAILED_STATES for state in submitted_states):
                    failed.append(entry)
        if args.scope == "inactive":
            selected = inactive
        elif args.scope == "unsubmitted":
            selected = unsubmitted
        elif args.scope == "failed":
            selected = failed
        else:
            by_path = {str(item["path"]): item for item in inactive}
            for item in unsubmitted:
                by_path.setdefault(str(item["path"]), item)
            for item in failed:
                by_path.setdefault(str(item["path"]), item)
            selected = sorted(by_path.values(), key=lambda item: item["date"], reverse=True)
        if not selected:
            print("No matching bundle snapshots found.")
            return

    rows = [
        {
            "idx": str(i),
            "bundle": str(item["bundle"]),
            "state": str(item.get("state", "unknown")),
            "saved": item["date"].strftime("%Y-%m-%d %H:%M:%S"),
            "jobs": str(item.get("job_count", 0)),
            "submitted": str(item.get("submitted_count", 0)),
            "path": str(item["path"]),
        }
        for i, item in enumerate(selected, start=1)
    ]
    print(_render_table(rows))
    print(f"\nScope: {args.scope}")
    print("Available scopes:")
    print("- inactive: stale snapshots hidden by active policy.")
    print("- failed: snapshots where all submitted jobs are terminal failures.")
    print("- unsubmitted: snapshots with zero submitted jobs.")
    print("- all: union of inactive, failed, and unsubmitted.")
    if not args.yes:
        print("\nPreview only. Re-run with --yes to delete these bundle files.")
        return
    removed = 0
    for item in selected:
        path = Path(item["path"])
        if path.exists():
            path.unlink()
            removed += 1
    print(f"\nRemoved {removed} bundle file(s).")
