from __future__ import annotations

import argparse
import sys

from ..context import agent_context


def main(argv=None) -> None:
    if argv is None:
        argv = sys.argv[1:]
    if not argv:
        parser = argparse.ArgumentParser(
            description="Dump the agent documentation context as a single string."
        )
        parser.add_argument(
            "--sections",
            nargs="+",
            help="Optional list of agent filenames or substrings to include.",
        )
        parser.print_help()
        return
    parser = argparse.ArgumentParser(
        description="Dump the agent documentation context as a single string."
    )
    parser.add_argument(
        "--sections",
        nargs="+",
        help="Optional list of agent filenames or substrings to include.",
    )
    args = parser.parse_args(argv)

    context = agent_context(sections=args.sections)
    print(context)
