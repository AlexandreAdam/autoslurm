"""Human-readable campaign discovery and exact record grouping."""
import argparse
import json

from ..campaigns import inspect_campaign, fetch_campaign
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
    inspect = actions.add_parser('inspect', help='Observe all members or read cached context.')
    fetch = actions.add_parser('fetch', help='Refresh linked receipts/status and bounded execution logs.')
    for command in (inspect, fetch):
        command.add_argument('name')
        command.add_argument('--cached', action='store_true')
        command.add_argument('--member')
        command.add_argument('--job', dest='job_name')
        command.add_argument('--task', type=int, dest='task_index')
        command.add_argument('--timeout', type=float, default=120)
    fetch.add_argument('--tail', type=int, default=40)
    fetch.add_argument('--max-log-bytes', type=int, default=65536)
    fetch.add_argument('--max-logs', type=int, default=20)
    fetch.add_argument('--max-total-log-bytes', type=int, default=262144)
    fetch.add_argument('--stream', choices=('both','stdout','stderr'), default='both')
    for command in (listing, show, create, inspect, fetch):
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
        elif args.action in ('inspect','fetch'):
            options = {'refresh':not args.cached,'member':args.member,'job_name':args.job_name,
                       'task_index':args.task_index,'timeout':args.timeout}
            if args.action == 'fetch':
                options.update(tail=args.tail,max_log_bytes=args.max_log_bytes,max_logs=args.max_logs,
                               max_total_log_bytes=args.max_total_log_bytes,stream=args.stream)
            result = (fetch_campaign if args.action == 'fetch' else inspect_campaign)(args.name,**options)
        else:
            result = create_campaign(args.name, [{'member_id': item[0], 'machine': item[1], 'bundle_path': item[2]}
                for item in args.member], context=args.context)
    except DiagnosticError as error:
        exit_with_error(error, json_output=args.json, debug=args.debug)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, separators=(',',':')))
    elif args.action in ('inspect','fetch'):
        _print_view(result)
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

    if isinstance(result,dict) and result.get('state') == 'partial':
        raise SystemExit(1)


def _print_view(result):
    print(f"Campaign {result['name']}: {result['state']} ({'cached' if result['cached'] else 'refresh'})")
    if result['context']:
        print(result['context'])
    for row in result['members']:
        view = row.get('view')
        print(f"  {row['member_id']} on {row['machine']}: {row['state']}")
        if row.get('diagnostic'):
            print('    ' + row['diagnostic']['summary'])
        if not view: continue
        print(f"    Run: {view['state']}; observation: {view['freshness']} at {view['observed_at'] or 'never'}")
        print(f"    Tasks: {_count_text(row['counts'])}")
        if view.get('last_observed'):
            print(f"    Last known: {row['last_known_state']} at {row['last_known_at']}; tasks: {_count_text(row['last_known_counts'])}")
        for error in view.get('errors',[]):
            print('    ' + error['source'] + ': ' + error['message'])
        for job in view['jobs']:
            print(f"    {job['name']} [{job['id'] or '-'}]: {job['state']}")
            for task in job.get('tasks',[]) if len(job.get('tasks',[])) <= 20 else []:
                if task['task_index'] is not None:
                    print(f"      task {task['task_index']}: {task['state']} reason={task.get('reason') or '-'} exit={task.get('exit_code') or '-'}")
        for log in view.get('logs',[]):
            print(f"    {log.get('job_name','logs')} task={log.get('task_index','-')} {log['state']}")
            if log.get('text'): print(log['text'])
            if log.get('error'): print(log['error'])
    print(result['count_scope'])
    if result['details_truncated']:
        print('Details bounded; select one member/job/task for a narrower view.')


def _count_text(counts):
    return ', '.join(f'{count} {state}' for state,count in (counts or {}).items() if count) or 'none observed'
