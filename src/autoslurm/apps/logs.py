"""Direct terminal interface to shared execution-log inspection."""

import argparse
import json
import sys

from ..inspection import inspect_logs


def main(argv=None):
    parser = argparse.ArgumentParser(prog='asl logs', description='Read job stdout/stderr with status, exit codes and failure reasons.')
    selected = parser.add_mutually_exclusive_group()
    selected.add_argument('--bundle-file', help='Exact saved submission snapshot.')
    selected.add_argument('--receipt', help='Exact local submission receipt.')
    parser.add_argument('--job', help='Job name in the selected run.')
    parser.add_argument('--task', type=int, help='Exact array task index.')
    parser.add_argument('--stream', choices=('both', 'stdout', 'stderr'), default='both')
    parser.add_argument('--tail', type=int, default=40, help='Last N lines, within the byte limit (default 40).')
    parser.add_argument('--max-bytes', type=int, default=65536, help='Bytes read per log, 1..1048576 (default 65536).')
    parser.add_argument('--max-logs', type=int, default=20, help='Maximum log files, 1..100 (default 20).')
    freshness = parser.add_mutually_exclusive_group()
    freshness.add_argument('--cached', action='store_true', help='Read cached evidence only, without cluster or source-log access.')
    freshness.add_argument('--refresh', action='store_true', help='Refresh status and log excerpts (the default).')
    parser.add_argument('--json', action='store_true', help='Print the shared structured evidence.')
    argv = sys.argv[1:] if argv is None else list(argv)
    if not argv:
        parser.print_help()
        return
    args = parser.parse_args(argv)
    if not args.bundle_file and not args.receipt:
        parser.error('Select --bundle-file PATH or --receipt PATH. Bundle/index navigation remains available through asl inspect.')
    try:
        view = inspect_logs(args.bundle_file, receipt_path=args.receipt, job_name=args.job,
                            task_index=args.task, stream=args.stream, tail=args.tail,
                            max_log_bytes=args.max_bytes, max_logs=args.max_logs, refresh=not args.cached)
    except (ValueError, RuntimeError, OSError) as error:
        print(json.dumps({'state': 'error', 'error': str(error)}) if args.json else str(error))
        raise SystemExit(1) from None
    if args.json:
        print(json.dumps(view, indent=2))
    else:
        print(f"Run: {view['state']} ({view['freshness']})")
        for job in view['jobs']:
            if args.job is not None and job['name'] != args.job:
                continue
            for task in job['tasks']:
                if args.task is not None and task['task_index'] != args.task:
                    continue
                print(f"{job['name']} {task['job_id'] or 'not submitted'}: {task['state']}  exit={task.get('exit_code') or 'unknown'}  reason={task.get('reason') or 'unknown'}")
        for log in view['logs']:
            if log['state'] == 'omitted':
                print(f"Logs omitted: {log['count']} ({log['reason']})")
                continue
            streams = '+'.join(log.get('streams', [log.get('stream', 'log')]))
            print(f"{streams}: {log.get('path', 'unresolved path')} [{log['state']}, {log.get('freshness', 'unavailable')}]")
            if log['state'] == 'available':
                print(log['text'] if log['text'] else '(empty)' if log.get('empty') else '(no lines requested)')
                if log.get('truncated'):
                    print('  Excerpt truncated; full log remains at the recorded path.')
                if log.get('changed_during_read'):
                    print('  Log changed during this read; refresh for a newer excerpt.')
            elif log.get('error'):
                print('  ' + log['error'])
        if not view['logs']:
            print('No submitted log identity is available for this selection.')
        for error in view['errors']:
            print(f"{error['source']}: {error['message']}")
    if view['errors']:
        raise SystemExit(1)
