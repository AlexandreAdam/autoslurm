import contextlib
import io
import json
import subprocess
from pathlib import Path

import pytest

from autoslurm import create_campaign,inspect_campaign,fetch_campaign,save_config,execute_acp
from autoslurm.apps import root
from autoslurm.execution import resolve_execution_context
from autoslurm.errors import InvalidRequestError
from autoslurm.storage import jobs_dir,storage_root
from tests.inspection_helpers import remote_observation


@pytest.fixture
def campaign(tmp_path,monkeypatch):
    members=[];paths={};calls=[];state={'offline':None}
    for machine in ['rusty','popeye']:
        directory=tmp_path/machine;(directory/'out').mkdir(parents=True)
        job={'name':'work','machine':machine,'script':'science','id':'101','slurm':{'array':'0-2'}}
        context=resolve_execution_context(machine,{'ssh_alias':machine,'path':str(directory)})
        job['_autoslurm_execution']=context.resolve_job(job)
        path=jobs_dir()/(machine+'_20261123000000.json');path.write_text(json.dumps({'work':job}));paths[machine]=path
        members.append({'member_id':machine+'-share','machine':machine,'bundle_path':str(path)})
        for index in range(3):(directory/'out'/f'work-101_{index}.out').write_text(machine+' progress\n')
    create_campaign('study',members,context='why this split')
    def run(command,**kwargs):
        calls.append((command,kwargs));machine=command[-2]
        assert 'BatchMode=yes' in command and kwargs['timeout']<=30
        if state['offline']==machine:return subprocess.CompletedProcess(command,255,'','route unavailable')
        if command[-1]=='python3 -B -':
            output=io.StringIO()
            with contextlib.redirect_stdout(output):exec(kwargs['input'],{})
            return subprocess.CompletedProcess(command,0,output.getvalue(),'')
        status='COMPLETED' if machine=='rusty' else 'RUNNING'
        accounting='\n'.join(f'101_{i}|{status}|0:0||101_{i}' for i in range(3))
        return subprocess.CompletedProcess(command,0,remote_observation(accounting=accounting),'')
    monkeypatch.setattr(subprocess,'run',run)
    return paths,calls,state


def test_two_machine_ids_and_recorded_transport_stay_distinct(campaign):
    paths,calls,_=campaign
    save_config({'machines':{'other':{'ssh_alias':'wrong'}},'default_machine':'other'})
    view=inspect_campaign('study')
    assert view['state']=='observed'
    assert [row['view']['state'] for row in view['members']]==['completed','running']
    assert view['fresh_task_counts']['completed']==view['fresh_task_counts']['running']==3
    assert len(calls)==2 and {command[-2] for command,_ in calls}=={'rusty','popeye'}
    assert [row['view']['jobs'][0]['id'] for row in view['members']]==['101','101']


def test_offline_member_keeps_last_known_counts_through_repeated_refresh_and_cache(campaign):
    _,_,state=campaign
    inspect_campaign('study');state['offline']='popeye'
    for refresh in [True,True,False]:
        view=inspect_campaign('study',refresh=refresh)
        rusty,popeye=view['members']
        assert view['state']=='partial' and popeye['last_known_state']=='running'
        assert popeye['last_known_counts']['running']==3 and popeye['last_known_at']
        assert rusty['view']['state']=='completed'
        assert view['fresh_task_counts']['running']==0


def test_fetch_reads_only_bounded_evidence(campaign):
    _,calls,_=campaign
    view=fetch_campaign('study',max_logs=2,max_total_log_bytes=16)
    logs=[l for row in view['members'] for l in row['view']['logs'] if l['state']!='omitted']
    assert len(logs)<=2 and sum(len(l.get('text','').encode()) for l in logs)<=16
    assert {l['job_name'] for l in logs}=={'work'}
    assert len([c for c,_ in calls if c[-1]=='python3 -B -'])==2


def test_cached_has_no_remote_source_or_cache_writes(campaign,monkeypatch):
    _,calls,_=campaign
    fetch_campaign('study');calls.clear()
    def forbidden(*args,**kwargs):pytest.fail('Cached campaign must not fetch/query/write')
    monkeypatch.setattr(subprocess,'run',forbidden)
    monkeypatch.setattr('autoslurm.inspection_cache.InspectionCache.save_observation',forbidden)
    monkeypatch.setattr('autoslurm.inspection_cache.InspectionCache.save_excerpt',forbidden)
    monkeypatch.setattr('autoslurm.log_files.read_log',forbidden)
    monkeypatch.setattr('autoslurm.inspection_receipts.refresh_submission',forbidden)
    result=fetch_campaign('study',refresh=False)
    assert result['cached'] and result['state']=='observed'
    assert result['fresh_task_counts']['completed']==0
    assert any('progress' in log.get('text','') for row in result['members'] for log in row['view']['logs'])
    assert calls==[]


@pytest.mark.parametrize('kwargs',[{'member':'absent'},{'job_name':'work'},{'member':'rusty-share','job_name':'absent'},
    {'member':'rusty-share','job_name':'work','task_index':9},{'task_index':True},{'refresh':1},{'timeout':0},
    {'timeout':float('nan')},{'tail':-1},{'max_logs':21},{'max_log_bytes':65537},{'max_total_log_bytes':262145}])
def test_selectors_and_bounds_validate_before_effects(campaign,kwargs):
    _,calls,_=campaign
    with pytest.raises(InvalidRequestError):fetch_campaign('study',**kwargs)
    assert calls==[]


@pytest.mark.parametrize('fault',['missing','changed','receipt-link','giant-array'])
def test_bad_member_preserves_healthy_neighbour(campaign,fault):
    paths,calls,_=campaign
    path=paths['popeye'];payload=json.loads(path.read_text())
    if fault=='missing':path.unlink()
    else:
        if fault=='changed':payload['work']['script']='different science'
        elif fault=='receipt-link':payload['work']['_autoslurm_submission']={'submission_id':'b'*32,'receipt_path':'/elsewhere'}
        else:payload['work']['slurm']['array']='0-99999999999'
        path.write_text(json.dumps(payload))
    result=inspect_campaign('study')
    assert result['state']=='partial' and result['members'][0]['view']['state']=='completed'
    assert result['members'][1]['view'] is None and result['members'][1]['diagnostic']
    assert len(calls)==1


def test_explicit_member_job_task_uses_shared_pipeline(campaign):
    result=fetch_campaign('study',member='popeye-share',job_name='work',task_index=1)
    assert len(result['members'])==1
    view=result['members'][0]['view']
    assert [t['task_index'] for t in view['jobs'][0]['tasks']]==[1]
    assert all(l['task_index']==1 for l in view['logs'])


def test_partial_cli_json_and_acp_keep_evidence(campaign,capsys):
    _,_,state=campaign;state['offline']='popeye'
    with pytest.raises(SystemExit) as error:root.main(['campaign','inspect','study','--json'])
    assert error.value.code==1
    result=json.loads(capsys.readouterr().out)
    assert result['members'][0]['view']['state']=='completed' and result['state']=='partial'
    assert execute_acp({'action':'inspect_campaign','name':'study'})['result']['state']=='partial'


def test_fetch_refreshes_receipt_before_job_query_without_rebinding(tmp_path,monkeypatch):
    from tests.integration.test_fetch_evidence import run_fixture,transport
    path,receipt,observed=run_fixture(tmp_path,known=False,array=True)
    create_campaign('recover',[{'member_id':'cluster','machine':'cluster','bundle_path':str(path)}])
    calls=transport(monkeypatch,observed)
    result=fetch_campaign('recover',member='cluster',job_name='sample',task_index=7)
    assert result['members'][0]['view']['jobs'][0]['id']=='101'
    assert result['members'][0]['state']=='available'
    assert calls[0][0][-1]=='python3 -B -'
    assert inspect_campaign('recover',refresh=False)['members'][0]['view']


def test_deadline_caps_adapters_and_preserves_other_member(campaign,monkeypatch):
    _,calls,_=campaign
    import autoslurm.observation_deadline as deadline
    original=subprocess.run;clock=[0.0]
    monkeypatch.setattr(deadline.time,'monotonic',lambda:clock[0])
    def slow(command,**kwargs):
        if command[-2]=='rusty':
            clock[0]+=kwargs['timeout']+.01
            raise subprocess.TimeoutExpired(command,kwargs['timeout'])
        return original(command,**kwargs)
    monkeypatch.setattr(subprocess,'run',slow)
    result=inspect_campaign('study',timeout=1)
    assert result['state']=='partial' and result['members'][1]['view']['state']=='running'
    assert all(kwargs['timeout']<=1 for _,kwargs in calls)
    assert deadline.remaining_timeout(30)==30


def test_large_details_keep_counts_and_mark_omission(campaign):
    paths,_,_=campaign
    # A fresh campaign is required for altered definitions.
    for path in paths.values():
        data=json.loads(path.read_text());data['work']['slurm']['array']='0-999';path.write_text(json.dumps(data))
    create_campaign('large',[{'member_id':m,'machine':m,'bundle_path':str(p)} for m,p in paths.items()])
    result=inspect_campaign('large')
    assert result['details_truncated']
    assert all(row['view']['jobs'][0]['tasks_omitted']==750 for row in result['members'])
    assert len(json.dumps(result).encode())<=2*1024*1024


def test_never_observed_cached_campaign_is_explicitly_partial(campaign):
    _,calls,_=campaign
    result=inspect_campaign('study',refresh=False)
    assert result['state']=='partial' and calls==[]
    assert all(row['view']['freshness']=='never' for row in result['members'])


def test_member_change_during_observation_is_not_attributed(campaign,monkeypatch):
    paths,_,_=campaign;original=subprocess.run
    def run(command,**kwargs):
        result=original(command,**kwargs)
        if command[-2]=='rusty':
            payload=json.loads(paths['rusty'].read_text());payload['work']['script']='changed'
            paths['rusty'].write_text(json.dumps(payload))
        return result
    monkeypatch.setattr(subprocess,'run',run)
    result=inspect_campaign('study')
    assert result['members'][0]['view'] is None
    assert result['members'][0]['unverified_observation']['jobs'][0]['id']=='101'
    assert result['members'][1]['view']['state']=='running'


def test_exhausted_deadline_labels_unvisited_member(campaign,monkeypatch):
    _,_,_=campaign
    import autoslurm.observation_deadline as deadline
    original=subprocess.run;clock=[0.0]
    monkeypatch.setattr(deadline.time,'monotonic',lambda:clock[0])
    def run(command,**kwargs):
        result=original(command,**kwargs);clock[0]=5.0;return result
    monkeypatch.setattr(subprocess,'run',run)
    result=inspect_campaign('study',timeout=1)
    assert result['members'][1]['state']=='not_attempted'
    assert result['members'][0]['view'] is not None


def test_coordinator_does_not_hide_unexpected_bugs(campaign,monkeypatch):
    def bug(*args,**kwargs):raise TypeError('programming bug')
    monkeypatch.setattr('autoslurm.campaigns.inspect_bundle',bug)
    with pytest.raises(TypeError,match='programming bug'):inspect_campaign('study')
    with pytest.raises(TypeError,match='programming bug'):execute_acp({'action':'inspect_campaign','name':'study'})


def test_large_array_rejected_before_expanding_or_querying(campaign):
    paths,calls,_=campaign
    path=paths['rusty'];payload=json.loads(path.read_text());payload['work']['slurm']['array']='0-99999999999';path.write_text(json.dumps(payload))
    create_campaign('huge',[{'member_id':'rusty','machine':'rusty','bundle_path':str(path)}])
    result=inspect_campaign('huge')
    assert result['members'][0]['diagnostic'] and calls==[]


def test_response_byte_limit_preserves_ids_and_counts():
    from autoslurm.campaign_projection import campaign_view
    rows=[]
    counts={'completed':100,'failed':0,'cancelled':0,'pending':0,'running':0,'unknown':0,'not_submitted':0}
    for machine in ['rusty','popeye']:
        jobs=[{'name':f'job{i}','id':str(i),'state':'COMPLETED','counts':counts.copy(),
               'tasks':[{'state':'COMPLETED','reason':'x'*8192} for _ in range(100)]} for i in range(30)]
        rows.append({'member_id':machine,'machine':machine,'state':'available',
            'view':{'jobs':jobs,'state':'completed','freshness':'fresh','observed_at':'now','errors':[],'logs':[]}})
    record={'name':'test','campaign_id':'a'*32,'revision':1,'context':''}
    result=campaign_view(record,rows,refresh=True)
    assert len(json.dumps(result).encode())<=2*1024*1024
    assert result['fresh_task_counts']['completed']==6000
    assert len(result['members'][0]['view']['jobs'])==30
    assert result['details_truncated']


def test_utf8_log_content_respects_global_bytes(campaign):
    paths,_,_=campaign
    for path in paths.values():
        payload=json.loads(path.read_text())
        directory=Path(payload['work']['_autoslurm_execution']['storage_root'])/'out'
        for log in directory.glob('*.out'):log.write_bytes(b'\xff'*100)
    result=fetch_campaign('study',max_logs=2,max_total_log_bytes=20)
    assert sum(len(log.get('text','').encode()) for row in result['members'] for log in row['view']['logs'])<=20
    assert result['details_truncated']


def test_bad_prior_job_counts_are_not_accepted_as_cached_truth(campaign):
    inspect_campaign('study')
    from autoslurm.inspection_cache import InspectionCache
    from autoslurm.inspection_collection import load_run
    paths,_,_=campaign
    path=InspectionCache(storage_root()).observation_path(paths['rusty'])
    payload=json.loads(path.read_text());payload['jobs'][0]['counts']['completed']=10**100
    path.write_text(json.dumps(payload))
    result=inspect_campaign('study',refresh=False)
    assert result['state']=='partial' and result['members'][0]['last_known_counts']['completed']==0
