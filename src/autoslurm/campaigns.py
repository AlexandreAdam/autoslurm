"""Campaign observation composes existing run/receipt/status/log services."""
from datetime import datetime, timezone
import math
import re
import time

from .campaign_records import load_campaign, _member_definition, _invalid
from .campaign_projection import campaign_view, _counts
from .errors import DiagnosticError, _campaign_failure
from .inspection import inspect_bundle, fetch_run
from .array_status import declared_array_indices
from .observation_deadline import observation_deadline

__all__ = ['inspect_campaign','fetch_campaign']


def _check_workload(payload):
    # Validate before any array-expanding projection, without enumerating ranges.
    if len(payload) > 200:
        raise _invalid('Campaign detail currently supports at most 200 jobs per member.', field='jobs')
    total = 0
    for name, job in payload.items():
        if len(name.encode('utf-8')) > 128 or len(str(job.get('id') or '')) > 64:
            raise _invalid('Campaign job names/IDs exceed the detail limits.', field='jobs')
        if job.get('slurm') is not None and not isinstance(job['slurm'], dict):
            raise _invalid('Saved Slurm options must be a mapping.', field='slurm')
        if job.get('id') is not None and '_autoslurm_execution' not in job:
            raise _invalid('Submitted campaign members need recorded producing metadata; current-profile routing is not inferred.', field='execution')
        spec = (job.get('slurm') or {}).get('array')
        if spec is None:
            total += 1
            continue
        if not isinstance(spec, (str,int)) or type(spec) is bool or len(str(spec)) > 4096:
            raise _invalid('Array indices must use the documented Slurm syntax.', field='array')
        count = 0
        for part in str(spec).split('%',1)[0].split(','):
            match = re.fullmatch(r'(\d+)(?:-(\d+)(?::(\d+))?)?', part.strip())
            if not match:
                raise _invalid('Array indices must use the documented Slurm syntax.', field='array')
            if any(len(value) > 10 for value in match.groups() if value):
                raise _invalid('Campaign detail supports bounded integer array indices.', field='array')
            start = int(match[1]); end = int(match[2] or match[1]); step = int(match[3] or 1)
            if end < start or step < 1 or end > 2147483647:
                raise _invalid('Array range or step is invalid.', field='array')
            count += (end-start)//step+1
        total += count
        if total > 10000:
            raise _invalid('Select a smaller saved workload; campaign observation is limited to 10000 declared tasks per member.', field='array')


def _observe(name, *, refresh=True, member=None, job_name=None, task_index=None,
             include_logs=False, tail=40, max_log_bytes=65536, max_logs=20,
             max_total_log_bytes=262144, stream='both', timeout=120):
    if type(refresh) is not bool or type(timeout) not in (int,float) or not math.isfinite(timeout) or not 0 < timeout <= 120:
        raise _invalid('Use a boolean refresh and a finite timeout greater than zero up to 120 seconds.', field='refresh/timeout')
    if member is not None and (not isinstance(member,str) or not member):
        raise _invalid('Select an exact member identity.', field='member')
    if (job_name is not None or task_index is not None) and member is None:
        raise _invalid('Select a member before narrowing job/task evidence.', field='member')
    if job_name is not None and (not isinstance(job_name,str) or not job_name):
        raise _invalid('Select a nonempty job name.', field='job_name')
    if task_index is not None and (type(task_index) is not int or task_index < 0 or job_name is None):
        raise _invalid('Select a named job and a nonnegative integer array index.', field='task_index')
    if (type(tail) is not int or not 0 <= tail <= 1000 or type(max_log_bytes) is not int or not 1 <= max_log_bytes <= 65536
        or type(max_logs) is not int or not 1 <= max_logs <= 20 or type(max_total_log_bytes) is not int
        or not 1 <= max_total_log_bytes <= 262144 or stream not in ('both','stdout','stderr')):
        raise _invalid('Campaign bounds: tail 0..1000, bytes 1..65536, logs 1..20, total log bytes 1..262144 and a valid stream.', field='log_bounds')
    record = load_campaign(name)
    members = [m for m in record['members'] if member is None or m['member_id'] == member]
    if not members:
        raise _invalid('The selected member is absent from this exact campaign.', field='member')
    plans = []
    # All selector checks happen before receipt refresh or remote observations.
    for item in members:
        try:
            path,payload = _member_definition(item,record['campaign_path'])
            _check_workload(payload)
        except DiagnosticError as error:
            plans.append((item,None,None,error.diagnostic.to_dict()))
            continue
        if job_name is not None and job_name not in payload:
            raise _invalid('The selected job is absent from this member definition.', field='job_name')
        if task_index is not None:
            indices = declared_array_indices((payload[job_name].get('slurm') or {}).get('array'))
            if indices is None or task_index not in indices:
                raise _invalid('The selected task is absent from the declared array.', field='task_index')
        plans.append((item,path,payload,None))
    end = time.monotonic() + timeout
    remaining_logs = max_logs; remaining_bytes = max_total_log_bytes
    rows = []
    clipped = False
    with observation_deadline(timeout):
        for index,(item,path,payload,error) in enumerate(plans):
            row = {'member_id':item['member_id'],'machine':item['machine'],
                   'bundle_path':str(path) if path else None,'state':'unavailable','diagnostic':error,'view':None}
            rows.append(row)
            if error:
                continue
            remaining = end - time.monotonic()
            if refresh and remaining <= 0:
                row['state']='not_attempted'
                row['diagnostic']=_campaign_failure('Campaign observation deadline reached; member was not attempted.',
                    member=item['member_id'], code='command_timeout', stage='observe_campaign').to_dict()
                continue
            quota = min(remaining_logs, max(1, math.ceil(remaining_logs / (len(plans)-index))))
            byte_limit = min(max_log_bytes, max(1, remaining_bytes // max(1, quota*(len(plans)-index))))
            try:
                with observation_deadline(max(0,remaining)/(len(plans)-index)):
                    if include_logs and quota and remaining_bytes:
                        view = fetch_run(path, refresh=refresh, job_name=job_name, task_index=task_index,
                            tail=tail,max_log_bytes=byte_limit,max_logs=quota,stream=stream)
                    else:
                        view = inspect_bundle(path, refresh=refresh, job_name=job_name, task_index=task_index,
                                              refresh_receipts=refresh and include_logs)
                        if include_logs:
                            view['logs'].append({'state':'omitted','reason':'Campaign log allowance reached.'})
            except DiagnosticError as failure:
                row['diagnostic']=failure.diagnostic.to_dict()
                continue
            # Do not let a source mutation while observing replace the pinned member.
            try:
                _member_definition(item,record['campaign_path'])
            except DiagnosticError as failure:
                row['diagnostic']=failure.diagnostic.to_dict()
                row['unverified_observation'] = {'jobs':[{key:job[key] for key in ('name','id','state')} for job in view['jobs']],
                    'reason':'Definition changed during observation; not attributed to this campaign.'}
                continue
            row['run_task_counts'] = _counts(view['jobs'])
            for log in view.get('logs',[]):
                if log.get('state') != 'omitted':
                    remaining_logs -= 1
                    raw = (log.get('text') or '').encode('utf-8')
                    cap = max(0, min(byte_limit,remaining_bytes))
                    if len(raw) > cap:
                        log['text'] = raw[:cap].decode('utf-8', errors='ignore')
                        log['campaign_truncated'] = True
                        clipped = True
                    remaining_bytes -= len((log.get('text') or '').encode('utf-8'))
            if job_name is not None:
                view['jobs'] = [j for j in view['jobs'] if j['name']==job_name]
                if task_index is not None:
                    for job in view['jobs']:
                        job['tasks']=[t for t in job['tasks'] if t['task_index']==task_index]
            row.update(state='available',view=view)
            clipped |= include_logs and (remaining_logs <= 0 or remaining_bytes <= 0)
    return campaign_view(record,rows,refresh=refresh,clipped=clipped,
                         collected_at=datetime.now(timezone.utc).isoformat())


def inspect_campaign(name, *, refresh=True, member=None, job_name=None, task_index=None, timeout=120):
    """Observe member status, or read caches only with refresh=False."""
    return _observe(name,refresh=refresh,member=member,job_name=job_name,task_index=task_index,timeout=timeout)


def fetch_campaign(name, *, refresh=True, member=None, job_name=None, task_index=None,
                   tail=40,max_log_bytes=65536,max_logs=20,max_total_log_bytes=262144,stream='both',timeout=120):
    """Refresh exact member receipts/status and bounded execution evidence only."""
    return _observe(name,refresh=refresh,member=member,job_name=job_name,task_index=task_index,
        include_logs=True,tail=tail,max_log_bytes=max_log_bytes,max_logs=max_logs,
        max_total_log_bytes=max_total_log_bytes,stream=stream,timeout=timeout)
