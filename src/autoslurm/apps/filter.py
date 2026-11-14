from __future__ import annotations

import argparse
import sys

from ..bundle_selection import get_bundle_filter_mode, set_bundle_filter_mode
from ..errors import ConfigurationError, SelectionError
from .error_output import exit_with_error


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
    parser.add_argument('--debug', action='store_true', help='Show original selection/configuration errors.')
    return parser


def _main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    mode = get_bundle_filter_mode()
    if args.mode is not None:
        mode = set_bundle_filter_mode(args.mode)
    print(f"Current bundle filter: {mode}")
    print("Available filters:")
    print("- active: show running/completed submission history; also show the latest ready_to_go snapshot when it is the newest snapshot for a bundle name (or latest broken if no ready_to_go exists).")
    print("- all: show every saved bundle snapshot with no filtering.")


def main(argv: list[str] | None = None) -> None:
    selected = list(sys.argv[1:] if argv is None else argv)
    try:
        return _main(selected)
    except (ConfigurationError, SelectionError) as error:
        exit_with_error(error, debug='--debug' in selected)
