"""Receipt/cache/script faults retain exact evidence and never repeat dispatch."""

import errno
import json
import os
from pathlib import Path
import subprocess

import pytest

from autoslurm import (SelectionError, RecordWriteError, SubmissionError, load_submission,
    list_submissions, inspect_bundle, execute_acp, save_bundle, save_config, submit_jobs)
from autoslurm import record_files, submission, submission_operation
from autoslurm.apps import root
from autoslurm.inspection_cache import InspectionCache
from autoslurm.job_to_slurm import create_slurm_script
from autoslurm.storage import storage_root, slurm_dir
from tests.inspection_helpers import saved_run, mock_scheduler


def receipt_fixture():
    path = storage_root() / 'submissions' / ('a' * 32 + '.json')
    bundle = saved_run(jobs={'fit': {'id': '101', '_autoslurm_submission': {
        'submission_id': 'a' * 32, 'receipt_path': str(path)}}})
    receipt = {'protocol': 1, 'submission_id': 'a' * 32, 'bundle': 'study', 'bundle_path': str(bundle),
        'planned_path': str(bundle), 'receipt_path': str(path), 'execution_receipt_path': str(path),
        'machine': 'mock', 'execution': {'is_remote': False}, 'state': 'submitted',
        'execution_finished': True, 'jobs': {'fit': {'state': 'accepted', 'id': '101'}}}
    submission.write_receipt(path, receipt)
    return path, receipt


def no_command(*args, **kwargs):
    pytest.fail('Record failure launched a command')


@pytest.mark.parametrize('kind,code', [('missing', 'resource_missing'), ('json', 'record_invalid'),
    ('utf8', 'record_invalid'), ('shape', 'record_invalid'), ('directory', 'resource_inaccessible'),
    ('link', 'resource_inaccessible'), ('fifo', 'resource_inaccessible')])
def test_receipt_reads_have_exact_safe_diagnosis_without_commands(tmp_path, monkeypatch, kind, code):
    path = tmp_path / 'receipt.json'
    if kind == 'json': path.write_text('{"retained-secret":')
    if kind == 'utf8': path.write_bytes(b'\xff')
    if kind == 'shape': path.write_text('[]')
    if kind == 'directory': path.mkdir()
    if kind == 'link': path.symlink_to(tmp_path / 'absent')
    if kind == 'fifo': os.mkfifo(path)
    monkeypatch.setattr(subprocess, 'run', no_command)
    with pytest.raises(SelectionError) as stopped:
        load_submission(path)
    facts = stopped.value.diagnostic.to_dict()
    assert facts['code'] == code and facts['context']['receipt_path'] == str(path)
    assert facts['context']['resource'] == 'submission_receipt' and facts['effects'] == {}
    assert 'retained-secret' not in json.dumps(facts)
    assert 'repeat a submission' in facts['next_action']


@pytest.mark.parametrize('field,value', [('protocol', 99), ('jobs', {}), ('state', []),
    ('bundle_path', []), ('updated_at', None), ('execution', []), ('execution', {'is_remote': 'no'}),
    ('jobs', {'fit': {'state': []}}), ('jobs', {'fit': {'state': 'accepted', 'id': 'bad'}})])
def test_malformed_receipt_contract_is_not_an_unclassified_bug(field, value):
    path, receipt = receipt_fixture()
    receipt[field] = value
    path.write_text(json.dumps(receipt))
    before = path.read_bytes()
    with pytest.raises(SelectionError) as stopped: load_submission(path)
    assert stopped.value.diagnostic.code == 'record_invalid'
    assert stopped.value.diagnostic.stage == 'validate_receipt'
    assert isinstance(stopped.value.__cause__, ValueError)
    assert path.read_bytes() == before


@pytest.mark.parametrize('path', ['', None, [], 'bad\x00path'])
def test_bad_receipt_selector_is_local_validation(path, monkeypatch):
    monkeypatch.setattr(record_files.os, 'open', no_command)
    with pytest.raises(SelectionError) as stopped: load_submission(path)
    assert stopped.value.diagnostic.code == 'invalid_argument'


def test_receipt_listing_absence_differs_from_denied_or_broken(monkeypatch):
    assert list_submissions() == [] and not (storage_root() / 'submissions').exists()
    path, receipt = receipt_fixture()
    assert list_submissions('study')[0]['jobs']['fit']['id'] == '101'
    path.write_text('{')
    with pytest.raises(SelectionError) as stopped: list_submissions()
    assert stopped.value.diagnostic.context['receipt_path'] == str(path)
    native = PermissionError(errno.EACCES, 'retained-secret')
    def denied(*args): raise native
    monkeypatch.setattr(submission.os, 'scandir', denied)
    with pytest.raises(SelectionError) as stopped: list_submissions()
    assert stopped.value.__cause__ is native and stopped.value.diagnostic.code == 'resource_inaccessible'


@pytest.mark.parametrize('operation', ['receipt', 'projection'])
@pytest.mark.parametrize('fault', ['serialization', 'before_sync', 'after_publish'])
def test_receipt_and_projection_keep_ids_and_true_publication_facts(operation, fault, monkeypatch):
    path, receipt = receipt_fixture()
    selected = path if operation == 'receipt' else Path(receipt['bundle_path'])
    before = selected.read_bytes()
    if fault == 'serialization':
        if operation == 'receipt': receipt['bad'] = object()
        else:
            real_dump = record_files.json.dump
            def invalid(value, stream, **kwargs):
                value = {**value, 'bad': object()}
                return real_dump(value, stream, **kwargs)
            monkeypatch.setattr(record_files.json, 'dump', invalid)
    else:
        real_sync = record_files.os.fsync
        calls = []
        def failed(fd):
            calls.append(fd)
            if len(calls) == (1 if fault == 'before_sync' else 2):
                raise OSError(errno.ENOSPC, 'retained-secret')
            return real_sync(fd)
        monkeypatch.setattr(record_files.os, 'fsync', failed)
    with pytest.raises(RecordWriteError) as stopped:
        if operation == 'receipt': submission.write_receipt(path, receipt)
        else: submission.project_receipt(receipt)
    facts = stopped.value.diagnostic.to_dict()
    assert facts['context']['receipt_path'] == str(path) and facts['context']['submission_id'] == 'a' * 32
    assert facts['context']['bundle_path'] == receipt['bundle_path']
    assert facts['effects']['record_publication'] == ('succeeded' if fault == 'after_publish' else 'not_started')
    if fault != 'after_publish': assert selected.read_bytes() == before
    saved = json.loads(selected.read_text())
    assert (saved['jobs']['fit'] if operation == 'receipt' else saved['fit'])['id'] == '101'
    assert receipt['jobs']['fit']['id'] == '101'
    assert 'retained-secret' not in json.dumps(facts)


@pytest.mark.parametrize('change', ['id', 'identity', 'missing_job', 'shape'])
def test_projection_refuses_mismatched_tracking_without_modifying_bytes(change):
    path, receipt = receipt_fixture()
    target = Path(receipt['bundle_path'])
    data = json.loads(target.read_text())
    if change == 'id': data['fit']['id'] = '999'
    if change == 'identity': data['fit']['_autoslurm_submission']['submission_id'] = 'b' * 32
    if change == 'missing_job': data = {'other': {}}
    if change == 'shape': data = []
    target.write_text(json.dumps(data))
    before = target.read_bytes()
    with pytest.raises(SelectionError) as stopped: submission.project_receipt(receipt)
    assert stopped.value.diagnostic.code == 'record_invalid'
    assert stopped.value.diagnostic.context['receipt_path'] == str(path)
    assert target.read_bytes() == before


@pytest.mark.parametrize('kind', ['json', 'utf8', 'freshness', 'link', 'fifo'])
def test_cache_faults_are_diagnosed_as_unavailable_not_empty(kind, monkeypatch):
    selected = saved_run()
    mock_scheduler(monkeypatch, accounting='101|COMPLETED|0:0|None|101')
    view = inspect_bundle(selected)
    cache = InspectionCache(storage_root())
    target = cache.observation_path(selected)
    if kind == 'json': target.write_text('{"retained-secret":')
    if kind == 'utf8': target.write_bytes(b'\xff')
    if kind == 'freshness':
        view['freshness'] = []
        target.write_text(json.dumps(view))
    if kind in {'link', 'fifo'}:
        target.unlink()
        if kind == 'link': target.symlink_to(target.parent / 'absent')
        else: os.mkfifo(target)
    monkeypatch.setattr(subprocess, 'run', no_command)
    current = inspect_bundle(selected, refresh=False)
    assert current['jobs'][0]['id'] == '101' and current['jobs'][0]['state'] == 'UNKNOWN'
    error = next(error for error in current['errors'] if error['source'] == 'cache')
    assert error['diagnostic']['code'] == ('resource_inaccessible' if kind in {'link', 'fifo'} else 'record_invalid')
    assert error['diagnostic']['context']['path'] == str(target)
    assert 'retained-secret' not in json.dumps(error)


@pytest.mark.parametrize('after_publish', [False, True])
def test_cache_write_diagnostic_preserves_live_observation(after_publish, monkeypatch):
    selected = saved_run()
    mock_scheduler(monkeypatch, accounting='101|COMPLETED|0:0|None|101')
    real_sync = record_files.os.fsync
    calls = []
    def failed(fd):
        calls.append(fd)
        if len(calls) == (2 if after_publish else 1): raise OSError(errno.EDQUOT, 'retained-secret')
        return real_sync(fd)
    monkeypatch.setattr(record_files.os, 'fsync', failed)
    view = inspect_bundle(selected)
    assert view['state'] == 'completed' and view['freshness'] == 'partial'
    assert view['jobs'][0]['id'] == '101' and view['jobs'][0]['tasks'][0]['source'] == 'accounting'
    facts = next(e for e in view['errors'] if e['source'] == 'cache')['diagnostic']
    assert facts['cause']['errno'] == errno.EDQUOT and facts['context']['resource'] == 'inspection_cache'
    assert facts['effects']['record_publication'] == ('succeeded' if after_publish else 'not_started')


def test_broken_receipt_is_per_item_evidence_without_losing_known_id(monkeypatch):
    path, receipt = receipt_fixture()
    path.write_text('{')
    monkeypatch.setattr(subprocess, 'run', no_command)
    view = inspect_bundle(receipt['bundle_path'], refresh=False)
    assert view['jobs'][0]['id'] == '101'
    assert next(e for e in view['errors'] if e['source'] == 'receipt')['diagnostic']['code'] == 'record_invalid'


@pytest.mark.parametrize('mode', ['text', 'json', 'debug'])
def test_submission_cli_and_acp_expose_read_diagnosis_once(tmp_path, monkeypatch, capsys, mode):
    monkeypatch.setattr(subprocess, 'run', no_command)
    path = str(tmp_path / 'missing.json')
    args = ['submission', path] + (['--' + mode] if mode != 'text' else [])
    with pytest.raises(SelectionError if mode == 'debug' else SystemExit) as stopped: root.main(args)
    output = capsys.readouterr()
    if mode == 'text': assert stopped.value.code == 1 and output.err.count('Operation:') == 1 and output.out == ''
    if mode == 'json': assert json.loads(output.out)['diagnostic']['code'] == 'resource_missing' and output.err == ''
    if mode == 'debug': assert isinstance(stopped.value.__cause__, FileNotFoundError)
    result = execute_acp({'action': 'inspect_submission', 'receipt_path': path})
    assert result['diagnostic']['code'] == 'resource_missing'


@pytest.mark.parametrize('after_publish', [False, True])
def test_direct_script_atomic_write_keeps_old_or_complete_content(after_publish, monkeypatch):
    from datetime import datetime
    job = {'name': 'fit', 'script': 'echo science', 'slurm': {}}
    date = datetime(2026, 11, 16)
    name = create_slurm_script(job, date, {'env_command': 'true'})
    target = slurm_dir() / name
    before = target.read_bytes()
    real_sync = record_files.os.fsync
    calls = []
    def failed(fd):
        calls.append(fd)
        if len(calls) == (2 if after_publish else 1): raise OSError(errno.ENOSPC, 'retained-secret')
        return real_sync(fd)
    monkeypatch.setattr(record_files.os, 'fsync', failed)
    with pytest.raises(RecordWriteError) as stopped:
        create_slurm_script({**job, 'script': 'echo new-science'}, date, {'env_command': 'true'})
    facts = stopped.value.diagnostic.to_dict()
    assert facts['context']['job'] == 'fit' and facts['context']['resource'] == 'slurm_script'
    if after_publish: assert b'echo new-science' in target.read_bytes()
    else: assert target.read_bytes() == before
    assert list(slurm_dir().iterdir()) == [target]


def test_staging_diagnosis_stops_before_dispatch(monkeypatch):
    save_config({'machines': {'mock': {'env_command': 'true'}}, 'default_machine': 'mock'})
    selected = save_bundle({'fit': {'script': 'echo science'}}, 'study')
    monkeypatch.setattr('autoslurm.bundle_preparation.validate_slurm_content', lambda *a: None)
    monkeypatch.setattr(subprocess, 'run', no_command)
    def script_failure(path, content):
        native = OSError(errno.ENOSPC, 'disk full')
        error = record_files._write_error(native, path, 'sync_temporary',
            {'record_publication': 'not_started', 'record_durability': 'not_started'})
        raise error from native
    monkeypatch.setattr(submission_operation, 'atomic_text', script_failure)
    with pytest.raises(SubmissionError) as stopped: submit_jobs('study', bundle_path=selected)
    error = stopped.value
    assert error.receipt['state'] == 'rejected' and error.receipt['jobs']['fit']['state'] == 'not_submitted'
    assert error.diagnostic.context['job'] == 'fit' and error.diagnostic.context['receipt_path'] == error.receipt['receipt_path']
    assert not list(slurm_dir().glob('*.sh'))


def test_accepted_id_and_storage_diagnostic_survive_all_submission_wrappers(monkeypatch):
    from autoslurm import bulk_submit_driver
    save_config({'machines': {'mock': {'env_command': 'true'}}, 'default_machine': 'mock'})
    selected = save_bundle({'A': {'script': 'echo first'}, 'B': {'script': 'echo later', 'dependencies': ['A']}}, 'study')
    monkeypatch.setattr('autoslurm.bundle_preparation.validate_slurm_content', lambda *a: None)
    real_write = bulk_submit_driver.write_receipt
    def fail_accepted(path, receipt):
        if receipt['jobs']['A'].get('id'):
            receipt['bad'] = object()
            try: real_write(path, receipt)
            finally: receipt.pop('bad', None)
        else: real_write(path, receipt)
    calls = []
    def scheduler(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, 'Submitted batch job 101', '')
    monkeypatch.setattr(bulk_submit_driver, 'write_receipt', fail_accepted)
    monkeypatch.setattr(subprocess, 'run', scheduler)
    with pytest.raises(SubmissionError) as stopped: submit_jobs('study', bundle_path=selected)
    error = stopped.value
    assert len(calls) == 1 and error.receipt['jobs']['A']['id'] == '101'
    assert error.receipt['state'] == 'uncertain' and error.diagnostic.context['submission_id'] == error.receipt['submission_id']
    assert error.diagnostic.effects['record_publication'] == 'not_started'
    assert load_submission(error.receipt['receipt_path'])['jobs']['A']['id'] == '101'


def test_read_close_failure_is_secondary_to_parse_and_native_cause(tmp_path, monkeypatch):
    path = tmp_path / 'receipt.json'
    path.write_text('{"retained-secret":')
    real_fdopen = record_files.os.fdopen
    native = OSError(errno.EIO, 'close failed')
    class Stream:
        def __init__(self, stream): self.stream = stream
        def fileno(self): return self.stream.fileno()
        def read(self): return self.stream.read()
        def close(self):
            self.stream.close()
            raise native
    monkeypatch.setattr(record_files.os, 'fdopen', lambda *a, **kw: Stream(real_fdopen(*a, **kw)))
    with pytest.raises(SelectionError) as stopped: load_submission(path)
    error = stopped.value
    assert isinstance(error.__cause__, json.JSONDecodeError) and error.diagnostic.code == 'record_invalid'
    assert error.diagnostic.secondary[0].stage == 'close_record'
    assert error.record_cleanup_errors[0].__cause__ is native
    assert 'retained-secret' not in json.dumps(error.diagnostic.to_dict())


def test_read_and_cache_programming_bugs_stay_visible(tmp_path, monkeypatch):
    path = tmp_path / 'receipt.json'
    path.write_text('{}')
    bug = RuntimeError('reader bug')
    def broken(*args): raise bug
    monkeypatch.setattr(record_files.json, 'load', broken)
    with pytest.raises(RuntimeError) as stopped: load_submission(path)
    assert stopped.value is bug
    cache = InspectionCache(tmp_path)
    with pytest.raises(RuntimeError) as stopped: cache._read(path, lambda value: True)
    assert stopped.value is bug


def test_receipt_denial_retains_errno_and_does_not_look_missing(tmp_path, monkeypatch):
    path, receipt = receipt_fixture()
    native = PermissionError(errno.EACCES, 'retained-secret')
    def denied(*args, **kwargs): raise native
    monkeypatch.setattr(record_files.os, 'open', denied)
    with pytest.raises(SelectionError) as stopped: load_submission(path)
    assert stopped.value.__cause__ is native
    assert stopped.value.diagnostic.code == 'resource_inaccessible'
    assert stopped.value.diagnostic.cause.errno == errno.EACCES


@pytest.mark.parametrize('replacement', ['missing', 'regular', 'link'])
def test_receipt_open_race_rechecks_absence(replacement, monkeypatch):
    path, receipt = receipt_fixture()
    native = FileNotFoundError(errno.ENOENT, 'raced read')
    def raced(*args, **kwargs):
        path.unlink()
        if replacement == 'regular': path.write_text('{}')
        if replacement == 'link': path.symlink_to(path.parent / 'absent')
        raise native
    monkeypatch.setattr(record_files.os, 'open', raced)
    with pytest.raises(SelectionError) as stopped: load_submission(path)
    assert stopped.value.__cause__ is native
    assert stopped.value.diagnostic.code == ('resource_missing' if replacement == 'missing' else 'resource_inaccessible')


def test_fdopen_launch_failure_releases_unclaimed_descriptor(tmp_path, monkeypatch):
    path = tmp_path / 'receipt.json'
    path.write_text('{}')
    native = OSError(errno.EMFILE, 'fdopen failed')
    real_open = record_files.os.open
    descriptors = []
    def opened(*args, **kwargs):
        value = real_open(*args, **kwargs)
        descriptors.append(value)
        return value
    def failed(*args, **kwargs): raise native
    monkeypatch.setattr(record_files.os, 'open', opened)
    monkeypatch.setattr(record_files.os, 'fdopen', failed)
    with pytest.raises(SelectionError) as stopped: load_submission(path)
    assert stopped.value.__cause__ is native and len(descriptors) == 1
    with pytest.raises(OSError) as closed: os.fstat(descriptors[0])
    assert closed.value.errno == errno.EBADF


def test_excerpt_cache_failure_keeps_live_text_and_diagnosis(tmp_path, monkeypatch):
    from tests.integration.test_inspection_boundaries import remote_run, remote_logs
    selected = remote_run(tmp_path)
    calls = remote_logs(monkeypatch)
    real_replace = record_files.os.replace
    def failed_excerpt(source, destination):
        if Path(destination).parent.name == 'logs': raise OSError(errno.EDQUOT, 'retained-secret')
        return real_replace(source, destination)
    monkeypatch.setattr(record_files.os, 'replace', failed_excerpt)
    view = inspect_bundle(selected, include_logs=True)
    assert len(calls) == 2 and view['logs'][0]['text'] == 'live detail' and view['logs'][0]['state'] == 'available'
    facts = view['logs'][0]['cache_error']['diagnostic']
    assert facts['cause']['errno'] == errno.EDQUOT and facts['effects']['record_publication'] == 'unknown'
    assert any(error.get('diagnostic') == facts for error in view['errors'])
    assert 'retained-secret' not in json.dumps(facts)


@pytest.mark.parametrize('operation', ['refresh', 'cli', 'acp'])
def test_failed_local_projection_preserves_receipt_and_exposes_diagnostic(operation, monkeypatch, capsys):
    path, receipt = receipt_fixture()
    target = Path(receipt['bundle_path'])
    target.write_text('{')
    monkeypatch.setattr(subprocess, 'run', no_command)
    if operation == 'refresh':
        with pytest.raises(SubmissionError) as stopped: submission.refresh_submission(path)
        assert stopped.value.receipt['jobs']['fit']['id'] == '101'
        assert stopped.value.diagnostic.context['resource'] == 'tracking_snapshot'
    elif operation == 'cli':
        with pytest.raises(SystemExit) as stopped: root.main(['submission', str(path), '--refresh', '--json'])
        assert stopped.value.code == 1
        result = json.loads(capsys.readouterr().out)
        assert result['jobs']['fit']['id'] == '101' and result['diagnostic']['code'] == 'record_invalid'
    else:
        result = execute_acp({'action': 'inspect_submission', 'receipt_path': str(path), 'refresh': True})
        assert result['result']['jobs']['fit']['id'] == '101' and result['diagnostic']['code'] == 'record_invalid'
    assert load_submission(path)['jobs']['fit']['id'] == '101' and target.read_text() == '{'


def test_cache_miss_is_quiet_and_validator_bug_is_visible(tmp_path):
    cache = InspectionCache(tmp_path)
    absent = tmp_path / 'absent.json'
    assert cache._read(absent, lambda value: True) == (None, None)
    assert not cache.root.exists()
    absent.write_text('{}')
    bug = TypeError('validator bug')
    def failed(value): raise bug
    with pytest.raises(TypeError) as stopped: cache._read(absent, failed)
    assert stopped.value is bug
