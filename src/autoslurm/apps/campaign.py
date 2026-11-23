"""Human-readable campaign discovery and exact record grouping."""
import argparse
import json

from ..campaign_records import create_campaign, load_campaign, list_campaigns
from ..errors import DiagnosticError
from .error_output import exit_with_error


def main(argv=None):
    parser = argparse.ArgumentParser(prog='asl campaign', description=__doc__)
    actions = parser.add_subparsers(dest='action')
    listing = actions.add_parser('list', help='Discover controller-local campaigns without connecting.')
    show = actions.add_parser('show', help='Read an exact campaign definition without connecting.')
    show.add_argument('name')
    create = actions.add_parser('create', help='Group one or two exact existing bundles without submitting.')
    create.add_argument('name')
    create.add_argument('--member', action='append', nargs=3, required=True, metavar=('MEMBER','MACHINE','BUNDLE_PATH'))
    create.add_argument('--context', default='')
    for command in (listing, show, create):
        command.add_argument('--json', action='store_true')
        command.add_argument('--debug', action='store_true')
    args = parser.parse_args(argv)
    if not args.action:
        parser.print_help()
        return
    try:
        if args.action == 'list':
            result = list_campaigns()
        elif args.action == 'show':
            result = load_campaign(args.name)
        else:
            result = create_campaign(args.name, [{'member_id': item[0], 'machine': item[1], 'bundle_path': item[2]}
                for item in args.member], context=args.context)
    except DiagnosticError as error:
        exit_with_error(error, json_output=args.json, debug=args.debug)
    if args.json:
        print(json.dumps(result, indent=2))
    elif isinstance(result, list):
        if not result:
            print('No saved campaigns found on this controller.')
        for row in result:
            print(f"{row['name']}: {row['state']}  {row['campaign_path']}")
            if row.get('diagnostic'):
                print('  ' + row['diagnostic']['summary'])
    else:
        print(f"Campaign {result['name']} ({result['campaign_id']})")
        if result['context']:
            print(result['context'])
        for member in result['members']:
            print(f"  {member['member_id']} on {member['machine']}: {member['bundle_ref']}")
