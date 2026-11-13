"""Direct terminal interface to shared execution-log inspection."""

import argparse
import json
import sys

from ..inspection import inspect_bundles
from ..submission import load_submission
from .inspection_selection import resolve_job_selection
from .status import _build_reference_date, _selected_paths, _status_rows


def main(argv=None):
    parser = argparse.ArgumentParser(prog='asl logs', description='Read job stdout/stderr with status, exit codes and failure reasons.')
    parser.add_argument('bundle', nargs='*', help='Bundle name/index from asl status; supports ranges like 1-3.')
    parser.add_argument('--latest', '-l', action='store_true', help='Read the latest visible saved bundle.')
    parser.add_argument('--view', action='store_true', help='List bundles with the same indices as asl status.')
    parser.add_argument('--date', help='Select the snapshot nearest this timestamp, as in asl status.')
    for field in ('year', 'month', 'day', 'hour', 'minute', 'second'):
        parser.add_argument('--' + field, type=int, help=f'Reference {field} for historical selection.')
    selected = parser.add_mutually_exclusive_group()
    selected.add_argument('--bundle-file', help='Exact saved submission snapshot.')
    selected.add_argument('--receipt', help='Exact local submission receipt.')
    parser.add_argument('--job', help='Job name or one-based row index from asl status BUNDLE (with --array for expanded rows).')
    parser.add_argument('--array', nargs='*', metavar='TASK', help='Use expanded array row indices; optionally filter task indices/ranges, as in asl status.')
    parser.add_argument('--task', '--array-task', type=int, help='Exact Slurm array task index, rather than a display row.')
    parser.add_argument('--stream', choices=('both', 'stdout', 'stderr'), default='both')
    parser.add_argument('--tail', type=int, default=40, help='Last N lines, within the byte limit (default 40).')
    parser.add_argument('--max-bytes', type=int, default=65536, help='Bytes read per log, 1..1048576 (default 65536).')
    parser.add_argument('--max-logs', type=int, default=20, help='Maximum log files per run, 1..100 (default 20).')
    freshness = parser.add_mutually_exclusive_group()
    freshness.add_argument('--cached', action='store_true', help='Read cached evidence only, without cluster or source-log access.')
    freshness.add_argument('--refresh', action='store_true', help='Refresh status and log excerpts (the default).')
    parser.add_argument('--json', action='store_true', help='Print the shared structured evidence.')
    argv = sys.argv[1:] if argv is None else list(argv)
    if not argv:
        parser.print_help()
        return
    args = parser.parse_args(argv)
    if sum((bool(args.bundle), args.latest, args.bundle_file is not None, args.receipt is not None)) > 1:
        parser.error('Choose one bundle selector: name/index, latest, bundle-file or receipt.')
    if args.view:
        if args.bundle or args.latest or args.bundle_file or args.receipt or args.job or args.task is not None or args.array is not None:
            parser.error('--view lists bundles; choose a bundle separately to read logs.')
        from .status import main as status_main
        forwarded = ['--cached'] if args.cached else []
        for field in ('date', 'year', 'month', 'day', 'hour', 'minute', 'second'):
            value = getattr(args, field)
            if value is not None:
                forwarded.extend(['--' + field, str(value)])
        if args.json:
            forwarded.append('--json')
        return status_main(forwarded)
    if not args.bundle and not args.latest and not args.bundle_file and not args.receipt:
        parser.error('Select a bundle name/index from asl status, or use --latest. Use --view to list bundles.')
    try:
        reference = _build_reference_date(args.date, args.year, args.month, args.day, args.hour, args.minute, args.second)
        if args.receipt:
            paths = [load_submission(args.receipt)['bundle_path']]
        elif args.bundle_file:
            paths = [args.bundle_file]
        else:
            entries = _status_rows(reference)
            if args.latest:
                if not entries:
                    print('No saved bundles found.')
                    return
                paths = [entries[0]['path']]
            else:
                paths = _selected_paths(args.bundle, entries, parser, reference)
        job_name, task_index, array_tasks = resolve_job_selection(paths, args.job, args.array, args.task, parser)
        views = inspect_bundles(paths, job_name=job_name, task_index=task_index,
                               task_indices=array_tasks if task_index is None else None,
                               include_logs=True, stream=args.stream, tail=args.tail,
                               max_log_bytes=args.max_bytes, max_logs=args.max_logs, refresh=not args.cached)
    except (ValueError, RuntimeError, OSError, argparse.ArgumentTypeError) as error:
        print(json.dumps({'state': 'error', 'error': str(error)}) if args.json else str(error))
        raise SystemExit(1) from None
    if args.json:
        print(json.dumps(views[0] if len(views) == 1 else views, indent=2))
    else:
        for view in views:
            _print_view(view, job_name, task_index, array_tasks, show_identity=len(views) > 1)
    if any(view['errors'] for view in views):
        raise SystemExit(1)


def _print_view(view, job_name, task_index, array_tasks, *, show_identity=False):
    if show_identity:
        print(view['bundle_path'])
    print(f"Run: {view['state']} ({view['freshness']})")
    for job in view['jobs']:
        if job_name is not None and job['name'] != job_name:
            continue
        for task in job['tasks']:
            if task_index is not None and task['task_index'] != task_index:
                continue
            if array_tasks is not None and job['is_array'] and task['task_index'] not in array_tasks:
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
