"""Terminal presentation for explicit preparation and software inspection."""

import argparse
import json
import sys

from ..software_status import inspect_software
from ..software_requirements import software_expectations
from ..software_preparation import prepare_software, inspect_software_release
from ..software_sources import SoftwarePreparationError


def main(argv=None):
    parser = argparse.ArgumentParser(prog="asl software", description="Prepare isolated application releases or inspect software on a configured machine.")
    actions = parser.add_subparsers(dest="action")
    prepare = actions.add_parser("prepare", help="Build a new application release without changing the scientific dependency base.")
    source = prepare.add_mutually_exclusive_group()
    source.add_argument("--bundle-file", help="Saved bundle with a shared software request.")
    source.add_argument("--local-project", help="Infer project name/Git origin; local edits are not uploaded.")
    prepare.add_argument("--revision", help="Commit, branch or tag for --local-project; omitted means fresh upstream HEAD.")
    prepare.add_argument("--machine", help="Configured machine; defaults to the selected machine.")
    prepare.add_argument("--json", action="store_true", help="Print structured preparation evidence.")
    status = actions.add_parser("status", help="Read project branches, commits and working-tree changes.")
    status.add_argument("--machine", help="Configured machine; defaults to the selected machine.")
    status.add_argument("--project", help="Project path relative to the machine's software_root; omit to list projects.")
    status.add_argument("--limit", type=int, default=20, help="Maximum projects to inspect (1–100).")
    status.add_argument("--json", action="store_true", help="Print structured observation evidence.")
    status.add_argument("--release", help="Inspect an exact preparation ID using its original root and SSH alias.")
    status.add_argument("--verify", action="store_true", help="Recheck a selected release's installation and Python dependencies.")
    status.add_argument("--local-project", help="Local project directory: read pyproject/requirements and desired Git revision.")
    status.add_argument("--requirements", help="Local requirements/constraints file to compare against the target environment.")
    status.add_argument("--package", help="Application distribution name; inferred from --local-project when supplied.")
    status.add_argument("--expected-version", help="Desired installed application version; defaults to local pyproject version.")
    status.add_argument("--expected-commit", help="Desired full application Git commit; defaults to local project HEAD.")
    status.add_argument("--dependency", action="append", default=[], help="Additional important dependency to check (repeatable).")
    argv = sys.argv[1:] if argv is None else list(argv)
    if not argv:
        parser.print_help()
        return
    args = parser.parse_args(argv)
    if args.action == 'prepare':
        if not args.bundle_file and not args.local_project:
            prepare.print_help()
            print('\nChoose --bundle-file PATH or --local-project PATH to prepare software.')
            return
        return _prepare(args)
    if args.action == 'status' and len(argv) == 1:
        status.print_help()
        return
    if args.release:
        if any((args.project, args.local_project, args.requirements, args.package, args.expected_version, args.expected_commit, args.dependency)):
            parser.error('--release is an exact preparation inspection; use project/dependency status separately.')
        return _release_status(args)
    if args.verify:
        parser.error('--verify requires --release ID.')
    try:
        expectations = None
        if args.local_project or args.requirements or args.package or args.expected_version or args.expected_commit or args.dependency:
            expectations = software_expectations(local_project=args.local_project, requirements=args.requirements,
                                                 package=args.package, expected_version=args.expected_version,
                                                 expected_commit=args.expected_commit, dependencies=args.dependency)
        result = inspect_software(machine=args.machine, project=args.project, limit=args.limit, expectations=expectations)
    except (ValueError, RuntimeError, OSError) as error:
        if args.json:
            print(json.dumps({"state": "unavailable", "machine": args.machine, "error": str(error)}))
        else:
            print(str(error))
        raise SystemExit(1) from error
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Software on {result['machine']}: {result['software_root']}")
        print(f"Observed: {result['observed_at']}")
        if result["state"] != "observed":
            print(f"  {result['state']}: {result.get('error', 'Software directory does not exist.')}")
        elif not result["projects"]:
            print("  No Git projects found at this location.")
        for project in result["projects"]:
            state = ("bare cache" if project.get("bare") else "changed" if project["dirty"] else "clean") if project["state"] == "observed" else project["state"]
            commit = (project.get("commit") or "unknown")[:12]
            branch = project.get("branch") or ("detached" if project.get("commit") else "unknown")
            print(f"  {project['name']}: {branch}  {commit}  {state}")
            if project.get("error"):
                print(f"    {project['error']}")
        if result["truncated"]:
            print("  Additional projects were omitted; use --project or increase --limit.")
        if "compatibility" in result:
            print(f"Environment compatibility: {result['compatibility']['state']}")
            environment = result.get("environment", {})
            if environment.get("python"):
                print(f"  Python: {environment['python']}")
            for name, package in environment.get("packages", {}).items():
                if package.get("state") == "installed":
                    print(f"  Installed {name}: {package['version']}")
            for check in result["compatibility"]["checks"]:
                details = f" ({check['requirement']}; installed {check.get('installed') or 'unknown'})" if check.get("requirement") else ""
                print(f"  {check['state']}: {check['name']}: {check['message']}{details}")
            print("  Metadata comparison only; scientific imports, GPU support and minor/transitive dependencies are not checked.")
    if result["state"] != "observed" or any(project["state"] != "observed" for project in result["projects"]):
        raise SystemExit(1)
    if result.get("compatibility", {}).get("state") in {"potential_problem", "unknown"}:
        raise SystemExit(1)


def _show_release(result, structured):
    if structured:
        print(json.dumps(result, indent=2))
        return
    release_id = result['release_id']
    print(f"Software release {release_id}: {result['state']}")
    for project in result.get('projects', []):
        print(f"  {project['name']}: {project['commit']}  {project.get('distribution', '')} {project.get('version', '')}")
    if result.get('installation'):
        print(f"  Installation: {result['installation']}")
    if result.get('error'):
        print('  ' + result['error']['message'])
    if result.get('observation', {}).get('state') == 'unavailable':
        print('  Observation unavailable; saved state may be stale.')
    if result.get('verification'):
        print('  Verification: ' + result['verification']['state'])
        for error in result['verification']['errors']:
            print('    ' + error)
    print(f"Inspect: asl software status --release {release_id} --verify")
    if result['state'] == 'ready':
        print(f"Select for jobs: asl submit --bundle-file PATH --software-release {release_id}")


def _prepare(args):
    try:
        result = prepare_software(machine=args.machine, bundle_path=args.bundle_file,
                                  local_project=args.local_project, revision=args.revision,
                                  on_created=(None if args.json else lambda identity: print(
                                      f'Preparing software release {identity}. Inspect with: asl software status --release {identity}',
                                      file=sys.stderr, flush=True)))
    except SoftwarePreparationError as error:
        _show_release(error.evidence, args.json)
        raise SystemExit(1) from None
    except (ValueError, RuntimeError, OSError, KeyError) as error:
        print(json.dumps({'state': 'failed', 'error': str(error)}) if args.json else str(error))
        raise SystemExit(1) from None
    _show_release(result, args.json)


def _release_status(args):
    try:
        result = inspect_software_release(args.release, machine=args.machine, verify=args.verify)
    except (ValueError, RuntimeError, OSError) as error:
        print(json.dumps({'state': 'unavailable', 'error': str(error)}) if args.json else str(error))
        raise SystemExit(1) from None
    _show_release(result, args.json)
    if (result['state'] != 'ready' or result['observation']['state'] != 'observed'
            or (args.verify and result.get('verification', {}).get('state') != 'verified')):
        raise SystemExit(1)
