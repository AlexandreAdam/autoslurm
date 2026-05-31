from __future__ import annotations

import argparse

from ..save_load_jobs import get_bundle_filter_mode, set_bundle_filter_mode


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Manage global bundle visibility filter used by AutoSlurm CLI surfaces. "
            "'active' shows submitted histories, plus only the latest draft per bundle name when no submitted history exists; "
            "'all' shows every saved snapshot."
        )
    )
    parser.add_argument(
        "mode",
        nargs="?",
        choices=("active", "all"),
        help="Set filter mode. Omit to print current mode.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    mode = get_bundle_filter_mode()
    if args.mode is not None:
        mode = set_bundle_filter_mode(args.mode)
    print(f"Current bundle filter: {mode}")
    print("Available filters:")
    print("- active: show running/completed submission history; also show the latest ready_to_go snapshot when it is the newest snapshot for a bundle name (or latest broken if no ready_to_go exists).")
    print("- all: show every saved bundle snapshot with no filtering.")
