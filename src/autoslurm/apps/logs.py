from __future__ import annotations

import sys

from . import inspect, status


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else list(argv)
    if not args:
        status.main([])
        return
    inspect.main(args)
