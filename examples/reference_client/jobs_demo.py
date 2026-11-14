"""Submit-side client glue using only supported AutoSlurm APIs.

Planning/validation are local; preview explicitly performs normal readiness
checks. This command never submits. Scientific commands do not import this file.
"""

import argparse
from contextlib import redirect_stdout
import json
from pathlib import PurePosixPath
import sys

from autoslurm import from_typer, load_bundle_from_path, preview_bundle, save_bundle
from typed_science_demo import shard_app, reduce_app


def command_contracts():
    return {
        'shards': from_typer(shard_app, script='science-typed-shard', input_args=('input_file',)),
        'reduce': from_typer(reduce_app, script='science-typed-reduce', input_args=('input_file',), path_args=('parts_dir',)),
    }


def build_bundle(*, input_file, output_dir):
    commands = command_contracts()
    base = PurePosixPath(output_dir)
    return {
        'shards': commands['shards'].job(name='shards',
            script_args={'input_file': input_file, 'output_dir': str(base / 'parts')},
            slurm={'array': '0-3%2', 'time': '00:01:00', 'cpus_per_task': 1, 'mem': '64M'}),
        'reduce': commands['reduce'].job(name='reduce',
            script_args={'input_file': input_file, 'output_dir': str(base / 'summary'), 'parts_dir': str(base / 'parts')},
            dependencies=('shards',), slurm={'time': '00:01:00', 'cpus_per_task': 1, 'mem': '64M'}),
    }


def validate_saved_bundle(path):
    commands = command_contracts()
    jobs, _, _ = load_bundle_from_path(path)
    checked = {}
    for job in jobs:
        if job['name'] not in commands:
            raise ValueError(f"Unknown reference-client job {job['name']!r}; no trusted contract is registered.")
        checked[job['name']] = commands[job['name']].validate_job(job)
    if set(checked) != set(commands):
        raise ValueError('The reference workflow requires both shards and reduce jobs.')
    if checked['shards'].get('dependencies') or checked['reduce'].get('dependencies') != ['shards']:
        raise ValueError('The reference reducer must depend on shards.')
    return checked


def main(argv=None):
    parser = argparse.ArgumentParser(description='Plan, revalidate or preview a typed scientific bundle. Never submits.')
    actions = parser.add_subparsers(dest='action')
    plan = actions.add_parser('plan', help='Save a local four-shard/reducer plan; no cluster contact.')
    plan.add_argument('--bundle', default='typed-array')
    plan.add_argument('--input-file', default='data/measurements.json')
    plan.add_argument('--output-dir', default='typed-array')
    for action in ('validate', 'preview'):
        child = actions.add_parser(action)
        child.add_argument('--bundle-path', required=True)
        if action == 'preview':
            child.add_argument('--machine')
    args = parser.parse_args(argv)
    if args.action is None:
        parser.print_help()
        return 0
    try:
        if args.action == 'plan':
            jobs = build_bundle(input_file=args.input_file, output_dir=args.output_dir)
            with redirect_stdout(sys.stderr):
                path = save_bundle(jobs, args.bundle)
            result = {'bundle_path': str(path), 'jobs': jobs}
        else:
            jobs = validate_saved_bundle(args.bundle_path)
            result = {'bundle_path': args.bundle_path, 'jobs': jobs}
            if args.action == 'preview':
                result = preview_bundle(args.bundle_path, machine=args.machine)
        print(json.dumps(result, indent=2))
    except (OSError, ValueError) as error:
        parser.exit(1, f'science-jobs: {error}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
