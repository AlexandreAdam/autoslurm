"""Robust bounded stdout/stderr retrieval, shared by terminal and agent callers."""

import base64
from pathlib import Path
import os
import subprocess

import pytest

from autoslurm import inspect_logs, execute_acp
from autoslurm.log_probe import read_log
from autoslurm.storage import out_dir, storage_root
from tests.inspection_helpers import saved_run, mock_scheduler


def test_empty_log_is_available_and_different_from_missing(monkeypatch):
    path = saved_run()
    source = out_dir() / 'sample-101.out'
    source.touch()
    mock_scheduler(monkeypatch)
    entry = inspect_logs(path)['logs'][0]
    assert entry['state'] == 'available' and entry['empty'] and entry['bytes_read'] == 0
    source.unlink()
    assert inspect_logs(path)['logs'][0]['state'] == 'missing'


def test_permission_denied_is_not_reported_as_missing(tmp_path, monkeypatch):
    source = tmp_path / 'job.out'
    real_open = os.open
    def denied(path, *a, **kw):
        if str(path) == str(source):
            raise PermissionError('denied')
        return real_open(path, *a, **kw)
    monkeypatch.setattr(os, 'open', denied)
    assert read_log(str(source), 100) == {'state': 'error', 'kind': 'unreadable'}


def test_directory_and_fifo_are_errors_without_blocking(tmp_path):
    assert read_log(str(tmp_path), 100)['kind'] == 'not_regular'
    fifo = tmp_path / 'job.out'
    os.mkfifo(fifo)
    assert read_log(str(fifo), 100)['kind'] == 'not_regular'


def test_sparse_large_log_reads_only_the_requested_suffix(tmp_path, monkeypatch):
    source = tmp_path / 'job.out'
    with source.open('wb') as stream:
        stream.truncate(1024 ** 3)
        stream.seek(-4, 2)
        stream.write(b'LAST')
    real_read = os.read
    reads = []
    def bounded(descriptor, count):
        reads.append(count)
        return real_read(descriptor, count)
    monkeypatch.setattr(os, 'read', bounded)
    entry = read_log(str(source), 32)
    assert entry['data'].endswith(b'LAST') and len(entry['data']) == 32
    assert reads == [32]


def test_concurrent_log_growth_is_marked(tmp_path, monkeypatch):
    source = tmp_path / 'job.out'
    source.write_bytes(b'initial')
    real_read = os.read
    def append(descriptor, count):
        value = real_read(descriptor, count)
        with source.open('ab') as stream:
            stream.write(b' newer data')
        return value
    monkeypatch.setattr(os, 'read', append)
    entry = read_log(str(source), 100)
    assert entry['state'] == 'ok_changed' and entry['data'] == b'initial'


def test_rotation_during_read_is_marked(tmp_path, monkeypatch):
    source = tmp_path / 'job.out'
    source.write_bytes(b'old')
    real_read = os.read
    def rotate(descriptor, count):
        value = real_read(descriptor, count)
        source.rename(tmp_path / 'previous.out')
        source.write_bytes(b'new')
        return value
    monkeypatch.setattr(os, 'read', rotate)
    entry = read_log(str(source), 100)
    assert entry['state'] == 'ok_changed' and entry['data'] == b'old'


def test_stream_selection_happens_before_file_limit(monkeypatch, tmp_path):
    stdout, stderr = tmp_path / 'stdout.out', tmp_path / 'stderr.err'
    stdout.write_text('normal progress')
    stderr.write_text('failure detail')
    path = saved_run(jobs={'sample': {'id': '101', 'slurm': {'output': str(stdout), 'error': str(stderr)}}})
    mock_scheduler(monkeypatch)
    view = inspect_logs(path, stream='stderr', max_logs=1)
    assert len(view['logs']) == 1 and view['logs'][0]['stream'] == 'stderr'
    assert view['logs'][0]['text'] == 'failure detail'
    response = execute_acp({'action': 'inspect_run', 'bundle_path': str(path), 'include_logs': True, 'stream': 'stderr'})
    assert response['status'] == 'success' and response['result']['logs'][0]['stream'] == 'stderr'


def test_stdout_and_stderr_using_same_path_are_one_combined_log(monkeypatch, tmp_path):
    output = tmp_path / 'combined.out'
    output.write_text('combined evidence')
    path = saved_run(jobs={'sample': {'id': '101', 'slurm': {'output': str(output), 'error': str(output)}}})
    mock_scheduler(monkeypatch)
    logs = inspect_logs(path)['logs']
    assert len(logs) == 1 and logs[0]['streams'] == ['stdout', 'stderr']


def test_remote_candidates_are_deduplicated_and_malformed_ids_fail(monkeypatch):
    from autoslurm.log_files import _query_remote_tails
    config = {'ssh_alias': 'recorded-alias'}
    for payload in ('0|missing||\n0|missing||', '9|missing||', 'not a record'):
        monkeypatch.setattr('subprocess.run', lambda command, **kwargs: subprocess.CompletedProcess(command, 0, payload, ''))
        snapshots, error = _query_remote_tails(config, ['/recorded/job.out'], 64)
        assert not snapshots and error


def test_byte_count_cannot_be_smaller_than_the_returned_data(monkeypatch):
    from autoslurm.log_files import _decode_remote_entry
    from autoslurm.inspection_cache import InspectionCache
    reference = {'job_name': 'sample', 'job_id': '101', 'task_index': None, 'key': 'local'}
    entry = _decode_remote_entry(reference, '/job.out', ['ok', '0', base64.b64encode(b'one byte').decode()],
                                 tail=10, max_bytes=100, observed_at='now', cache=InspectionCache(storage_root()))
    assert entry['state'] == 'error'


def test_cache_failure_keeps_live_local_log(monkeypatch):
    path = saved_run()
    (out_dir() / 'sample-101.out').write_text('live error detail')
    mock_scheduler(monkeypatch)
    def fail(*a, **kw):
        raise OSError('cache unavailable')
    monkeypatch.setattr('autoslurm.inspection_cache.atomic_json', fail)
    view = inspect_logs(path)
    assert view['logs'][0]['text'] == 'live error detail'
    assert view['logs'][0]['cache_error']


def test_invalid_stream_and_ambiguous_run_fail_before_queries(monkeypatch):
    path = saved_run()
    monkeypatch.setattr('subprocess.run', lambda *a, **k: pytest.fail('Invalid request queried scheduler'))
    with pytest.raises(ValueError):
        inspect_logs(path, stream='dataset')
    with pytest.raises(ValueError):
        inspect_logs(path, receipt_path='other.json')
