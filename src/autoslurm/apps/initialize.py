import argparse
import sys
from ..save_load_jobs import save_bundle


def parse_args(argv=None):
    # fmt: off
    parser = argparse.ArgumentParser(description='Initialize a bundle of jobs to run with SLURM')
    parser.add_argument('name', help='Name of the job bundle (JSON file containing multiple jobs/scripts to be scheduled).')
    # fmt: on
    args = parser.parse_args(argv)
    return args


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if not argv:
        parser = argparse.ArgumentParser(description='Initialize a bundle of jobs to run with SLURM')
        parser.add_argument('name', help='Name of the job bundle (JSON file containing multiple jobs/scripts to be scheduled).')
        parser.print_help()
        return
    args = parse_args(argv)
    save_bundle({}, args.name)
