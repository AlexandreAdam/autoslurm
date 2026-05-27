from __future__ import annotations

import argparse
from pathlib import Path

from ..save_load_jobs import inactive_bundle_snapshots


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
        "--yes",
        action="store_true",
        help="Delete inactive bundle files. Without this flag, only preview is shown.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    inactive = inactive_bundle_snapshots()
    if not inactive:
        print("No inactive bundle snapshots found.")
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
        for i, item in enumerate(inactive, start=1)
    ]
    print(_render_table(rows))
    if not args.yes:
        print("\nPreview only. Re-run with --yes to delete these inactive bundle files.")
        return
    removed = 0
    for item in inactive:
        path = Path(item["path"])
        if path.exists():
            path.unlink()
            removed += 1
    print(f"\nRemoved {removed} inactive bundle file(s).")
