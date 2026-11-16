"""Direct bundle/config record boundaries preserve identity and write evidence."""

from datetime import datetime
import errno
import json
from pathlib import Path
import subprocess

import pytest

from autoslurm import (InvalidRequestError, RecordWriteError, SelectionError,
    execute_acp, load_bundle_from_path, preview_bundle, save_bundle, save_config,
    schedule_job, submit_jobs)
from autoslurm import record_files, save_load_jobs, bundle_selection
from autoslurm.apps import config as config_cli, filter as filter_cli, initialize, root, schedule, submit
from autoslurm.bundle_metadata import update_job_metadata
from autoslurm.storage import config_file_path, jobs_dir, slurm_dir, storage_root


def profile():
    return {'machines': {'mock': {'env_command': 'true'}}, 'default_machine': 'mock'}


def forbidden(*args, **kwargs):
    pytest.fail('Local record failure reached an external command')


@pytest.mark.parametrize('kind,code,cause', [
    ('missing', 'resource_missing', FileNotFoundError), ('json', 'record_invalid', json.JSONDecodeError),
    ('utf8', 'record_invalid', UnicodeError), ('shape', 'record_invalid', None),
    ('directory', 'resource_inaccessible', None), ('link', 'resource_inaccessible', FileNotFoundError),
])
def test_direct_loader_uses_discovery_read_diagnostics(tmp_path, monkeypatch, kind, code, cause):
    selected = tmp_path / 'external.json'
    if kind == 'json': selected.write_text('{"retained-secret":')
    if kind == 'utf8': selected.write_bytes(b'\xff')
    if kind == 'shape': selected.write_text('["retained-secret"]')
    if kind == 'directory': selected.mkdir()
    if kind == 'link': selected.symlink_to(tmp_path / 'absent')
    monkeypatch.setattr(subprocess, 'run', forbidden)
    for operation in (lambda: load_bundle_from_path(selected), lambda: bundle_selection.bundle_snapshot_state(selected, strict=True)):
        with pytest.raises(SelectionError) as stopped:
            operation()
        error = stopped.value
        assert error.diagnostic.code == code and error.diagnostic.context['bundle_path'] == str(selected)
        assert error.diagnostic.effects == {}
        if cause:
            assert isinstance(error.__cause__, cause)
        assert 'retained-secret' not in json.dumps(error.diagnostic.to_dict())


def test_read_permission_is_unavailable_with_original_errno(tmp_path, monkeypatch):
    path = tmp_path / 'bundle.json'
    path.write_text('{}')
    original = PermissionError(errno.EACCES, 'retained-secret')
    def denied(*args, **kwargs): raise original
    monkeypatch.setattr(bundle_selection.os, 'open', denied)
    with pytest.raises(SelectionError) as stopped:
        load_bundle_from_path(path)
    error = stopped.value
    assert error.__cause__ is original and error.diagnostic.cause.errno == errno.EACCES
    assert error.diagnostic.code == 'resource_inaccessible'


@pytest.mark.parametrize('replacement', ['missing', 'link', 'regular'])
def test_failed_read_after_lookup_never_mistakes_replacement_for_absence(tmp_path, monkeypatch, replacement):
    path = tmp_path / 'bundle.json'
    path.write_text('{}')
    original = FileNotFoundError(errno.ENOENT, 'raced read')
    def raced(*args, **kwargs):
        path.unlink()
        if replacement == 'link': path.symlink_to(tmp_path / 'absent')
        if replacement == 'regular': path.write_text('{}')
        raise original
    monkeypatch.setattr(bundle_selection.os, 'open', raced)
    with pytest.raises(SelectionError) as stopped:
        load_bundle_from_path(path)
    assert stopped.value.__cause__ is original
    assert stopped.value.diagnostic.code == ('resource_missing' if replacement == 'missing' else 'resource_inaccessible')


def test_fifo_bundle_is_rejected_without_opening(tmp_path, monkeypatch):
    import os
    if not hasattr(os, 'mkfifo'): pytest.skip('POSIX FIFO unavailable')
    path = tmp_path / 'bundle.json'
    os.mkfifo(path)
    monkeypatch.setattr(bundle_selection.os, 'open', forbidden)
    with pytest.raises(SelectionError) as stopped:
        load_bundle_from_path(path)
    assert stopped.value.diagnostic.code == 'resource_inaccessible'


@pytest.mark.parametrize('kind', ['json', 'shape', 'graph'])
@pytest.mark.parametrize('operation', ['append', 'metadata'])
def test_broken_saved_bundle_is_never_rewritten_or_replaced(kind, operation, monkeypatch):
    path = jobs_dir() / 'study_20261116000000.json'
    path.write_text('{"retained-secret":' if kind == 'json' else
                    '[]' if kind == 'shape' else json.dumps({'fit': {'script': 'science', 'dependencies': ['absent']}}))
    before = path.read_bytes()
    monkeypatch.setattr(subprocess, 'run', forbidden)
    monkeypatch.setattr(save_load_jobs, 'atomic_json', forbidden)
    with pytest.raises(InvalidRequestError if kind == 'graph' else SelectionError) as stopped:
        if operation == 'append': save_bundle({'later': {'script': 'science'}}, 'study', append=True)
        else: update_job_metadata('study', datetime(2026, 11, 16), 'fit', {'id': '101'})
    facts = stopped.value.diagnostic.to_dict()
    assert facts['context']['bundle_path'] == str(path) and facts['context']['bundle'] == 'study'
    assert 'retained-secret' not in json.dumps(facts)
    assert path.read_bytes() == before and list(jobs_dir().glob('*.json')) == [path]


@pytest.mark.parametrize('operation', ['bundle', 'append', 'schedule', 'metadata', 'config'])
@pytest.mark.parametrize('fault', ['serialization', 'directory_sync'])
def test_write_errors_keep_domain_identity_and_real_publication_effects(operation, fault, monkeypatch):
    selected = save_bundle({'fit': {'script': 'science', 'id': '101'}}, 'study')
    save_config(profile())
    date = datetime.strptime(selected.stem.rsplit('_', 1)[1], '%Y%m%d%H%M%S')
    before = selected.read_bytes()
    if fault == 'directory_sync':
        real_sync = record_files.os.fsync
        calls = 0
        def failed_directory_sync(fd):
            nonlocal calls
            calls += 1
            if calls == 2: raise OSError(errno.EIO, 'directory sync failed')
            return real_sync(fd)
        monkeypatch.setattr(record_files.os, 'fsync', failed_directory_sync)
    bad = object() if fault == 'serialization' else 'new'
    config = profile()
    config['machines']['mock']['extra'] = bad
    actions = {
        'bundle': lambda: save_bundle({'later': {'script': 'science', 'extra': bad}}, 'new-study'),
        'append': lambda: save_bundle({'later': {'script': 'science', 'extra': bad}}, 'study', append=True),
        'schedule': lambda: schedule_job({'name': 'later', 'script': 'science', 'extra': bad}, 'study', append=True),
        'metadata': lambda: update_job_metadata('study', date, 'fit', {'extra': bad}),
        'config': lambda: save_config(config),
    }
    monkeypatch.setattr(subprocess, 'run', forbidden)
    with pytest.raises(RecordWriteError) as stopped:
        actions[operation]()
    error = stopped.value
    facts = error.diagnostic.to_dict()
    assert facts['effects']['record_publication'] == ('not_started' if fault == 'serialization' else 'succeeded')
    assert facts['effects']['record_durability'] == ('not_started' if fault == 'serialization' else 'unknown')
    if operation == 'config':
        assert facts['context']['resource'] == 'configuration' and facts['context']['source'] == 'save_config'
        assert facts['context']['path'] == str(config_file_path())
    else:
        assert facts['context']['bundle'] == ('new-study' if operation == 'bundle' else 'study')
        assert facts['context']['bundle_path'] == facts['context']['path']
        if operation in {'schedule', 'metadata'}:
            assert facts['context']['job'] == ('later' if operation == 'schedule' else 'fit')
    assert json.loads(selected.read_text())['fit']['id'] == '101'
    if fault == 'serialization': assert selected.read_bytes() == before
    else: assert Path(facts['context']['path']).is_file()


@pytest.mark.parametrize('metadata,exception', [([], InvalidRequestError), ({'name': 'other'}, InvalidRequestError),
    ({'dependencies': ['absent']}, InvalidRequestError), ({'id': '102'}, InvalidRequestError),
    ({'id': None}, InvalidRequestError)])
def test_metadata_validation_keeps_scheduler_id_and_original_bytes(metadata, exception):
    path = save_bundle({'fit': {'script': 'science', 'id': '101'}}, 'study')
    date = datetime.strptime(path.stem.rsplit('_', 1)[1], '%Y%m%d%H%M%S')
    before = path.read_bytes()
    with pytest.raises(exception): update_job_metadata('study', date, 'fit', metadata)
    assert path.read_bytes() == before


def test_missing_metadata_job_is_typed_without_creating_directories(tmp_path, monkeypatch):
    path = save_bundle({'fit': {'script': 'science'}}, 'study')
    date = datetime.strptime(path.stem.rsplit('_', 1)[1], '%Y%m%d%H%M%S')
    with pytest.raises(SelectionError) as stopped:
        update_job_metadata('study', date, 'absent', {'id': '101'})
    assert stopped.value.diagnostic.code == 'resource_missing' and stopped.value.diagnostic.context['job'] == 'absent'
    monkeypatch.setattr('autoslurm.bundle_metadata.jobs_dir', lambda: tmp_path / 'absent-root')
    with pytest.raises(SelectionError): update_job_metadata('study', date, 'fit', {})
    assert not (tmp_path / 'absent-root').exists()


def test_scheduled_append_reports_effective_job_and_batch_does_not_guess_bad_job():
    selected = save_bundle({'fit': {'script': 'science'}}, 'study')
    before = selected.read_bytes()
    with pytest.raises(RecordWriteError) as stopped:
        schedule_job({'name': 'fit', 'script': 'science', 'bad': object()}, 'study', append=True)
    assert stopped.value.diagnostic.context['job'] == 'fit_001'
    with pytest.raises(RecordWriteError) as stopped:
        save_bundle({'first': {'script': 'science', 'bad': object()}, 'last': {'script': 'science'}}, 'study', append=True)
    assert 'job' not in stopped.value.diagnostic.context
    assert selected.read_bytes() == before


@pytest.mark.parametrize('name', [None, [], '../escape', 'nested/name', 'a\\b', 'bad\nname'])
def test_invalid_bundle_name_stops_before_storage(name, monkeypatch):
    monkeypatch.setattr(save_load_jobs, 'atomic_json', forbidden)
    with pytest.raises(SelectionError) as stopped:
        save_bundle({}, name)
    assert stopped.value.diagnostic.context['field'] == 'name'
    assert not list(jobs_dir().glob('*.json'))


@pytest.mark.parametrize('operation', ['preview', 'submit'])
def test_public_engine_read_failure_retains_machine_and_bundle(operation, monkeypatch):
    save_config(profile())
    path = jobs_dir() / 'study_20261116000000.json'
    path.write_text('{')
    monkeypatch.setattr(subprocess, 'run', forbidden)
    with pytest.raises(SelectionError) as stopped:
        preview_bundle(path) if operation == 'preview' else submit_jobs('study', bundle_path=path)
    assert stopped.value.diagnostic.context['machine'] == 'mock'
    assert stopped.value.diagnostic.context['bundle_path'] == str(path)
    assert not list(slurm_dir().glob('*.sh'))
    assert not list((storage_root() / 'submissions').glob('*.json'))


@pytest.mark.parametrize('route', ['config', 'configuration', 'standalone', 'filter', 'initialize', 'schedule', 'submit'])
def test_record_cli_failure_is_rendered_once_with_native_debug(route, monkeypatch, capsys):
    save_config(profile())
    path = save_bundle({'fit': {'script': 'science'}}, 'study')
    original = OSError(errno.ENOSPC, 'record write failed')
    def fail(*args, **kwargs): raise original
    monkeypatch.setattr(record_files.os, 'fsync', fail)
    monkeypatch.setattr(subprocess, 'run', forbidden)
    if route in {'config', 'configuration', 'standalone'}:
        entry = config_cli.main if route == 'standalone' else lambda args: root.main([route, *args])
        args, debug = ['--machine', 'mock', '--results-root', '/science'], '--debug'
    elif route == 'filter': entry, args, debug = filter_cli.main, ['all'], '--debug'
    elif route == 'initialize': entry, args, debug = initialize.main, ['empty'], '--debug'
    elif route == 'schedule':
        monkeypatch.setattr(schedule, 'parse_script_args', lambda *a, **kw: {})
        entry, args, debug = schedule.main, ['science', '--time', '1:00'], '--autoslurm-debug'
    else:
        def failing_submit(*a, **kw): save_config(profile())
        monkeypatch.setattr(submit, 'submit_jobs', failing_submit)
        entry, args, debug = submit.main, ['--bundle-file', str(path)], '--debug'
    capsys.readouterr()
    with pytest.raises(SystemExit) as stopped: entry(args)
    assert stopped.value.code == 1
    output = capsys.readouterr()
    assert 'storage_failed' in output.err and output.err.count('Operation:') == 1
    assert 'not_started' in output.err
    with pytest.raises(RecordWriteError) as stopped: entry([*args, debug])
    assert stopped.value.__cause__ is original


def test_acp_schedule_preserves_writer_diagnostic(monkeypatch):
    def fail(*args, **kwargs): raise OSError(errno.ENOSPC, 'disk full')
    monkeypatch.setattr(record_files.os, 'fsync', fail)
    result = execute_acp({'action': 'schedule', 'job': {'name': 'fit', 'script': 'science'}, 'bundle': 'study'})
    assert result['status'] == 'error' and result['diagnostic']['code'] == 'storage_failed'
    assert result['diagnostic']['context']['bundle'] == 'study'


@pytest.mark.parametrize('bug', [TypeError('bug'), KeyError('bug'), ValueError('bug')])
def test_unexpected_reader_bug_is_not_misreported_as_corrupt_data(tmp_path, monkeypatch, bug):
    path = tmp_path / 'bundle.json'
    path.write_text('{}')
    def fail(*args, **kwargs): raise bug
    monkeypatch.setattr(record_files.json, 'load', fail)
    with pytest.raises(type(bug)) as stopped: load_bundle_from_path(path)
    assert stopped.value is bug
