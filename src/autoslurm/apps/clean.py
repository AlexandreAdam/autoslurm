from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from ..bundle_selection import all_bundle_snapshots, bundle_snapshots, inactive_bundle_snapshots
from ..inspection import observe_job_statuses
from ..inspection_collection import load_run
from ..status import FAILED_STATES


SCOPES = {
    "inactive": "stale snapshots hidden by active policy (default)",
    "failed": "all submitted jobs failed (excluding cancellation)",
    "unsubmitted": "zero submitted jobs; tracked attempts remain protected",
    "cancelled": "all submitted jobs cancelled",
    "completed": "all jobs submitted and completed successfully",
    "terminal": "all submitted jobs finished, including mixed outcomes",
    "all": "union of inactive, unsubmitted and terminal snapshots",
}
TERMINAL_SCOPES = {"failed", "cancelled", "completed", "terminal", "all"}


def _terminal_scope(entry):
    """Require fresh, complete task observations, never just an aggregate failure."""
    run = load_run(entry["path"])
    if run.errors or not run.jobs:
        return None
    # An unfinished/partial/uncertain dispatch may still accept more work.
    if any(receipt["state"] != "submitted" for receipt in run.submissions):
        return None
    submitted = [job for job in run.jobs if job.get("id") is not None]
    if not submitted:
        return None
    observed = observe_job_statuses(submitted)
    if len(observed) != len(submitted):
        return None
    states = []
    for job, view in zip(submitted, observed):
        if (view["name"] != job["name"] or view["errors"] or not view["observed_at"]
                or not view["tasks"]):
            return None
        task_states = [task["state"] for task in view["tasks"]]
        if any(state not in FAILED_STATES | {"COMPLETED"} for state in task_states):
            return None
        if view["state"] not in FAILED_STATES | {"COMPLETED"}:
            return None
        states.extend([view["state"], *task_states])
    entry["cleanup_fingerprint"] = run.fingerprint
    entry["terminal_cleanup"] = True
    entry["state"] = "terminal"
    if all(state == "COMPLETED" for state in states) and len(submitted) == len(run.jobs):
        entry["state"] = "completed"
    elif all(state == "CANCELLED" for state in states):
        entry["state"] = "cancelled"
    elif all(state in FAILED_STATES - {"CANCELLED"} for state in states):
        entry["state"] = "failed"
    return entry["state"]


def _render_table(rows: list[dict[str, str]]) -> str:
    headers = ["idx", "bundle", "state", "saved", "jobs", "submitted", "path"]
    widths = {key: max(len(key), max(len(row[key]) for row in rows)) for key in headers}
    lines = ["  ".join(key.center(widths[key]) for key in headers)]
    lines.extend("  ".join(row[key].ljust(widths[key]) for key in headers) for row in rows)
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Preview/remove saved bundle snapshots by scope. "
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
        choices=tuple(SCOPES),
        default="inactive",
        help="Scope filters automatic selection; terminal scopes also constrain explicit targets: " + "; ".join(f"{key}: {value}" for key, value in SCOPES.items()),
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Delete selected local bundle files only. Without this flag, only preview is shown.",
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
        if args.scope in TERMINAL_SCOPES:
            selected = [entry for entry in selected
                        if (args.scope == "all" and entry.get("submitted_count") == 0)
                        or ((state := _terminal_scope(entry))
                            and (args.scope in {"terminal", "all"} or args.scope == state))]
        if not selected:
            print("No matching bundle snapshots found.")
            return
    else:
        entries = all_bundle_snapshots()
        inactive = {str(entry["path"]) for entry in inactive_bundle_snapshots()}
        selected = []
        for entry in entries:
            path = str(entry["path"])
            structural_match = ((args.scope in {"inactive", "all"} and path in inactive)
                or (args.scope in {"unsubmitted", "all"} and entry.get("submitted_count") == 0))
            if structural_match:
                if args.scope == "all":
                    _terminal_scope(entry)
                selected.append(entry)
            elif args.scope in TERMINAL_SCOPES:
                terminal = _terminal_scope(entry)
                if terminal and (args.scope in {"terminal", "all"} or args.scope == terminal):
                    selected.append(entry)
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
    for key, description in SCOPES.items():
        print(f"- {key}: {description}")
    print("Only local bundle JSON files are removed; receipts, logs, scripts and scientific files remain.")
    print("Deleting a bundle removes its status/index/log navigation. Retained receipts do not restore it.")
    if not args.yes:
        print("\nPreview only. Re-run with --yes to delete these bundle files.")
        return
    removed = 0
    for item in selected:
        path = Path(item["path"])
        if path.exists():
            try:
                content = path.read_bytes()
                if '"_autoslurm_submission"' in content.decode("utf-8"):
                    if not item.get("terminal_cleanup"):
                        print(f"Retained submission evidence: {path}")
                        continue
                if item.get("cleanup_fingerprint") and hashlib.sha256(content).hexdigest() != item["cleanup_fingerprint"]:
                    print(f"Retained changed evidence: {path}")
                    continue
            except (OSError, UnicodeError):
                print(f"Retained unreadable evidence: {path}")
                continue
            path.unlink()
            removed += 1
    print(f"\nRemoved {removed} bundle file(s).")
