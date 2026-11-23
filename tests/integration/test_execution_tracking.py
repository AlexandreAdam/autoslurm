"""Laptop submissions inspected on an independent cluster installation, offline."""

import contextlib
import copy
from datetime import datetime
import io
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from autoslurm import (save_bundle, submit_jobs, save_config, load_submission,
                      refresh_submission, fetch_run, execute_acp, SubmissionError)
from autoslurm.apps import bulk_submit_driver as helper, status, root
from autoslurm.bulk_submit_driver import BulkSubmitPayload, submit_payload
from autoslurm.bundle_selection import bundle_snapshots
from autoslurm.execution_tracking import receipt_view
from autoslurm.inspection import inspect_bundle
from autoslurm.storage import storage_root, set_storage_root
from autoslurm.submission import validate_receipt


@pytest.fixture
def installations(tmp_path, monkeypatch):
    laptop = storage_root()
    cluster = tmp_path / 'cluster state'
    (cluster / 'slurm').mkdir(parents=True)
    (cluster / 'out').mkdir()
    save_config({'machines': {'cluster': {'ssh_alias': 'laptop-only-alias',
        'path': str(cluster), 'venv_path': '/prepared/env', 'env_command': 'true'}},
        'default_machine': 'cluster'})
    definitions = {
        'shards': {'name': 'shards', 'script': 'science shards', 'script_args': {'count': 5},
                   'slurm': {'array': '2,7'}, 'dependencies': []},
        'merge': {'name': 'merge', 'script': 'science merge', 'slurm': {}, 'dependencies': ['shards']}}
    planned = save_bundle(definitions, 'study')
    original = planned.read_bytes()
    calls, payloads = [], []
    scenario = {'failure': None}

    def run(command, **kwargs):
        calls.append(command)
        result = lambda stdout='', code=0, stderr='': subprocess.CompletedProcess(command, code, stdout, stderr)
        if command[0] == 'bash':
            return result()
        if command[0] == 'sbatch':
            # Both the execution receipt and selected snapshot exist before sbatch.
            identity = Path(command[-1]).stem.rsplit('_', 1)[1]
            receipt = json.loads((cluster / 'submissions' / (identity + '.execution.json')).read_text())
            path = Path(receipt['execution_bundle_path'])
            saved = json.loads(path.read_text())
            assert saved['shards']['_autoslurm_submission']['receipt_path'] == receipt['execution_receipt_path']
            assert not saved['shards']['_autoslurm_execution']['is_remote']
            if Path(command[-1]).name.startswith('merge_'):
                assert receipt['jobs']['shards']['id'] == saved['shards']['id'] == '101'
                assert command[command.index('--dependency') + 1] == 'afterok:101'
                if scenario['failure'] == 'partial':
                    return result(code=1, stderr='quota reached')
                if scenario['failure'] == 'lost-active':
                    raise SystemExit(255)
                return result('102')
            return result('101')
        if command[0] == 'scp':
            for source in command[5:-1]:
                shutil.copyfile(source, cluster / 'slurm' / Path(source).name)
            return result()
        if '-G' in command:
            assert command == ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', '-G', 'laptop-only-alias']
            return result('controlmaster auto\ncontrolpath /user/socket\n')
        assert command[:6] == ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', 'laptop-only-alias'], command
        if command[-1].startswith('bash -lc '):
            return result(str(cluster) + '\n')
        if command[-1] == 'python3 -B -':
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exec(kwargs['input'], {})
            return result(output.getvalue())
        if 'autoslurm.apps.bulk_submit_driver' in command[-1]:
            output = io.StringIO()
            exit_code = 0
            set_storage_root(cluster)
            try:
                with contextlib.redirect_stdout(output):
                    if '--capabilities' in command[-1]:
                        helper.main(['--capabilities'])
                    else:
                        payloads.append(json.loads(kwargs['input']))
                        monkeypatch.setattr(helper.sys, 'stdin', io.StringIO(kwargs['input']))
                        helper.main([])
            except SystemExit as error:
                exit_code = error.code
            finally:
                set_storage_root(laptop)
            if scenario['failure'] in {'lost-active', 'lost-final'} and '--capabilities' not in command[-1]:
                return result(code=255, stderr='connection lost')
            return result(output.getvalue(), exit_code)
        return result()  # mkdir for staged scripts

    monkeypatch.setattr(subprocess, 'run', run)
    return laptop, cluster, planned, original, calls, payloads, scenario


def local_observation(monkeypatch, calls):
    def run(command, **kwargs):
        calls.append(command)
        assert command[0] in {'squeue', 'sacct'}, 'Cluster inspection must use local Slurm only.'
        output = ('101_2|COMPLETED|0:0|None|101_2\n101_7|FAILED|1:0|NonZeroExitCode|101_7\n'
                  '102|PENDING|0:0|Dependency|102\n') if command[0] == 'sacct' else '102|PENDING|15:00|(Dependency)\n'
        return subprocess.CompletedProcess(command, 0, output, '')
    monkeypatch.setattr(subprocess, 'run', run)


def test_remote_submission_is_locally_inspectable_without_laptop(installations, monkeypatch, capsys):
    laptop, cluster, planned, original, calls, payloads, _ = installations
    receipt = submit_jobs('study', bundle_path=planned)
    assert planned.read_bytes() == original
    assert len(payloads) == 1
    origin_bytes = Path(receipt['receipt_path']).read_bytes()
    execution_path = Path(receipt['execution_receipt_path'])
    remote_bytes = execution_path.read_bytes()
    remote_bundle = Path(receipt['execution_bundle_path'])
    for name in ('shards-101_2.out', 'shards-101_7.out', 'merge-102.out'):
        (cluster / 'out' / name).write_text('scientific progress\nuseful evidence\n')
    # The workstation still owns its SSH view and original absolute paths.
    origin = json.loads(Path(receipt['bundle_path']).read_text())
    assert origin['shards']['_autoslurm_execution']['transport'] == {'ssh_alias': 'laptop-only-alias'}
    assert origin['shards']['_autoslurm_submission']['receipt_path'] == receipt['receipt_path']
    laptop.rename(laptop.with_name('laptop unavailable'))
    set_storage_root(cluster)
    before = len(calls)
    local_observation(monkeypatch, calls)
    entries = bundle_snapshots()
    assert len(entries) == 1 and entries[0]['state'] == 'active'
    assert entries[0]['path'] == remote_bundle
    capsys.readouterr()
    status.main(['1', '--json'])
    view = json.loads(capsys.readouterr().out)[0]
    jobs = {job['name']: job for job in view['jobs']}
    assert jobs['shards']['id'] == '101' and jobs['shards']['state'] == 'FAILED'
    assert jobs['merge']['state'] == 'PENDING'
    assert [task['task_index'] for task in jobs['shards']['tasks']] == [2, 7]
    evidence = fetch_run(receipt_path=execution_path, job_name='shards', task_index=7)
    assert not evidence['errors'] and evidence['freshness'] == 'fresh'
    assert any(log['state'] == 'available' and 'useful evidence' in log['text'] for log in evidence['logs'])
    scripts = inspect_bundle(receipt_path=execution_path, include_script=True)
    assert 'science shards' in json.dumps(scripts)
    assert execute_acp({'action': 'fetch_run', 'bundle_path': str(remote_bundle)})['status'] == 'success'
    for command in ('fetch', 'logs', 'inspect'):
        capsys.readouterr()
        root.main([command, '--receipt', str(execution_path), '--json'])
        result = json.loads(capsys.readouterr().out)
        assert result['bundle_path'] == str(remote_bundle)
    assert refresh_submission(execution_path)['execution']['is_remote'] is True  # original provenance
    assert execution_path.read_bytes() == remote_bytes  # reader never rewrites the helper-owned receipt
    assert all(command[0] in {'squeue', 'sacct'} for command in calls[before:])
    monkeypatch.setattr(subprocess, 'run', lambda *args, **kwargs: pytest.fail('Cached inspection contacted Slurm'))
    cached = fetch_run(receipt_path=execution_path, refresh=False, job_name='shards', task_index=7)
    assert cached['freshness'] == 'stale' and cached['logs'][0]['state'] == 'available'
    assert (laptop.with_name('laptop unavailable') / 'submissions' / Path(receipt['receipt_path']).name).read_bytes() == origin_bytes


@pytest.mark.parametrize('failure', ['partial', 'lost-active', 'lost-final'])
def test_execution_tracking_survives_lost_response_and_partial_submission(installations, monkeypatch, failure):
    laptop, cluster, planned, _, calls, payloads, scenario = installations
    scenario['failure'] = failure
    with pytest.raises(SubmissionError) as error:
        submit_jobs('study', bundle_path=planned)
    workstation = error.value.receipt
    execution_path = Path(workstation['execution_receipt_path'])
    execution_receipt = load_submission(execution_path)
    path = Path(execution_receipt['execution_bundle_path'])
    assert json.loads(path.read_text())['shards']['id'] == '101'
    count = len([command for command in calls if command[0] == 'sbatch'])
    set_storage_root(cluster)
    local_observation(monkeypatch, calls)
    evidence = fetch_run(receipt_path=execution_path)
    jobs = {job['name']: job for job in evidence['jobs']}
    assert jobs['shards']['id'] == '101'
    assert jobs['merge']['submission_state'] == {'partial': 'rejected', 'lost-active': 'submitting', 'lost-final': 'accepted'}[failure]
    assert evidence['state'] != 'ready_to_go'
    with pytest.raises(FileExistsError):
        submit_payload(BulkSubmitPayload(**payloads[0]))
    assert len([command for command in calls if command[0] == 'sbatch']) == count
    # Workstation recovery learns the extra exact execution view without losing its own identity.
    set_storage_root(laptop)
    def read_receipt(command, **kwargs):
        assert command == ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', 'laptop-only-alias', 'python3 -B -']
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exec(kwargs['input'], {})
        return subprocess.CompletedProcess(command, 0, output.getvalue(), '')
    monkeypatch.setattr(subprocess, 'run', read_receipt)
    recovered = refresh_submission(workstation['receipt_path'])
    assert recovered['execution_bundle_path'] == str(path)
    assert recovered['bundle_path'] == workstation['bundle_path']
    assert recovered['execution']['transport'] == {'ssh_alias': 'laptop-only-alias'}


def test_same_name_and_timestamp_do_not_replace_draft_or_attempt(installations, monkeypatch):
    _, cluster, planned, original, _, _, _ = installations
    import autoslurm.save_load_jobs as writer
    fixed = datetime(2026, 1, 2, 3, 4, 5)
    class FixedDate(datetime):
        @classmethod
        def now(cls):
            return fixed
    monkeypatch.setattr(writer, 'datetime', FixedDate)
    (cluster / 'jobs').mkdir()
    draft = cluster / 'jobs/study_20260102030405.json'
    draft.write_bytes(original)
    first = submit_jobs('study', bundle_path=planned)
    second = submit_jobs('study', bundle_path=planned)
    assert first['submission_id'] != second['submission_id']
    assert Path(first['execution_bundle_path']).name == 'study_20260102030406.json'
    assert Path(second['execution_bundle_path']).name == 'study_20260102030407.json'
    assert draft.read_bytes() == original
    set_storage_root(cluster)
    assert len(bundle_snapshots()) == 2  # two attempts, superseded draft hidden


@pytest.mark.parametrize('stage', ['create', 'before-sbatch', 'after-acceptance'])
def test_tracking_storage_failure_stops_scheduling_and_keeps_ids(installations, monkeypatch, stage):
    _, cluster, planned, _, calls, _, _ = installations
    from autoslurm import submission
    if stage == 'create':
        monkeypatch.setattr('autoslurm.bulk_submit_driver.create_execution_tracking',
                            lambda *args: (_ for _ in ()).throw(OSError('tracking directory read-only')))
    else:
        real_project = submission.project_receipt
        def project(receipt):
            if Path(receipt['bundle_path']).parent == cluster / 'jobs':
                if stage == 'before-sbatch' or receipt['jobs']['shards'].get('id'):
                    raise OSError('tracking publication failed')
            return real_project(receipt)
        monkeypatch.setattr(submission, 'project_receipt', project)
    with pytest.raises(SubmissionError) as error:
        submit_jobs('study', bundle_path=planned)
    expected_count = 1 if stage == 'after-acceptance' else 0
    assert len([command for command in calls if command[0] == 'sbatch']) == expected_count
    if expected_count:
        assert error.value.receipt['jobs']['shards']['id'] == '101'
        execution = load_submission(error.value.receipt['execution_receipt_path'])
        assert execution['jobs']['shards']['id'] == '101'
        set_storage_root(cluster)
        local_observation(monkeypatch, calls)
        assert fetch_run(receipt_path=execution['execution_receipt_path'])['jobs'][0]['id'] == '101'
    else:
        assert all(not job.get('id') for job in error.value.receipt['jobs'].values())


@pytest.mark.parametrize('fault', ['identity', 'receipt-link', 'root', 'graph', 'known-id', 'path-traversal'])
def test_inconsistent_tracking_payload_stops_before_any_claim_or_scheduler(installations, monkeypatch, fault):
    from autoslurm.bundle_preparation import prepare_bundle
    from autoslurm.execution import resolve_execution_context
    from autoslurm.save_load_jobs import load_bundle_from_path
    from autoslurm.submission_operation import create_submission_operation
    _, cluster, planned, _, _, _, _ = installations
    jobs, graph, _ = load_bundle_from_path(planned)
    context = resolve_execution_context('cluster', {'ssh_alias': 'laptop-only-alias', 'path': str(cluster)})
    prepared = prepare_bundle(jobs, graph, context)
    operation = create_submission_operation('study', planned, prepared, context)
    bundle = operation.tracking_bundle
    if fault == 'identity':
        bundle['shards']['_autoslurm_submission']['submission_id'] = '0' * 32
    elif fault == 'receipt-link':
        bundle['shards']['_autoslurm_submission']['receipt_path'] = '/other/receipt.json'
    elif fault == 'root':
        bundle['shards']['_autoslurm_execution']['results_root'] = '/other/results'
    elif fault == 'graph':
        bundle['merge']['dependencies'] = []
    elif fault == 'known-id':
        bundle['shards']['id'] = '999'
    else:
        operation.receipt['bundle'] = '../escape'
    with pytest.raises(ValueError):
        submit_payload(BulkSubmitPayload(graph, operation.script_names, str(cluster / 'slurm'),
                                         operation.receipt, tracking_bundle=bundle))
    assert not list(cluster.rglob('*.claim'))
    assert not list(cluster.rglob('*.json'))


@pytest.mark.parametrize('field', ['absent', 'wrong-root', 'changed-path'])
def test_execution_view_paths_are_validated_and_pinned(installations, field):
    _, _, planned, _, _, _, _ = installations
    receipt = submit_jobs('study', bundle_path=planned)
    changed = copy.deepcopy(receipt)
    if field == 'absent':
        changed.pop('execution_bundle_path')
    elif field == 'wrong-root':
        changed['execution_bundle_path'] = '/another/jobs/study_20260101000000.json'
    else:
        changed['execution_bundle_path'] = str(Path(receipt['execution_bundle_path']).with_name('study_20000101000000.json'))
    with pytest.raises(ValueError, match='tracking'):
        validate_receipt(changed, receipt)
    copied_reference = Path(receipt['execution_receipt_path']).with_name('copy.json')
    assert receipt_view(receipt, copied_reference)['bundle_path'] == receipt['bundle_path']


def test_receipt_cannot_select_another_attempt_with_the_same_name(installations, monkeypatch):
    _, cluster, planned, _, _, _, _ = installations
    first = submit_jobs('study', bundle_path=planned)
    second = submit_jobs('study', bundle_path=planned)
    path = Path(first['execution_receipt_path'])
    forged = json.loads(path.read_text())
    forged['execution_bundle_path'] = second['execution_bundle_path']
    path.write_text(json.dumps(forged))
    set_storage_root(cluster)
    monkeypatch.setattr(subprocess, 'run', lambda *args, **kwargs: pytest.fail('Mismatched receipt queried Slurm'))
    with pytest.raises(ValueError, match='exact selected receipt'):
        fetch_run(receipt_path=path)
    view = inspect_bundle(first['execution_bundle_path'], refresh=False)
    assert any('different tracking snapshot' in error['message'] for error in view['errors'])


def test_identical_storage_names_on_two_machines_still_select_distinct_receipt_views(installations):
    _, cluster, planned, _, _, _, _ = installations
    receipt = submit_jobs('study', bundle_path=planned)
    shared_namespace = copy.deepcopy(receipt)
    shared_namespace['receipt_path'] = str(cluster / 'submissions' / (receipt['submission_id'] + '.json'))
    shared_namespace['bundle_path'] = str(cluster / 'jobs/study_20000101000000.json')
    assert receipt_view(shared_namespace, shared_namespace['receipt_path'])['bundle_path'] == shared_namespace['bundle_path']
    assert receipt_view(shared_namespace, shared_namespace['execution_receipt_path'])['bundle_path'] == receipt['execution_bundle_path']


def test_missing_tracking_acknowledgment_retains_accepted_ids_and_recovers(installations, monkeypatch):
    _, _, planned, _, calls, _, _ = installations
    original_run = subprocess.run
    def missing_acknowledgment(command, **kwargs):
        response = original_run(command, **kwargs)
        if 'autoslurm.apps.bulk_submit_driver' in command[-1] and '--capabilities' not in command[-1]:
            body = json.loads(response.stdout)
            body['receipt'].pop('execution_bundle_path')
            return subprocess.CompletedProcess(command, response.returncode, json.dumps(body), response.stderr)
        return response
    monkeypatch.setattr(subprocess, 'run', missing_acknowledgment)
    with pytest.raises(SubmissionError, match='did not confirm execution-side tracking') as error:
        submit_jobs('study', bundle_path=planned)
    receipt = error.value.receipt
    assert receipt['state'] == 'submitted' and receipt['jobs']['shards']['id'] == '101'
    assert len([command for command in calls if command[0] == 'sbatch']) == 2
    recovered = refresh_submission(receipt['receipt_path'])
    assert recovered['execution_bundle_path'] and recovered['jobs']['shards']['id'] == '101'
    assert len([command for command in calls if command[0] == 'sbatch']) == 2


@pytest.mark.parametrize('capabilities', [
    {'submission_protocol': 1}, {'submission_protocol': 1, 'execution_tracking': 0},
    {'submission_protocol': 1, 'execution_tracking': True}, []])
def test_old_helper_cannot_silently_drop_execution_tracking(installations, monkeypatch, capabilities):
    _, cluster, planned, _, calls, _, _ = installations
    original_run = subprocess.run
    def old_helper(command, **kwargs):
        if '--capabilities' in command[-1]:
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, json.dumps(capabilities), '')
        return original_run(command, **kwargs)
    monkeypatch.setattr(subprocess, 'run', old_helper)
    with pytest.raises(RuntimeError) as stopped:
        submit_jobs('study', bundle_path=planned)
    assert stopped.value.diagnostic.code == ('compatibility_mismatch' if isinstance(capabilities, dict) else 'protocol_invalid')
    assert 'update AutoSlurm' in stopped.value.diagnostic.next_action
    assert not any(command[0] in {'sbatch', 'scp'} for command in calls)
    assert not list(cluster.rglob('*.json'))
