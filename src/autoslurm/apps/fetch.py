"""Selected-run fetching uses the existing log selector and presentation."""

from .logs import _main


def main(argv=None):
    return _main(argv, fetch=True)
