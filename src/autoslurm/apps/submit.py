import argparse
import sys
from pathlib import Path
from ..config import machine_config
from ..bundle_selection import bundle_snapshot_state, select_bundle_snapshot
from ..execution import resolve_execution_context
from ..job_runner import submit_jobs
from ..submission import SubmissionError
from ..errors import ConfigurationError, InvalidRequestError, SelectionError
from .error_output import exit_with_error


def parse_args(argv=None):
    """
    Parses command line arguments.

    Returns:
    argparse.Namespace: The parsed command line arguments.
    """
    parser = argparse.ArgumentParser(description="Run scripts on a SLURM cluster.")
    parser.add_argument("name", nargs="?", help="Name of the job")
    parser.add_argument('--debug', action='store_true', help='Show original selection, configuration or preparation errors.')
    # parser.add_argument('date', required=False, help='If provided, will look for job closest to this date. Otherwise, latest job is ran.'
    # 'Provide in the format [Y]YYYY-[M]MM-[D]DD-[H]HH-[m]mm-[s]ss.'
    # 'E.g., Y2021 will yield the latest job of 2021. M09 will yield the latest job of last September.'
    # 'D15 will yield the latest job of the 15th of the month. Y2021-M09 will yield the latest job of September 2021. etc.')

    # Optional argument for machine configuration
    parser.add_argument(
        "--machine",
        required=False,
        help="Machine name to run the jobs (e.g., local, remote_1)",
    )

    # Optional arguments for custom machine configuration
    parser.add_argument("--ssh-alias", help="SSH config Host alias for the selected machine.")
    parser.add_argument(
        "--venv_path",
        required=False,
        help="Path to the virtualenv root; autoslurm renders source <venv>/bin/activate.",
    )
    parser.add_argument(
        "--env_command",
        required=False,
        help="Shell setup before venv activation (for example module load); also works without --venv_path.",
    )
    parser.add_argument(
        "--slurm_account",
        required=False,
        help="SLURM account to use for job submission",
    )
    parser.add_argument(
        "--bundle-file",
        required=False,
        type=Path,
        help="Explicit path to a JSON bundle file to submit instead of loading from AutoSlurm storage.",
    )
    parser.add_argument(
        "--latest",
        action="store_true",
        help="Submit the latest scheduled bundle from AutoSlurm storage.",
    )
    parser.add_argument(
        "--index",
        type=int,
        required=False,
        help="Submit a specific saved bundle snapshot by index (from `autoslurm status`).",
    )

    return parser.parse_args(argv)


def _main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if not argv:
        parser = argparse.ArgumentParser(description="Run scripts on a SLURM cluster.")
        parser.add_argument("name", help="Name of the job")
        parser.add_argument("--machine", required=False, help="Machine name to run the jobs (e.g., local, remote_1)")
        parser.add_argument("--ssh-alias", help="SSH config Host alias for the selected machine.")
        parser.add_argument("--venv_path", required=False, help="Path to the virtualenv root; autoslurm renders source <venv>/bin/activate.")
        parser.add_argument("--env_command", required=False, help="Shell setup before venv activation (for example module load); also works without --venv_path.")
        parser.add_argument("--slurm_account", required=False, help="SLURM account to use for job submission")
        parser.add_argument("--bundle-file", required=False, type=Path, help="Explicit path to a JSON bundle file to submit instead of loading from AutoSlurm storage.")
        parser.add_argument("--latest", action="store_true", help="Submit the latest scheduled bundle from AutoSlurm storage.")
        parser.print_help()
        return
    args = parse_args(argv)
    selected = select_bundle_snapshot(args.name, bundle_path=args.bundle_file, latest=args.latest, index=args.index)
    args.name, args.bundle_file = selected["bundle"], Path(selected["path"])

    bundle_snapshot_state(args.bundle_file, strict=True)

    machine_name, config = machine_config(args)
    try:
        submit_jobs(
            args.name,
            machine=machine_name,
            machine_overrides=config,
            bundle_path=args.bundle_file,
            context=resolve_execution_context(machine_name, config),
        )
    except InvalidRequestError as error:
        exit_with_error(error, debug=args.debug)
    except (SubmissionError, ValueError, RuntimeError, OSError) as exc:
        raise SystemExit(str(exc)) from exc


def main(argv=None):
    selected = list(sys.argv[1:] if argv is None else argv)
    try:
        return _main(selected)
    except (SelectionError, ConfigurationError) as error:
        exit_with_error(error, debug='--debug' in selected)
