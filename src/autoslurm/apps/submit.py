import argparse
import sys
from pathlib import Path
from ..utils import machine_config
from ..save_load_jobs import (
    bundle_snapshot_state,
    all_bundle_snapshots,
    bundle_snapshots,
    latest_bundle_summaries,
    list_saved_bundles,
)
from ..job_runner import submit_jobs


def parse_args(argv=None):
    """
    Parses command line arguments.

    Returns:
    argparse.Namespace: The parsed command line arguments.
    """
    parser = argparse.ArgumentParser(description="Run scripts on a SLURM cluster.")
    parser.add_argument("name", nargs="?", help="Name of the job")
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
    parser.add_argument(
        "--hostname", required=False, help="Hostname of the remote machine"
    )
    parser.add_argument("--hosturl", required=False, help="The url of the machine")
    parser.add_argument("--username", required=False, help="Username for SSH login")
    parser.add_argument(
        "--key_path", required=False, help="Path to the SSH private key"
    )
    parser.add_argument(
        "--venv_path",
        required=False,
        help="Path to the virtualenv root; autoslurm renders source <venv>/bin/activate.",
    )
    parser.add_argument(
        "--env_command",
        required=False,
        help="Legacy command to activate environment (deprecated; prefer --venv_path).",
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


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if not argv:
        parser = argparse.ArgumentParser(description="Run scripts on a SLURM cluster.")
        parser.add_argument("name", help="Name of the job")
        parser.add_argument("--machine", required=False, help="Machine name to run the jobs (e.g., local, remote_1)")
        parser.add_argument("--hostname", required=False, help="Hostname of the remote machine")
        parser.add_argument("--hosturl", required=False, help="The url of the machine")
        parser.add_argument("--username", required=False, help="Username for SSH login")
        parser.add_argument("--key_path", required=False, help="Path to the SSH private key")
        parser.add_argument("--venv_path", required=False, help="Path to the virtualenv root; autoslurm renders source <venv>/bin/activate.")
        parser.add_argument("--env_command", required=False, help="Legacy command to activate environment (deprecated; prefer --venv_path).")
        parser.add_argument("--slurm_account", required=False, help="SLURM account to use for job submission")
        parser.add_argument("--bundle-file", required=False, type=Path, help="Explicit path to a JSON bundle file to submit instead of loading from AutoSlurm storage.")
        parser.add_argument("--latest", action="store_true", help="Submit the latest scheduled bundle from AutoSlurm storage.")
        parser.print_help()
        return
    args = parse_args(argv)
    if args.latest and args.bundle_file is not None:
        raise SystemExit("--latest cannot be combined with --bundle-file.")
    if args.index is not None and args.bundle_file is not None:
        raise SystemExit("--index cannot be combined with --bundle-file.")
    if args.latest and args.index is not None:
        raise SystemExit("--latest cannot be combined with --index.")
    if args.latest and args.name is not None:
        raise SystemExit("--latest does not take a bundle name.")
    if args.index is not None and args.name is not None:
        raise SystemExit("--index does not take a bundle name.")
    if not args.latest and args.name is None:
        if args.index is None and args.bundle_file is None:
            raise SystemExit("Submit requires a bundle name unless --latest or --index is used.")

    if args.name is None and args.bundle_file is not None:
        stem = args.bundle_file.stem
        if "_" in stem:
            args.name = stem.rsplit("_", 1)[0]
        else:
            raise SystemExit("Unable to infer bundle name from --bundle-file. Provide an explicit bundle name.")

    if args.latest:
        drafts = [entry for entry in all_bundle_snapshots() if str(entry.get("state", "")).lower() == "ready_to_go"]
        if drafts:
            latest = max(drafts, key=lambda entry: entry["date"])
        else:
            summaries = latest_bundle_summaries()
            if not summaries:
                raise SystemExit("No saved bundles found.")
            latest = max(summaries, key=lambda entry: entry["date"])
        args.name = latest["bundle"]
        latest_path = latest.get("path")
        if latest_path is not None:
            args.bundle_file = Path(latest_path)
    elif args.index is not None:
        rows = bundle_snapshots()
        if not rows:
            raise SystemExit("No saved bundles found.")
        if args.index < 1 or args.index > len(rows):
            raise SystemExit(f"Bundle index '{args.index}' is out of range.")
        selected = rows[args.index - 1]
        args.name = selected["bundle"]
        args.bundle_file = Path(selected["path"])

    if args.bundle_file is None:
        draft_candidates = [
            entry
            for entry in all_bundle_snapshots()
            if str(entry.get("bundle", "")) == str(args.name)
            and str(entry.get("state", "")).lower() == "ready_to_go"
        ]
        if draft_candidates:
            selected = max(draft_candidates, key=lambda entry: entry["date"])
            args.bundle_file = Path(selected["path"])
        else:
            candidates = list_saved_bundles(bundle_name=args.name)
            if not candidates:
                raise SystemExit(f"No saved bundle found for '{args.name}'.")
            args.bundle_file = Path(candidates[0]["path"])

    try:
        snapshot = bundle_snapshot_state(args.bundle_file)
    except Exception as exc:
        raise SystemExit(f"Unable to validate bundle file '{args.bundle_file}': {exc}") from exc
    if str(snapshot.get("state", "")).lower() == "broken":
        raise SystemExit(
            "Refusing to submit broken bundle: dependency graph or bundle structure is invalid. "
            "Inspect with `autoslurm status` or `autoslurm inspect` and rebuild the bundle."
        )

    machine_name, config = machine_config(args)
    submit_jobs(
        args.name,
        machine=machine_name,
        machine_overrides=config,
        bundle_path=args.bundle_file,
    )
