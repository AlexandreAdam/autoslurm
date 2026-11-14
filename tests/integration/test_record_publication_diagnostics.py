"""Publication facts are local observations, not assumptions about rollback."""

import errno
import json
from pathlib import Path

import pytest

from autoslurm import RecordWriteError, save_bundle
from autoslurm.errors import (DiagnosticCause, DiagnosticError, RecordCollisionError,
                             record_write_failure)
from autoslurm import record_files
from autoslurm.storage import jobs_dir


def test_record_diagnostic_is_pure_bounded_and_payload_free(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Diagnostic construction performed I/O')
    monkeypatch.setattr('builtins.open', forbidden)
    monkeypatch.setattr('subprocess.run', forbidden)
    effects = {'record_publication': 'unknown'}
    diagnostic = record_write_failure(stage='publish_record', path='/records/run.json', effects=effects,
        cause=DiagnosticCause('OSError', 'token=retained-secret'), problem='storage')
    effects['record_publication'] = 'succeeded'
    assert diagnostic.effects['record_publication'] == 'unknown'
    assert diagnostic.code == 'storage_failed' and diagnostic.operation == 'record_publication'
    assert 'retained-secret' not in json.dumps(diagnostic.to_dict())
    with pytest.raises(ValueError):
        record_write_failure(stage='write', path='/record', effects={}, cause=None, problem='guess')


@pytest.mark.parametrize('data,cause', [({'bad': object()}, TypeError), ({'bad': {1, 2}}, TypeError)])
@pytest.mark.parametrize('existing', [False, True])
def test_serialization_failure_retains_destination_and_native_cause(record_root, data, cause, existing):
    path = record_root / 'record.json'
    if existing:
        path.write_text('{"original":true}')
    before = path.read_bytes() if existing else None
    with pytest.raises(RecordWriteError) as stopped:
        record_files.atomic_json(path, data)
    error = stopped.value
    assert isinstance(error, (DiagnosticError, OSError))
    assert isinstance(error.__cause__, cause)
    facts = error.diagnostic.to_dict()
    assert facts['code'] == 'invalid_argument' and facts['stage'] == 'serialize'
    assert facts['context'] == {'path': str(path), 'field': 'record_data'}
    assert facts['effects'] == {'record_publication': 'not_started', 'record_durability': 'not_started'}
    assert (path.read_bytes() if path.exists() else None) == before
    assert list(record_root.iterdir()) == ([path] if existing else [])


def test_circular_serialization_is_diagnosed_without_record_values(record_root):
    data = {'label': 'retained-secret'}
    data['cycle'] = data
    with pytest.raises(RecordWriteError) as stopped:
        record_files.atomic_json(record_root / 'record.json', data)
    assert isinstance(stopped.value.__cause__, ValueError)
    assert 'retained-secret' not in json.dumps(stopped.value.diagnostic.to_dict())
    assert list(record_root.iterdir()) == []


@pytest.mark.parametrize('fault,stage', [('mkdir', 'prepare_directory'), ('temporary', 'create_temporary'),
                                      ('fsync', 'sync_temporary')])
def test_prepublication_oserror_identifies_stage_errno_and_retains_old_record(record_root, monkeypatch, fault, stage):
    path = record_root / 'record.json'
    path.write_text('{"original":true}')
    before = path.read_bytes()
    original = OSError(errno.ENOSPC, 'retained-secret')
    def fail(*args, **kwargs):
        raise original
    target = {'mkdir': 'pathlib.Path.mkdir', 'temporary': 'autoslurm.record_files.tempfile.NamedTemporaryFile',
              'fsync': 'autoslurm.record_files.os.fsync'}[fault]
    monkeypatch.setattr(target, fail)
    with pytest.raises(RecordWriteError) as stopped:
        record_files.atomic_json(path, {'new': True})
    error = stopped.value
    assert error.__cause__ is original
    assert error.diagnostic.stage == stage and error.diagnostic.cause.errno == errno.ENOSPC
    assert error.diagnostic.effects['record_publication'] == 'not_started'
    assert 'retained-secret' not in json.dumps(error.diagnostic.to_dict())
    assert path.read_bytes() == before and list(record_root.iterdir()) == [path]


@pytest.mark.parametrize('exclusive', [False, True])
@pytest.mark.parametrize('after_effect', [False, True])
def test_publication_syscall_failure_is_unknown_even_if_a_complete_file_exists(record_root, monkeypatch, exclusive, after_effect):
    path = record_root / 'record.json'
    operation = 'link' if exclusive else 'replace'
    real = getattr(record_files.os, operation)
    original = OSError(errno.EIO, 'lost filesystem acknowledgement')
    def uncertain(*args, **kwargs):
        if after_effect:
            real(*args, **kwargs)
        raise original
    monkeypatch.setattr(record_files.os, operation, uncertain)
    with pytest.raises(RecordWriteError) as stopped:
        record_files.atomic_json(path, {'complete': True}, exclusive=exclusive)
    facts = stopped.value.diagnostic.to_dict()
    assert facts['stage'] == 'publish_record' and facts['effects']['record_publication'] == 'unknown'
    assert facts['effects']['record_durability'] == 'unknown' and stopped.value.__cause__ is original
    assert path.exists() is after_effect
    assert sorted(record_root.iterdir()) == ([path] if after_effect else [])
    if after_effect:
        assert json.loads(path.read_text()) == {'complete': True}


@pytest.mark.parametrize('exclusive', [False, True])
@pytest.mark.parametrize('fault', ['directory_open', 'directory_fsync', 'directory_close'])
def test_postpublication_failure_keeps_complete_record_and_known_effects(record_root, monkeypatch, exclusive, fault):
    path = record_root / 'record.json'
    original = OSError(errno.EIO, 'storage failed')
    real_open, real_sync, real_close = record_files.os.open, record_files.os.fsync, record_files.os.close
    directory_fd = None
    def opened(target, *args, **kwargs):
        nonlocal directory_fd
        if Path(target) == record_root:
            if fault == 'directory_open':
                raise original
            directory_fd = real_open(target, *args, **kwargs)
            return directory_fd
        return real_open(target, *args, **kwargs)
    def synced(fd):
        if fd == directory_fd and fault == 'directory_fsync':
            raise original
        return real_sync(fd)
    def closed(fd):
        real_close(fd)
        if fd == directory_fd and fault == 'directory_close':
            raise original
    monkeypatch.setattr(record_files.os, 'open', opened)
    monkeypatch.setattr(record_files.os, 'fsync', synced)
    monkeypatch.setattr(record_files.os, 'close', closed)
    with pytest.raises(RecordWriteError) as stopped:
        record_files.atomic_json(path, {'complete': True}, exclusive=exclusive)
    facts = stopped.value.diagnostic.to_dict()
    assert facts['effects']['record_publication'] == 'succeeded'
    assert facts['effects']['record_durability'] == ('succeeded' if fault == 'directory_close' else 'unknown')
    assert stopped.value.__cause__ is original
    assert json.loads(path.read_text()) == {'complete': True} and list(record_root.iterdir()) == [path]


@pytest.mark.parametrize('fault', ['storage', 'serialization', 'interrupt', 'bug'])
def test_cleanup_failure_cannot_replace_primary_or_its_cause(record_root, monkeypatch, fault):
    path = record_root / 'record.json'
    path.write_text('{"original":true}')
    failures = {'storage': OSError(errno.ENOSPC, 'disk full'), 'serialization': TypeError('retained-secret'),
                'interrupt': KeyboardInterrupt(), 'bug': KeyError('programming bug')}
    primary = failures[fault]
    def fail(*args, **kwargs):
        raise primary
    def cannot_unlink(*args, **kwargs):
        raise PermissionError(errno.EACCES, 'cleanup denied')
    monkeypatch.setattr(record_files.json, 'dump', fail)
    monkeypatch.setattr(Path, 'unlink', cannot_unlink)
    with pytest.raises(RecordWriteError if fault in {'storage', 'serialization'} else type(primary)) as stopped:
        record_files.atomic_json(path, {'new': True})
    error = stopped.value
    if isinstance(error, RecordWriteError):
        assert error.__cause__ is primary
        assert error.diagnostic.secondary[0].stage == 'cleanup_temporary'
        assert error.diagnostic.secondary[0].cause.errno == errno.EACCES
        assert 'retained-secret' not in json.dumps(error.diagnostic.to_dict())
    else:
        assert error is primary and error.__notes__
    assert isinstance(error.record_cleanup_errors[0].__cause__, PermissionError)
    assert path.read_text() == '{"original":true}'
    assert len(list(record_root.iterdir())) == 2  # Failed cleanup is retained, not hidden.


def test_cleanup_only_failure_reports_successful_publication(record_root, monkeypatch):
    path = record_root / 'record.json'
    original = PermissionError(errno.EACCES, 'cannot remove temporary')
    def fail(*args, **kwargs):
        raise original
    monkeypatch.setattr(Path, 'unlink', fail)
    with pytest.raises(RecordWriteError) as stopped:
        record_files.atomic_json(path, {'complete': True}, exclusive=True)
    facts = stopped.value.diagnostic.to_dict()
    assert facts['stage'] == 'cleanup_temporary' and facts['effects'] == {
        'record_publication': 'succeeded', 'record_durability': 'succeeded'}
    assert stopped.value.__cause__ is original and json.loads(path.read_text()) == {'complete': True}


@pytest.mark.parametrize('cleanup_error', [PermissionError(errno.EACCES, 'denied'), KeyError('cleanup bug')])
def test_snapshot_collision_with_cleanup_failure_does_not_select_another_name(monkeypatch, cleanup_error):
    competitor = []
    real_link = record_files.os.link
    def collision(source, target):
        competitor.append(Path(target))
        Path(target).write_text('{"competitor":true}')
        real_link(source, target)
    def cannot_unlink(*args, **kwargs):
        raise cleanup_error
    monkeypatch.setattr(record_files.os, 'link', collision)
    monkeypatch.setattr(Path, 'unlink', cannot_unlink)
    with pytest.raises(RecordCollisionError) as stopped:
        save_bundle({'fit': {'script': 'science'}}, 'study')
    error = stopped.value
    assert isinstance(error, FileExistsError) and isinstance(error, RecordWriteError)
    assert len(competitor) == 1 and error.record_cleanup_errors
    assert json.loads(competitor[0].read_text()) == {'competitor': True}
    assert list(jobs_dir().glob('*.json')) == competitor


def test_clean_collision_preserves_destination_and_is_compatible_with_file_exists(record_root):
    path = record_root / 'record.json'
    path.write_text('{"old":true}')
    with pytest.raises(RecordCollisionError) as stopped:
        record_files.atomic_json(path, {'new': True}, exclusive=True)
    assert isinstance(stopped.value, (RecordWriteError, FileExistsError))
    assert stopped.value.diagnostic.effects['record_publication'] == 'not_started'
    assert not stopped.value.diagnostic.secondary and not getattr(stopped.value, 'record_cleanup_errors', ())
    assert path.read_text() == '{"old":true}' and list(record_root.iterdir()) == [path]


def test_temporary_close_failure_cannot_mask_serialization_failure(record_root, monkeypatch):
    real_temporary = record_files.tempfile.NamedTemporaryFile
    close_error = OSError(errno.EIO, 'close failed')
    class Stream:
        def __init__(self, stream):
            self.stream = stream
        def __getattr__(self, name):
            return getattr(self.stream, name)
        def close(self):
            self.stream.close()
            raise close_error
    monkeypatch.setattr(record_files.tempfile, 'NamedTemporaryFile', lambda **kw: Stream(real_temporary(**kw)))
    with pytest.raises(RecordWriteError) as stopped:
        record_files.atomic_json(record_root / 'record.json', {'bad': object()})
    error = stopped.value
    assert error.diagnostic.stage == 'serialize' and isinstance(error.__cause__, TypeError)
    assert error.diagnostic.secondary[0].stage == 'close_temporary'
    assert error.record_cleanup_errors[0].__cause__ is close_error
    assert list(record_root.iterdir()) == []


def test_unknown_writer_bug_remains_native_and_cleans_temporary(record_root, monkeypatch):
    original = KeyError('programming bug')
    def fail(*args, **kwargs):
        raise original
    monkeypatch.setattr(record_files.json, 'dump', fail)
    with pytest.raises(KeyError) as stopped:
        record_files.atomic_json(record_root / 'record.json', {})
    assert stopped.value is original and list(record_root.iterdir()) == []


def test_secondary_limit_cannot_replace_primary(record_root, monkeypatch):
    from autoslurm.errors import Diagnostic
    diagnostic = record_write_failure(stage='serialize', path=str(record_root / 'record.json'),
        effects={'record_publication': 'not_started'}, cause=DiagnosticCause('OSError'))
    diagnostic = diagnostic.with_secondary(*(Diagnostic('storage_failed', 'writer', 'cleanup') for _ in range(4)))
    original = RecordWriteError(diagnostic)
    def fail(*args, **kwargs):
        raise original
    monkeypatch.setattr(record_files.json, 'dump', fail)
    monkeypatch.setattr(Path, 'unlink', lambda *a, **kw: (_ for _ in ()).throw(PermissionError('cleanup denied')))
    with pytest.raises(RecordWriteError) as stopped:
        record_files.atomic_json(record_root / 'record.json', {})
    assert stopped.value is original and len(original.diagnostic.secondary) == 4
    assert len(original.record_cleanup_errors) == 1


def test_cleanup_preserves_native_error_without_exception_notes(record_root, monkeypatch):
    class LegacyError(Exception):
        add_note = None
    original = LegacyError('original')
    def fail(*args, **kwargs):
        raise original
    monkeypatch.setattr(record_files.json, 'dump', fail)
    monkeypatch.setattr(Path, 'unlink', lambda *a, **kw: (_ for _ in ()).throw(PermissionError('cleanup denied')))
    with pytest.raises(LegacyError) as stopped:
        record_files.atomic_json(record_root / 'record.json', {})
    assert stopped.value is original and original.record_cleanup_errors


def test_directory_close_failure_does_not_mask_failed_directory_sync(record_root, monkeypatch):
    real_sync, real_close = record_files.os.fsync, record_files.os.close
    count = 0
    original = OSError(errno.EIO, 'directory sync failed')
    def sync(fd):
        nonlocal count
        count += 1
        if count == 2:
            raise original
        return real_sync(fd)
    def close(fd):
        real_close(fd)
        raise OSError(errno.EBADF, 'directory close failed')
    monkeypatch.setattr(record_files.os, 'fsync', sync)
    monkeypatch.setattr(record_files.os, 'close', close)
    with pytest.raises(RecordWriteError) as stopped:
        record_files.atomic_json(record_root / 'record.json', {'complete': True})
    error = stopped.value
    assert error.diagnostic.stage == 'sync_directory' and error.__cause__ is original
    assert error.diagnostic.secondary[0].stage == 'close_directory'
    assert error.diagnostic.effects['record_publication'] == 'succeeded'
    assert json.loads((record_root / 'record.json').read_text()) == {'complete': True}


@pytest.fixture
def record_root(tmp_path):
    root = tmp_path / "publication"
    root.mkdir()
    return root
