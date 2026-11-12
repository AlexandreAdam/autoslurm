"""Terminal presentation for in-place Git updates and read-only inspection."""

import argparse
import json
import sys

from ..software_status import inspect_software
from ..software_requirements import software_expectations
from ..software_update import update_software, SoftwareUpdateError


def main(argv=None):
    parser = argparse.ArgumentParser(prog="asl software", description="Update an existing Git checkout or inspect machine software.")
    actions = parser.add_subparsers(dest="action")
    update = actions.add_parser("update", help="Run git pull --ff-only in one existing project; creates no code copies.")
    update.add_argument("--machine", help="Configured machine; defaults to the selected machine.")
    update.add_argument("--project", help="Existing checkout relative to software_root (required for updates).")
    update.add_argument("--json", action="store_true", help="Print structured before/after commit evidence.")
    status = actions.add_parser("status", help="Read project branches, commits and working-tree changes.")
    status.add_argument("--machine", help="Configured machine; defaults to the selected machine.")
    status.add_argument("--project", help="Project path relative to the machine's software_root; omit to list projects.")
    status.add_argument("--limit", type=int, default=20, help="Maximum projects to inspect (1–100).")
    status.add_argument("--json", action="store_true", help="Print structured observation evidence.")
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
    if args.action == 'update':
        if not args.project:
            update.print_help()
            print('\nChoose --project PATH to update an existing checkout.')
            return
        return _update(args)
    if args.action == 'status' and len(argv) == 1:
        status.print_help()
        return
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



def _update(args):
    try:
        result = update_software(machine=args.machine, project=args.project)
    except SoftwareUpdateError as error:
        if args.json:
            print(json.dumps(error.evidence, indent=2))
        else:
            print(str(error))
            if error.evidence.get('after_commit'):
                print('Current commit: ' + error.evidence['after_commit'])
            print(f'Inspect: asl software status --machine {args.machine or error.evidence["machine"]} --project {args.project}')
        raise SystemExit(1) from None
    except (ValueError, RuntimeError, OSError) as error:
        print(json.dumps({'state': 'failed', 'error': str(error)}) if args.json else str(error))
        raise SystemExit(1) from None
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        state = 'Updated' if result['state'] == 'updated' else 'Already up to date'
        print(f'{state}: {result["machine"]}/{result["project"]} ({result["branch"]})')
        print(f'  {result["before_commit"]} -> {result["after_commit"]}')
