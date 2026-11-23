"""Presentation of connection reachability, not scientific readiness."""
import argparse
import json

from ..connections import check_connections
from ..errors import DiagnosticError
from .error_output import exit_with_error


def main(argv=None):
    parser = argparse.ArgumentParser(prog='asl connection', description=__doc__)
    actions = parser.add_subparsers(dest='action')
    check = actions.add_parser('check', help='Probe configured SSH connections without prompting.')
    selection = check.add_mutually_exclusive_group()
    selection.add_argument('--machine')
    selection.add_argument('--all', action='store_true', dest='all_machines')
    check.add_argument('--json', action='store_true')
    check.add_argument('--debug', action='store_true')
    args = parser.parse_args(argv)
    if not args.action:
        parser.print_help()
        return
    try:
        result = check_connections(args.machine, all_machines=args.all_machines)
    except DiagnosticError as error:
        exit_with_error(error, json_output=args.json, debug=args.debug)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        for row in result['machines']:
            print(f"{row['machine']}: {row['state']} (from this controller at {row['observed_at']})")
            if row['diagnostic']:
                print('  ' + row['diagnostic']['next_action'])
    if result['state'] != 'observed':
        raise SystemExit(1)
