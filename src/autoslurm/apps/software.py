"""Terminal presentation for in-place Git updates and read-only inspection."""

import argparse
import json
import sys

from ..software_status import inspect_software
from ..software_requirements import software_expectations
from ..software_update import update_software, SoftwareUpdateError
from ..errors import ConfigurationError, InvalidRequestError, DiagnosticError, Diagnostic, DiagnosticCause
from .error_output import render_diagnostic, exit_with_error


def main(argv=None):
    parser = argparse.ArgumentParser(prog="asl software", description="Update an existing Git checkout or inspect machine software.")
    actions = parser.add_subparsers(dest="action")
    update = actions.add_parser("update", help="Pull one checkout and refresh its editable install in the configured environment.")
    update.add_argument("--machine", help="Configured machine; defaults to the selected machine.")
    update.add_argument("--project", help="Existing checkout relative to software_root (required for updates).")
    update.add_argument("--json", action="store_true", help="Print structured before/after commit evidence.")
    update.add_argument("--debug", action="store_true", help="Show original software-update errors and causes.")
    status = actions.add_parser("status", help="Read project branches, commits and working-tree changes.")
    status.add_argument("--machine", help="Configured machine; defaults to the selected machine.")
    status.add_argument("--project", help="Project path relative to the machine's software_root; omit to list projects.")
    status.add_argument("--limit", type=int, default=20, help="Maximum projects to inspect (1–100).")
    status.add_argument("--json", action="store_true", help="Print structured observation evidence.")
    status.add_argument('--debug', action='store_true', help='Show original operation failures and native causes.')
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
    except DiagnosticError as error:
        exit_with_error(error, json_output=args.json, debug=args.debug)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Software on {result['machine']}: {result['software_root']}")
        print(f"Observed: {result['observed_at']}")
        if result["state"] != "observed":
            _show_diagnostic(result)
            if not result.get('diagnostic'):
                print(f"  {result['state']}: {result.get('error', 'Software directory does not exist.')}")
        elif not result["projects"]:
            print("  No Git projects found at this location.")
        for project in result["projects"]:
            state = ("bare cache" if project.get("bare") else "changed" if project["dirty"] else "clean") if project["state"] == "observed" else project["state"]
            commit = (project.get("commit") or "unknown")[:12]
            branch = project.get("branch") or ("detached" if project.get("commit") else "unknown")
            print(f"  {project['name']}: {branch}  {commit}  {state}")
            _show_diagnostic(project, indent='    ')
            if project.get('error') and not project.get('diagnostic'):
                print(f"    {project['error']}")
        if result["truncated"]:
            print("  Additional projects were omitted; use --project or increase --limit.")
        if "compatibility" in result:
            print(f"Environment compatibility: {result['compatibility']['state']}")
            environment = result.get("environment", {})
            _show_diagnostic(environment)
            if environment.get("python"):
                print(f"  Python: {environment['python']}")
            for name, package in environment.get("packages", {}).items():
                if package.get("state") == "installed":
                    print(f"  Installed {name}: {package['version']}")
                if package.get('state') != 'missing':
                    _show_diagnostic(package, indent='    ')
            for check in result["compatibility"]["checks"]:
                details = f" ({check['requirement']}; installed {check.get('installed') or 'unknown'})" if check.get("requirement") else ""
                if 'expected' in check:
                    details = f" (expected {check['expected']}; installed {check.get('installed') or 'unknown'})"
                elif 'expected_commit' in check:
                    details = f" (expected {check['expected_commit']}; installed {check.get('installed_commit') or 'unknown'})"
                print(f"  {check['state']}: {check['name']}: {check['message']}{details}")
                _show_diagnostic(check, indent='    ')
            print("  Metadata comparison only; scientific imports, GPU support and minor/transitive dependencies are not checked.")
    if result["state"] != "observed" or any(project["state"] != "observed" for project in result["projects"]):
        raise SystemExit(1)
    environment = result.get('environment', {})
    if (result.get('compatibility', {}).get('state') in {'potential_problem', 'unknown'}
            or environment.get('diagnostic') or any(package.get('state') == 'unavailable'
                for package in environment.get('packages', {}).values())):
        raise SystemExit(1)



def _show_diagnostic(item, *, indent='  '):
    record = item.get('diagnostic')
    if record is None:
        return
    fields = {key: record[key] for key in ('code', 'operation', 'stage', 'context', 'effects', 'summary', 'next_action')}
    fields['cause'] = DiagnosticCause(**record['cause']) if record.get('cause') is not None else None
    print('\n'.join(indent + line for line in render_diagnostic(Diagnostic(**fields)).splitlines()))


def _update(args):
    try:
        result = update_software(machine=args.machine, project=args.project)
    except SoftwareUpdateError as error:
        if args.debug:
            raise
        if args.json:
            print(json.dumps(error.evidence, indent=2))
        else:
            output = sys.stderr if error.diagnostic is not None else sys.stdout
            print(render_diagnostic(error.diagnostic) if error.diagnostic is not None else str(error), file=output)
            if error.evidence.get('after_commit'):
                print('Last observed commit: ' + error.evidence['after_commit'], file=output)
            installation = error.evidence.get('installation')
            if isinstance(installation, dict):
                print(f'Editable install: {installation["state"]} ({installation["python"]})', file=output)
            print(f'Inspect: asl software status --machine {args.machine or error.evidence["machine"]} --project {args.project}', file=output)
        raise SystemExit(1) from None
    except (ConfigurationError, InvalidRequestError) as error:
        exit_with_error(error, json_output=args.json, debug=args.debug)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        state = 'Updated' if result['state'] == 'updated' else 'Already up to date'
        print(f'{state}: {result["machine"]}/{result["project"]} ({result["branch"]})')
        print(f'  {result["before_commit"]} -> {result["after_commit"]}')
        print(f'  Editable install refreshed: {result["installation"]["python"]}')
