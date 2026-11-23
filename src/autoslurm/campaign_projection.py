"""Pure bounded projection of supplied member evidence; no discovery or commands."""
import copy
import json
from .errors import _text

_CATEGORIES = ('completed','failed','cancelled','running','pending','unknown','not_submitted')
_RESPONSE_BYTES = 2 * 1024 * 1024


def _counts(jobs):
    return {key: sum(job.get('counts', {}).get(key, 0) for job in jobs) for key in _CATEGORIES}


def _bounded(value, key=None, clipped=None):
    if isinstance(value, str):
        limit = 65536 if key == 'text' else 4096
        raw = value.encode('utf-8')
        if len(raw) > limit and clipped is not None:
            clipped[0] = True
        if key != 'text':
            return _text(value, limit=limit, multiline=True)
        return value if len(raw) <= limit else raw[:limit].decode('utf-8', errors='ignore')
    if isinstance(value, dict):
        return {name: _bounded(item, name, clipped) for name, item in value.items()}
    if isinstance(value, list):
        if key == 'errors' and len(value) > 20:
            return [_bounded(item, clipped=clipped) for item in value[:20]] + [{'source':'bounds','message':f'{len(value)-20} additional errors omitted.'}]
        return [_bounded(item, clipped=clipped) for item in value]
    return value


def campaign_view(record, rows, *, refresh, clipped=False, collected_at=None):
    rows = copy.deepcopy(rows)
    for row in rows:
        view = row.get('view')
        row['counts'] = row.pop('run_task_counts', None) or (_counts(view['jobs']) if view else None)
        previous = view.get('last_observed') if view else None
        row['last_known_counts'] = _counts(previous['jobs']) if previous and previous.get('jobs') else row['counts']
        if view:
            row['last_known_state'] = previous['state'] if previous else view['state']
            row['last_known_at'] = previous['observed_at'] if previous else view['observed_at']
            if view['errors'] or view['freshness'] in {'partial','failed','never'}:
                row['state'] = 'partial'
    fresh = [row for row in rows if refresh and row.get('view') and row['view']['freshness'] == 'fresh']
    result = {'name':record['name'], 'campaign_id':record['campaign_id'], 'revision':record['revision'],
        'context':record['context'], 'cached':not refresh, 'collected_at':collected_at, 'members':rows,
        'state':'partial' if any(row['state'] != 'available' for row in rows) else 'observed',
        'fresh_task_counts':{key:sum(row['counts'][key] for row in fresh) for key in _CATEGORIES},
        'last_known_task_counts':{key:sum((row['last_known_counts'] or {}).get(key,0) for row in rows) for key in _CATEGORIES},
        'count_scope':'Scheduler tasks across all member jobs; not unique scientific work or scientific success.',
        'details_truncated':clipped}
    # Keep aggregate task counts, but make bounded details explicit and selectable.
    for row in rows:
        if not row.get('view'): continue
        for source in [row['view'], row['view'].get('last_observed') or {}]:
            budget = 250
            for job in source.get('jobs', []):
                tasks = job.get('tasks', [])
                keep = min(len(tasks), budget)
                job['tasks'] = tasks[:keep]
                job['tasks_omitted'] = len(tasks) - keep
                budget -= keep
                result['details_truncated'] |= bool(job['tasks_omitted'])
    text_clipped = [False]
    result = _bounded(result, clipped=text_clipped)
    result['details_truncated'] |= text_clipped[0]
    if len(json.dumps(result,ensure_ascii=False).encode('utf-8')) > _RESPONSE_BYTES:
        result['details_truncated'] = True
        for row in result['members']:
            if not row.get('view'): continue
            for source in [row['view'], row['view'].get('last_observed') or {}]:
                source['jobs'] = [{key:job[key] for key in ('name','id','state','counts') if key in job}
                                  for job in source.get('jobs', [])]
                source['job_details_omitted'] = True
    # A final compact form retains per-member failure/state/counts and all known IDs.
    if len(json.dumps(result,ensure_ascii=False).encode('utf-8')) > _RESPONSE_BYTES:
        for row in result['members']:
            view = row.get('view')
            if row.get('unverified_observation'):
                row['unverified_observation']['jobs'] = [_minimal_job(job) for job in row['unverified_observation']['jobs']]
            if view:
                row['view'] = {key:view[key] for key in ('state','freshness','observed_at')}
                row['view']['jobs'] = [_minimal_job(job) for job in view['jobs']]
                row['view']['submissions'] = [{key:item.get(key) for key in ('submission_id','receipt_path','state')}
                                              for item in view.get('submissions',[])[:20]]
                row['view']['submissions_omitted'] = max(0,len(view.get('submissions',[]))-20)
                row['view']['errors'] = [{'source':_text(item.get('source','observation'),512),
                    'message':_text(item.get('message','Unavailable detail'),512)} for item in view.get('errors',[])[:3]]
                row['details_omitted'] = 'Response byte limit; select one member/job/task for evidence.'
    return result


def _minimal_job(job):
    return {'name':_text(job['name'],128),'id':_text(job['id'],128) if job.get('id') else None,
            'state':_text(job['state'],128),
            'counts':{key:job.get('counts',{}).get(key,0) for key in _CATEGORIES},
            'details_omitted':True}
