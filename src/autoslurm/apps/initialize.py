import argparse
import sys
from ..save_load_jobs import save_bundle
from ..errors import InvalidRequestError, SelectionError, RecordWriteError
from .error_output import exit_with_error


def _build_parser():
    # fmt: off
    parser = argparse.ArgumentParser(description='Initialize a bundle of jobs to run with SLURM')
    parser.add_argument('name', help='Name of the job bundle (JSON file containing multiple jobs/scripts to be scheduled).')
    parser.add_argument('--debug', action='store_true', help='Show original record errors.')
    # fmt: on
    return parser


def parse_args(argv=None):
    return _build_parser().parse_args(argv)


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if not argv:
        _build_parser().print_help()
        return
    args = parse_args(argv)
    try:
        save_bundle({}, args.name)
    except (InvalidRequestError, SelectionError, RecordWriteError) as error:
        exit_with_error(error, debug=args.debug)
