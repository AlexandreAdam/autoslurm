"""Selected execution evidence, exact remote reader and no scientific transfers."""

import contextlib
import copy
import io
import json
import os
from pathlib import Path
import subprocess

import pytest

from autoslurm import fetch_run, execute_acp, load_submission, save_config, refresh_submission, SubmissionError
from autoslurm.apps import root
from autoslurm.execution import resolve_execution_context
from autoslurm.inspection import inspect_bundles
from autoslurm.receipt_fetch import MAX_RECEIPT_BYTES
from autoslurm.storage import storage_root
from autoslurm.submission import write_receipt
from tests.inspection_helpers import remote_observation


def run_fixture(tmp_path, *, known=False, array=False):
    remote = tmp_path / 'remote evidence'
    (remote / 'submissions').mkdir(parents=True)
    (remote / 'out').mkdir()
    identity = 'c' * 32
    local_receipt = storage_root() / 'submissions' / (identity + '.json')
    path = storage_root() / 'jobs/study_20260101000000.json'
    definition = {'name': 'sample', 'script': 'scientific-command', 'machine': 'cluster',
        'slurm': {'array': '2,7'} if array else {}, '_autoslurm_snapshot_kind': 'submission',
        '_autoslurm_submission': {'submission_id': identity, 'receipt_path': str(local_receipt), 'state': 'accepted' if known else 'uncertain'}}
    context = resolve_execution_context('cluster', {'ssh_alias': 'producing-alias', 'path': str(remote), 'venv_path': '/unused'})
    execution = context.resolve_job(definition)
    definition['_autoslurm_execution'] = execution
    if known:
        definition['id'] = '101'
    path.write_text(json.dumps({'sample': definition}))
    current = {'protocol': 1, 'submission_id': identity, 'bundle': 'study', 'bundle_path': str(path),
        'planned_path': str(path), 'receipt_path': str(local_receipt), 'machine': 'cluster', 'execution': execution,
        'execution_receipt_path': str(remote / 'submissions' / (identity + '.json')),
        'state': 'submitted' if known else 'uncertain', 'execution_finished': known,
        'jobs': {'sample': {'state': 'accepted', 'id': '101'} if known else {'state': 'uncertain'}}}
    write_receipt(local_receipt, current)
    observed = copy.deepcopy(current)
    observed.update(state='submitted', execution_finished=True)
    observed['jobs']['sample'] = {'state': 'accepted', 'id': '101'}
    Path(current['execution_receipt_path']).write_text(json.dumps(observed))
    for task in ([2, 7] if array else [None]):
        suffix = f'101_{task}' if task is not None else '101'
        (remote / 'out' / f'sample-{suffix}.out').write_text('progress\nuseful failure detail\n')
    return path, local_receipt, observed


def transport(monkeypatch, observed, *, receipt_response=None, scheduler_failed=False, observed_tasks=False):
    calls = []
    def run(command, **kwargs):
        assert command[:2] == ['ssh', 'producing-alias'], command
        calls.append((command, kwargs))
        if command[-1] == 'python3 -B -':
            assert kwargs['timeout'] == 30
            receipt_read = 'query_log_paths([' + repr(observed['execution_receipt_path']) in kwargs['input']
            if receipt_read and receipt_response is not None:
                if isinstance(receipt_response, BaseException):
                    raise receipt_response
                code, stdout, stderr = receipt_response
                return subprocess.CompletedProcess(command, code, stdout, stderr)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exec(kwargs['input'], {})  # Exact shipped reader against temporary files only.
            return subprocess.CompletedProcess(command, 0, output.getvalue(), '')
        assert command[-1].startswith('bash -lc ')
        array = observed_tasks or json.loads(Path(observed['bundle_path']).read_text())['sample']['slurm'].get('array')
        ids = ('101', '101_2', '101_7') if array else ('101',)
        accounting = '\n'.join(f'{identity}|FAILED|1:0|NonZeroExitCode|{identity}' for identity in ids)
        return subprocess.CompletedProcess(command, 0,
            remote_observation(accounting=accounting, queue_code=1 if scheduler_failed else 0), '')
    monkeypatch.setattr(subprocess, 'run', run)
    return calls


def test_fetch_recovers_ids_before_status_and_logs_and_updates_exact_snapshot(tmp_path, monkeypatch):
    path, receipt, observed = run_fixture(tmp_path)
    calls = transport(monkeypatch, observed)
    # A changed/default profile must not redirect this saved attempt.
    save_config({'machines': {'elsewhere': {'env_command': 'true'}}, 'default_machine': 'elsewhere'})
    result = fetch_run(receipt_path=receipt)
    assert result['state'] == 'failed' and result['jobs'][0]['id'] == '101'
    assert result['logs'][0]['text'] == 'progress\nuseful failure detail'
    assert result['freshness'] == 'fresh' and not result['errors']
    assert load_submission(receipt)['state'] == 'submitted'
    assert json.loads(path.read_text())['sample']['id'] == '101'
    assert len(calls) == 3
    assert observed['execution_receipt_path'] in calls[0][1]['input']
    assert calls[1][0][-1].startswith('bash -lc ') and '/out/' in calls[2][1]['input']


@pytest.mark.parametrize('response,code', [
    ((255, '', 'private transport output'), 'transport_failed'),
    ((0, '0|missing||\n', ''), 'resource_missing'),
    ((0, '0|error|unreadable|\n', ''), 'resource_inaccessible'),
    ((0, '0|error|not_regular|\n', ''), 'record_invalid'),
    ((0, '0|ok_changed|1|eA==\n', ''), 'observation_unavailable'),
    ((0, '0|ok|1048577|eA==\n', ''), 'protocol_invalid'),
    ((0, '1|missing||\n', ''), 'protocol_invalid'),
    ((0, '0|ok|2|eA==\n', ''), 'protocol_invalid'),
    ((0, '0|ok|1|!!!!\n', ''), 'protocol_invalid'),
    ((0, '0|ok|1|/w==\n', ''), 'protocol_invalid'),
    ((0, '0|ok|1|eA==\n', ''), 'protocol_invalid'),  # Whole bytes, invalid JSON.
    ((0, '0|missing||\n0|missing||\n', ''), 'protocol_invalid'),
    (subprocess.TimeoutExpired(['ssh'], 30), 'command_timeout'),
    (FileNotFoundError('ssh'), 'command_unavailable'),
])
def test_receipt_failure_preserves_known_ids_and_readable_logs(tmp_path, monkeypatch, response, code):
    path, receipt, observed = run_fixture(tmp_path, known=True)
    transport(monkeypatch, observed, receipt_response=response)
    result = fetch_run(path)
    assert result['jobs'][0]['id'] == '101' and result['logs'][0]['state'] == 'available'
    assert result['freshness'] == 'partial'
    errors = [entry for entry in result['errors'] if entry['source'] == 'receipt_refresh']
    assert errors[0]['diagnostic']['code'] == code
    assert 'private transport output' not in json.dumps(result)
    assert load_submission(receipt)['jobs']['sample']['id'] == '101'


def test_fetch_keeps_recovered_ids_even_when_local_receipt_publication_fails(tmp_path, monkeypatch):
    from autoslurm import submission
    path, receipt, observed = run_fixture(tmp_path)
    transport(monkeypatch, observed)
    def denied(*a, **k):
        raise PermissionError('cannot persist receipt')
    monkeypatch.setattr(submission, 'write_receipt', denied)
    result = fetch_run(path)
    assert result['jobs'][0]['id'] == '101' and result['logs'][0]['state'] == 'available'
    assert result['freshness'] == 'partial' and any(error['source'] == 'receipt_refresh' for error in result['errors'])
    assert load_submission(receipt)['jobs']['sample']['state'] == 'uncertain'


def test_mismatched_receipt_identity_is_not_published(tmp_path, monkeypatch):
    path, receipt, observed = run_fixture(tmp_path, known=True)
    observed['jobs']['sample']['id'] = '999'
    Path(observed['execution_receipt_path']).write_text(json.dumps(observed))
    transport(monkeypatch, observed)
    result = fetch_run(path)
    assert result['jobs'][0]['id'] == load_submission(receipt)['jobs']['sample']['id'] == '101'
    assert any(entry.get('diagnostic', {}).get('code') == 'protocol_invalid' for entry in result['errors'])


def test_receipt_link_to_another_snapshot_is_not_fetched(tmp_path, monkeypatch):
    path, receipt, observed = run_fixture(tmp_path, known=True)
    local = load_submission(receipt)
    local['bundle_path'] = str(tmp_path / 'other.json')
    write_receipt(receipt, local)
    calls = transport(monkeypatch, observed)
    result = fetch_run(path)
    assert len(calls) == 2 and all('/submissions/' not in kwargs.get('input', '') for _, kwargs in calls)
    assert 'exact selected tracking snapshot' in result['errors'][0]['message']


def test_sparse_array_selection_and_bounds_apply_before_log_reads(tmp_path, monkeypatch):
    path, receipt, observed = run_fixture(tmp_path, array=True)
    calls = transport(monkeypatch, observed)
    result = fetch_run(path, job_name='sample', task_index=7, tail=1, max_log_bytes=12, max_logs=1)
    assert len(result['logs']) == 1 and result['logs'][0]['task_index'] == 7
    assert result['logs'][0]['bytes_read'] <= 12 and result['logs'][0]['truncated']
    assert 'sample-101_2.out' not in calls[-1][1]['input']


@pytest.mark.parametrize('options', [{'tail': -1}, {'max_log_bytes': 0}, {'max_logs': 101}, {'job_name': 'absent'},
    {'refresh': 'false'}, {'task_index': 99}, {'task_index': -1}, {'stream': 'invalid'}])
def test_invalid_request_fails_before_receipt_fetch_or_writes(tmp_path, monkeypatch, options):
    path, receipt, observed = run_fixture(tmp_path, array=True)
    before = (path.read_bytes(), receipt.read_bytes())
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: pytest.fail('Invalid request contacted machine'))
    with pytest.raises(ValueError):
        fetch_run(path, **options)
    assert before == (path.read_bytes(), receipt.read_bytes())


def test_cached_fetch_never_reads_receipt_source_status_or_logs_or_writes(tmp_path, monkeypatch):
    path, receipt, observed = run_fixture(tmp_path)
    transport(monkeypatch, observed)
    fetch_run(path)
    before = (path.read_bytes(), receipt.read_bytes())
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: pytest.fail('Cached read contacted machine'))
    monkeypatch.setattr('autoslurm.inspection_cache.atomic_json', lambda *a, **k: pytest.fail('Cached read wrote evidence'))
    monkeypatch.setattr('autoslurm.inspection_receipts.refresh_submission', lambda *a, **k: pytest.fail('Cached read refreshed receipt'))
    result = fetch_run(receipt_path=receipt, refresh=False)
    assert result['freshness'] == result['logs'][0]['freshness'] == 'stale'
    assert result['logs'][0]['text'].endswith('useful failure detail')
    assert before == (path.read_bytes(), receipt.read_bytes())


@pytest.mark.parametrize('args', [[], ['--help'], ['--view', '--cached']])
def test_fetch_help_and_cached_listing_do_not_contact_machine(monkeypatch, capsys, args):
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: pytest.fail('Listing/help contacted machine'))
    try:
        root.main(['fetch', *args])
    except SystemExit as error:
        assert error.code == 0
    assert capsys.readouterr().out


@pytest.mark.parametrize('selector', ['index', 'receipt', 'bundle-file', 'array-row'])
def test_fetch_cli_and_acp_use_shared_selection_and_structured_evidence(tmp_path, monkeypatch, capsys, selector):
    path, receipt, observed = run_fixture(tmp_path, array=selector == 'array-row')
    transport(monkeypatch, observed)
    args = {'index': ['1', '--job', '1'], 'receipt': ['--receipt', str(receipt)],
        'bundle-file': ['--bundle-file', str(path)], 'array-row': ['1', '--array', '--job', '2']}[selector]
    root.main(['fetch', *args, '--json'])
    result = json.loads(capsys.readouterr().out)
    assert result['jobs'][0]['id'] == '101' and result['logs'][0]['state'] == 'available'
    if selector == 'array-row':
        assert [entry['task_index'] for entry in result['logs']] == [7]
    agent = execute_acp({'action': 'fetch_run', 'receipt_path': str(receipt), 'refresh': False})
    assert agent['status'] == 'success' and agent['result']['freshness'] == 'stale'


def test_cli_reports_partial_failure_with_json_evidence_and_exit_one(tmp_path, monkeypatch, capsys):
    path, receipt, observed = run_fixture(tmp_path, known=True)
    transport(monkeypatch, observed, receipt_response=(255, '', 'failed'))
    with pytest.raises(SystemExit) as stopped:
        root.main(['fetch', '1', '--json'])
    assert stopped.value.code == 1
    result = json.loads(capsys.readouterr().out)
    assert result['jobs'][0]['id'] == '101' and result['logs'][0]['state'] == 'available'


def test_remote_receipt_read_is_bounded_even_for_giant_or_special_files(tmp_path, monkeypatch):
    path, receipt, observed = run_fixture(tmp_path, known=True)
    target = Path(observed['execution_receipt_path'])
    with target.open('wb') as stream:
        stream.truncate(1024 ** 3)
    calls = transport(monkeypatch, observed)
    with pytest.raises(SubmissionError) as stopped:
        refresh_submission(receipt)
    assert stopped.value.diagnostic.code == 'protocol_invalid'
    assert str(MAX_RECEIPT_BYTES) in calls[0][1]['input']
    target.unlink()
    os.mkfifo(target)
    with pytest.raises(SubmissionError) as stopped:
        refresh_submission(receipt)
    assert stopped.value.diagnostic.code == 'record_invalid'


def test_multi_run_receipt_error_does_not_discard_other_run(tmp_path, monkeypatch):
    from tests.inspection_helpers import saved_run
    path, receipt, observed = run_fixture(tmp_path, known=True)
    other = saved_run(name='other', jobs={'unsubmitted': {'script': 'science'}})
    transport(monkeypatch, observed, receipt_response=(255, '', 'failed'))
    results = inspect_bundles([path, other], include_logs=True, refresh_receipts=True)
    assert results[0]['logs'][0]['state'] == 'available' and results[0]['errors']
    assert results[1]['state'] == 'ready_to_go' and not results[1]['errors']


def test_local_fetch_uses_existing_log_reader_without_remote_receipts(monkeypatch):
    from tests.inspection_helpers import saved_run, mock_scheduler
    path = saved_run()
    (storage_root() / 'out/sample-101.out').write_text('local execution evidence')
    calls = mock_scheduler(monkeypatch)
    result = fetch_run(path)
    assert result['logs'][0]['text'] == 'local execution evidence'
    assert [command[0] for command in calls] == ['squeue', 'sacct']


def test_first_cached_fetch_reports_no_cache_without_source_reads(tmp_path, monkeypatch):
    path, receipt, observed = run_fixture(tmp_path, known=True)
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: pytest.fail('Uncached offline request contacted machine'))
    result = fetch_run(path, refresh=False)
    assert result['freshness'] == 'never' and result['logs'][0]['state'] == 'not_cached'


def test_unknown_submission_stays_uncertain_when_receipt_cannot_be_fetched(tmp_path, monkeypatch):
    path, receipt, observed = run_fixture(tmp_path)
    calls = transport(monkeypatch, observed, receipt_response=(255, '', 'failed'))
    result = fetch_run(path)
    assert result['state'] == 'uncertain' and result['jobs'][0]['id'] is None
    assert result['logs'] == [] and len(calls) == 1


def test_draft_fetch_does_not_guess_a_receipt_from_the_bundle_name(tmp_path, monkeypatch):
    from tests.inspection_helpers import saved_run
    path, receipt, observed = run_fixture(tmp_path)
    draft = saved_run(jobs={'sample': {'script': 'science'}})
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: pytest.fail('Draft guessed a submission'))
    result = fetch_run(draft)
    assert result['state'] == 'ready_to_go' and result['logs'] == []
    assert load_submission(receipt)['state'] == 'uncertain'


def test_reload_failure_retains_recovered_job_evidence(tmp_path, monkeypatch):
    from autoslurm.inspection_collection import InspectionRun
    path, receipt, observed = run_fixture(tmp_path)
    transport(monkeypatch, observed)
    monkeypatch.setattr('autoslurm.inspection_receipts.load_run', lambda path: InspectionRun(Path(path), [], None, [],
        [{'source': 'definition', 'message': 'definition became unreadable'}], None))
    result = fetch_run(path)
    assert result['jobs'][0]['id'] == '101' and result['logs'][0]['state'] == 'available'
    assert result['freshness'] == 'partial' and any('unreadable' in error['message'] for error in result['errors'])


def test_scheduler_failure_preserves_readable_logs(tmp_path, monkeypatch):
    path, receipt, observed = run_fixture(tmp_path, known=True)
    transport(monkeypatch, observed, scheduler_failed=True)
    result = fetch_run(path)
    assert result['logs'][0]['state'] == 'available' and result['freshness'] == 'partial'


def test_cached_inspection_cannot_request_receipt_refresh(tmp_path, monkeypatch):
    path, receipt, observed = run_fixture(tmp_path)
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: pytest.fail('Invalid cached request contacted machine'))
    with pytest.raises(ValueError):
        inspect_bundles([path], refresh=False, refresh_receipts=True)


@pytest.mark.parametrize('recorded_transport', [None, {}])
def test_missing_recorded_transport_is_diagnosed_without_host_fallback(tmp_path, monkeypatch, recorded_transport):
    path, receipt, observed = run_fixture(tmp_path, known=True)
    current = load_submission(receipt)
    current['execution']['transport'] = recorded_transport
    write_receipt(receipt, current)
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: pytest.fail('Invalid saved transport contacted a host'))
    with pytest.raises(SubmissionError) as stopped:
        refresh_submission(receipt)
    assert stopped.value.diagnostic.code == 'record_invalid'
    assert stopped.value.receipt['jobs']['sample']['id'] == '101'


def test_historical_observed_array_tasks_remain_fetchable(tmp_path, monkeypatch):
    path, receipt, observed = run_fixture(tmp_path, array=True)
    jobs = json.loads(path.read_text())
    jobs['sample']['slurm'] = {}
    path.write_text(json.dumps(jobs))
    transport(monkeypatch, observed, observed_tasks=True)
    result = fetch_run(path, job_name='sample', task_index=7)
    assert result['logs'][0]['task_index'] == 7 and result['logs'][0]['state'] == 'available'


def test_cache_write_failure_keeps_fetched_log_evidence(tmp_path, monkeypatch):
    path, receipt, observed = run_fixture(tmp_path)
    transport(monkeypatch, observed)
    def denied(*a, **k):
        raise PermissionError('cache unavailable')
    monkeypatch.setattr('autoslurm.inspection_cache.atomic_json', denied)
    result = fetch_run(path)
    assert result['jobs'][0]['id'] == '101' and result['logs'][0]['text'].endswith('useful failure detail')
    assert result['freshness'] == 'partial' and any(error['source'] == 'cache' for error in result['errors'])
