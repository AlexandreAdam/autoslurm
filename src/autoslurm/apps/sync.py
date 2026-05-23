from __future__ import annotations

import argparse
import sys

from ..sync import sync_machine


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else list(argv)
    parser = argparse.ArgumentParser(description="Sync a remote AutoSlurm machine into local storage.")
    parser.add_argument(
        "machine",
        nargs="?",
        help="Machine name to sync. Defaults to the configured default machine.",
    )
    if not args:
        parsed = parser.parse_args([])
        sync_machine(parsed.machine)
        return
    if args[0] in {"-h", "--help"}:
        parser.print_help()
        return
    parsed = parser.parse_args(args)
    sync_machine(parsed.machine)
