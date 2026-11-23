import json
from pathlib import Path

import pytest

from autoslurm import create_campaign, load_campaign, list_campaigns, execute_acp
from autoslurm.apps import root
from autoslurm.errors import DiagnosticError, InvalidRequestError, RecordCollisionError
from autoslurm.storage import jobs_dir, storage_root


def members():
    result=[]
    for machine in ['rusty','popeye']:
        path=jobs_dir()/f'{machine}_20261123000000.json'
        path.write_text(json.dumps({'work':{'name':'work','machine':machine,'id':'101','script':'science','slurm':{}}}))
        result.append({'member_id':machine+'-share','machine':machine,'bundle_path':str(path)})
    return result


def test_create_load_list_and_collision_preserve_exact_records():
    items=members(); originals=[Path(m['bundle_path']).read_bytes() for m in items]
    record=create_campaign('study',items,context='What and why')
    assert load_campaign('study')==record
    assert list_campaigns()[0]['members']==2
    assert record['format_version']==1 and all(not Path(m['bundle_ref']).is_absolute() for m in record['members'])
    with pytest.raises(RecordCollisionError):create_campaign('study',items)
    assert load_campaign('study')==record
    assert [Path(m['bundle_path']).read_bytes() for m in items]==originals


@pytest.mark.parametrize('name',['','../x','/tmp/x','x\n',None,4])
def test_invalid_campaign_name_never_writes(name):
    with pytest.raises(InvalidRequestError):create_campaign(name,members())
    assert not (storage_root()/'campaigns').exists()


@pytest.mark.parametrize('fault',['machine','duplicate-machine','duplicate-member','duplicate-path','missing','empty','extra','too-many','bad-context'])
def test_bad_members_fail_before_publication(fault):
    items=members(); context=''
    if fault=='machine': items[0]['machine']='other'
    elif fault=='duplicate-machine':items[1]['machine']='rusty'
    elif fault=='duplicate-member':items[1]['member_id']=items[0]['member_id']
    elif fault=='duplicate-path':items[1]['bundle_path']=items[0]['bundle_path']
    elif fault=='missing':Path(items[0]['bundle_path']).unlink()
    elif fault=='empty':Path(items[0]['bundle_path']).write_text('{}')
    elif fault=='extra':items[0]['unknown']=True
    elif fault=='too-many':items*=2
    else:context='x'*8193
    with pytest.raises(DiagnosticError):create_campaign('study',items,context=context)
    assert not (storage_root()/'campaigns').exists()


@pytest.mark.parametrize('fault',['version','revision','identity','duplicate-keys','giant','broken','absolute-ref'])
def test_bad_campaign_is_retained_and_discovery_preserves_neighbours(fault):
    create_campaign('good',members())
    record=create_campaign('bad',members());path=Path(record['campaign_path']); raw=json.loads(path.read_text())
    if fault=='version':raw['format_version']=2
    elif fault=='revision':raw['revision']=True
    elif fault=='identity':raw['campaign_id']='wrong'
    elif fault=='absolute-ref':raw['members'][0]['bundle_ref']='/other'
    text=json.dumps(raw)
    if fault=='duplicate-keys':text=text.replace('"format_version": 1','"format_version": 1, "format_version": 1')
    elif fault=='giant':text=' '*65537
    elif fault=='broken':text='broken'
    path.write_text(text)
    with pytest.raises(DiagnosticError):load_campaign('bad')
    assert path.read_text()==text
    rows=list_campaigns()
    assert [r['state'] for r in rows]==['unavailable','available']


def test_cli_and_acp_group_without_contact(capsys):
    items=members();args=['campaign','create','study','--json']
    for m in items:args+=['--member',m['member_id'],m['machine'],m['bundle_path']]
    root.main(args)
    assert json.loads(capsys.readouterr().out)['name']=='study'
    root.main(['campaign','list','--json'])
    assert json.loads(capsys.readouterr().out)[0]['name']=='study'
    assert execute_acp({'action':'load_campaign','name':'study'})['result']['name']=='study'


def test_load_does_not_require_member_access_after_cleanup():
    items=members();record=create_campaign('study',items)
    Path(items[0]['bundle_path']).unlink()
    assert load_campaign('study')==record


def test_legacy_ids_but_not_json_formatting_are_part_of_definition_identity():
    items=members();first=create_campaign('first',items)
    path=Path(items[0]['bundle_path']);payload=json.loads(path.read_text());path.write_text(json.dumps(payload,indent=4))
    assert create_campaign('formatted',items)['members'][0]['bundle_sha256']==first['members'][0]['bundle_sha256']
    payload['work']['id']='102';path.write_text(json.dumps(payload))
    assert create_campaign('changed',items)['members'][0]['bundle_sha256']!=first['members'][0]['bundle_sha256']


def test_receipt_outcomes_change_without_rebinding_definition():
    items=members();path=Path(items[0]['bundle_path']);payload=json.loads(path.read_text())
    payload['work']['_autoslurm_submission']={'submission_id':'a'*32,'receipt_path':'/exact/receipt.json','state':'uncertain'}
    path.write_text(json.dumps(payload));first=create_campaign('first',items)
    payload['work']['id']='102';payload['work']['_autoslurm_submission']['state']='accepted';path.write_text(json.dumps(payload))
    assert create_campaign('observed',items)['members'][0]['bundle_sha256']==first['members'][0]['bundle_sha256']
    payload['work']['_autoslurm_submission']['receipt_path']='/another/receipt.json';path.write_text(json.dumps(payload))
    assert create_campaign('rebound',items)['members'][0]['bundle_sha256']!=first['members'][0]['bundle_sha256']
