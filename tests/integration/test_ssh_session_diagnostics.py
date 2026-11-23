"""Owned session failures/cleanup preserve exact scheduler evidence, offline."""

import copy
import errno
import json
from pathlib import Path
import subprocess
import tempfile

import pytest

from autoslurm import SubmissionError, load_submission, refresh_submission, submit_jobs
from autoslurm.errors import Diagnostic, DiagnosticError, DiagnosticCause
from autoslurm import run_slurm, ssh_session_resources as resources
from tests.integration.test_execution_tracking import installations


PROFILE = {'ssh_alias': 'research-gpu'}


@pytest.fixture
def local_session(monkeypatch):
    with tempfile.TemporaryDirectory(prefix='asl-test-', dir='/tmp') as directory:
        folder = Path(directory) / 'socket'
        calls = []
        def allocate(**kwargs):
            assert kwargs['prefix'] == 'asl-ssh-'
            folder.mkdir()
            return str(folder)
        def run(command, **kwargs):
            calls.append((command, kwargs))
            return subprocess.CompletedProcess(command, 0, '', '')
        monkeypatch.setattr(resources.tempfile, 'mkdtemp', allocate)
        monkeypatch.setattr(subprocess, 'run', run)
        yield folder, calls, run


def fault_value(fault):
    return {
        'missing': FileNotFoundError(errno.ENOENT, 'retained-secret'),
        'permission': PermissionError(errno.EACCES, 'retained-secret'),
        'io': OSError(errno.EIO, 'retained-secret'),
        'timeout': subprocess.TimeoutExpired(['retained-secret'], 30, output='retained-secret'),
        'encoding': UnicodeDecodeError('utf-8', b'\xffretained-secret', 0, 1, 'bad'),
        'keyboard': KeyboardInterrupt('retained-secret'),
        'bug': TypeError('retained-secret'),
    }.get(fault)


@pytest.mark.parametrize('fault,code', [
    ('missing', 'command_unavailable'), ('permission', 'command_unavailable'), ('io', 'transport_failed'),
    ('timeout', 'command_timeout'), ('encoding', 'protocol_invalid'), ('ssh255', 'transport_failed'),
    ('exit1', 'command_failed'), ('signal', 'operation_interrupted'), ('shape', 'protocol_invalid')])
def test_open_failure_keeps_native_cause_and_cleans_only_owned_resources(local_session, monkeypatch, fault, code):
    folder, calls, original = local_session
    native = fault_value(fault)
    def run(command, **kwargs):
        if '-MNf' in command:
            calls.append((command, kwargs))
            assert kwargs['timeout'] == 30
            if native:
                raise native
            result = {'ssh255': 255, 'exit1': 1, 'signal': -15, 'shape': True}[fault]
            return subprocess.CompletedProcess(command, result, 'retained-secret', 'retained-secret')
        return original(command, **kwargs)
    monkeypatch.setattr(subprocess, 'run', run)
    with pytest.raises(DiagnosticError) as stopped:
        with run_slurm.ssh_submission_session(PROFILE, 'cluster'):
            pytest.fail('Failed session reached submission body')
    diagnostic = stopped.value.diagnostic
    assert diagnostic.code == code and diagnostic.stage == 'open_session'
    assert diagnostic.context['machine'] == 'cluster' and diagnostic.context['ssh_alias'] == 'research-gpu'
    assert diagnostic.effects['session_directory_cleanup'] == 'succeeded'
    assert 'scheduler_submission' not in diagnostic.effects  # Resource owner cannot infer scheduler effects.
    assert not folder.exists()
    assert 'retained-secret' not in json.dumps(diagnostic.to_dict())
    if native:
        assert stopped.value.__cause__ is native
    closes = [(cmd, kwargs) for cmd, kwargs in calls if '-O' in cmd]
    assert len(closes) == (0 if fault in {'missing', 'permission'} else 1)
    if closes:
        assert closes[0][1]['timeout'] == 10
        assert diagnostic.effects['ssh_master_close'] == 'succeeded'


@pytest.mark.parametrize('fault', ['permission', 'io'])
def test_allocation_failure_is_diagnosed_before_open(local_session, monkeypatch, fault):
    folder, calls, _ = local_session
    native = fault_value(fault)
    def allocate(**kwargs):
        raise native
    monkeypatch.setattr(resources.tempfile, 'mkdtemp', allocate)
    with pytest.raises(DiagnosticError) as stopped:
        with run_slurm.ssh_submission_session(PROFILE):
            pytest.fail('Allocation failure reached body')
    assert stopped.value.__cause__ is native
    assert stopped.value.diagnostic.code == 'storage_failed'
    assert stopped.value.diagnostic.stage == 'create_session_directory'
    assert stopped.value.diagnostic.effects['ssh_master_open'] == 'not_started'
    assert len(calls) == 1 and '-G' in calls[0][0]
    assert not folder.exists()


def test_long_default_socket_path_stops_before_ssh_and_is_removed(local_session, tmp_path, monkeypatch):
    _, calls, _ = local_session
    folder = tmp_path / ('long-path-' * 12)
    def allocate(**kwargs):
        folder.mkdir()
        return str(folder)
    monkeypatch.setattr(resources.tempfile, 'mkdtemp', allocate)
    with pytest.raises(DiagnosticError) as stopped:
        with run_slurm.ssh_submission_session(PROFILE):
            pytest.fail('Unsafe socket path reached body')
    assert stopped.value.diagnostic.stage == 'validate_control_path'
    assert stopped.value.diagnostic.code == 'configuration_invalid'
    assert stopped.value.diagnostic.effects['session_directory_cleanup'] == 'succeeded'
    assert not folder.exists() and len(calls) == 1


@pytest.mark.parametrize('fault,expected', [('ssh255', 'transport_failed'), ('timeout', 'command_timeout'),
    ('permission', 'command_unavailable'), ('remove', 'storage_failed'), ('both', 'transport_failed')])
def test_cleanup_only_failure_is_visible_with_resource_effects(local_session, monkeypatch, fault, expected):
    folder, calls, original = local_session
    real_remove = resources.shutil.rmtree
    native = fault_value(fault)
    def run(command, **kwargs):
        if '-O' in command:
            calls.append((command, kwargs))
            if native:
                raise native
            if fault in {'ssh255', 'both'}:
                return subprocess.CompletedProcess(command, 255, 'retained-secret', 'retained-secret')
        return original(command, **kwargs)
    def remove(path, *args, **kwargs):
        if Path(path) == folder and fault in {'remove', 'both'}:
            raise PermissionError(errno.EACCES, 'retained-secret')
        return real_remove(path, *args, **kwargs)
    monkeypatch.setattr(subprocess, 'run', run)
    monkeypatch.setattr(resources.shutil, 'rmtree', remove)
    with pytest.raises(DiagnosticError) as stopped:
        with run_slurm.ssh_submission_session(PROFILE):
            pass
    error = stopped.value
    assert error.diagnostic.code == expected
    assert error.diagnostic.effects['ssh_master_open'] == 'succeeded'
    assert error.diagnostic.effects['session_directory_cleanup'] == ('unknown' if fault in {'remove', 'both'} else 'succeeded')
    assert len(error.session_cleanup_diagnostics) == (2 if fault == 'both' else 1)
    assert len(error.diagnostic.secondary) == (1 if fault == 'both' else 0)
    assert 'retained-secret' not in json.dumps(error.session_cleanup_diagnostics)
    assert 'receipt' in str(error)


@pytest.mark.parametrize('primary_kind', ['runtime', 'diagnosed', 'keyboard', 'bug'])
@pytest.mark.parametrize('cleanup_fault', ['ssh255', 'keyboard', 'bug'])
def test_cleanup_never_replaces_body_error_or_interrupt(local_session, monkeypatch, primary_kind, cleanup_fault):
    folder, _, original = local_session
    primary = {'runtime': RuntimeError('primary failure'), 'keyboard': KeyboardInterrupt(),
        'bug': TypeError('primary bug'), 'diagnosed': DiagnosticError(Diagnostic('outcome_unknown', 'submit', 'dispatch',
            effects={'scheduler_submission': 'unknown'}))}[primary_kind]
    cleanup_native = fault_value(cleanup_fault)
    def run(command, **kwargs):
        if '-O' in command:
            if cleanup_native is not None:
                raise cleanup_native
            return subprocess.CompletedProcess(command, 255, 'retained-secret', 'retained-secret')
        return original(command, **kwargs)
    monkeypatch.setattr(subprocess, 'run', run)
    with pytest.raises(type(primary)) as stopped:
        with run_slurm.ssh_submission_session(PROFILE):
            raise primary
    assert stopped.value is primary and not folder.exists()
    assert primary.session_cleanup_diagnostics[0]['stage'] == 'close_session'
    assert 'retained-secret' not in json.dumps(primary.session_cleanup_diagnostics)
    if cleanup_native is not None:
        assert primary.session_cleanup_errors[0] is cleanup_native
    if primary_kind == 'diagnosed':
        assert primary.diagnostic.code == 'outcome_unknown'
        assert primary.diagnostic.effects == {'scheduler_submission': 'unknown'}
        assert len(primary.diagnostic.secondary) == 1


@pytest.mark.parametrize('fault', ['keyboard', 'bug'])
@pytest.mark.parametrize('stage', ['open', 'close'])
def test_unexpected_errors_remain_original_after_cleanup(local_session, monkeypatch, fault, stage):
    folder, _, original = local_session
    native = fault_value(fault)
    def run(command, **kwargs):
        if ('-MNf' if stage == 'open' else '-O') in command:
            raise native
        return original(command, **kwargs)
    monkeypatch.setattr(subprocess, 'run', run)
    with pytest.raises(type(native)) as stopped:
        with run_slurm.ssh_submission_session(PROFILE):
            pass
    assert stopped.value is native and not folder.exists()


def test_body_changes_cannot_redirect_owned_cleanup(local_session):
    folder, calls, _ = local_session
    profile = copy.deepcopy(PROFILE)
    with run_slurm.ssh_submission_session(profile) as options:
        profile['ssh_alias'] = 'another-machine'
        options.extend(['-o', 'ControlPath=/another/socket'])
    close = next(cmd for cmd, _ in calls if '-O' in cmd)
    assert close[-1] == 'research-gpu' and '/another/socket' not in ' '.join(close)
    assert str(folder) in ' '.join(close) and not folder.exists()


def test_open_failure_keeps_primary_diagnostic_when_close_also_fails(local_session, monkeypatch):
    folder, _, original = local_session
    native = subprocess.TimeoutExpired(['retained-secret'], 30)
    def run(command, **kwargs):
        if '-MNf' in command:
            raise native
        if '-O' in command:
            return subprocess.CompletedProcess(command, 255, 'retained-secret', '')
        return original(command, **kwargs)
    monkeypatch.setattr(subprocess, 'run', run)
    with pytest.raises(DiagnosticError) as stopped:
        with run_slurm.ssh_submission_session(PROFILE):
            pytest.fail('Failed open reached body')
    assert stopped.value.__cause__ is native and not folder.exists()
    diagnostic = stopped.value.diagnostic
    assert diagnostic.code == 'command_timeout' and diagnostic.stage == 'open_session'
    assert diagnostic.effects['ssh_master_open'] == diagnostic.effects['ssh_master_close'] == 'unknown'
    assert diagnostic.effects['session_directory_cleanup'] == 'succeeded'
    assert diagnostic.secondary[0].stage == 'close_session'


def test_existing_secondary_limit_cannot_mask_primary(local_session, monkeypatch):
    _, _, original = local_session
    prior = tuple(Diagnostic('storage_failed', 'record', 'cleanup') for _ in range(4))
    primary = DiagnosticError(Diagnostic('outcome_unknown', 'submit', 'dispatch', secondary=prior))
    def run(command, **kwargs):
        if '-O' in command:
            return subprocess.CompletedProcess(command, 255, '', '')
        return original(command, **kwargs)
    monkeypatch.setattr(subprocess, 'run', run)
    with pytest.raises(DiagnosticError) as stopped:
        with run_slurm.ssh_submission_session(PROFILE):
            raise primary
    assert stopped.value is primary and primary.diagnostic.secondary == prior
    assert len(primary.session_cleanup_diagnostics) == 1


@pytest.mark.parametrize('fault', ['keyboard', 'bug'])
@pytest.mark.parametrize('body_failed', [False, True])
def test_directory_cleanup_bug_or_interrupt_preserves_primary(local_session, monkeypatch, fault, body_failed):
    folder, _, _ = local_session
    real_remove = resources.shutil.rmtree
    native = fault_value(fault)
    primary = RuntimeError('body failed') if body_failed else native
    def remove(path, *args, **kwargs):
        if Path(path) == folder:
            raise native
        return real_remove(path, *args, **kwargs)
    monkeypatch.setattr(resources.shutil, 'rmtree', remove)
    with pytest.raises(type(primary)) as stopped:
        with run_slurm.ssh_submission_session(PROFILE):
            if body_failed:
                raise primary
    assert stopped.value is primary
    assert primary.session_cleanup_diagnostics[0]['stage'] == 'remove_session_directory'
    assert primary.session_cleanup_diagnostics[0]['code'] == ('operation_interrupted' if fault == 'keyboard' else 'internal_error')


@pytest.mark.parametrize('bad_output', [None, 1, 'x' * 65537,
    'controlmaster auto\ncontrolpath /one\ncontrolpath /other', '\ud800'])
def test_optional_settings_observation_falls_back_once(local_session, monkeypatch, bad_output):
    _, calls, original = local_session
    def run(command, **kwargs):
        if '-G' in command:
            calls.append((command, kwargs))
            assert kwargs['timeout'] == 10
            return subprocess.CompletedProcess(command, 0, bad_output, '')
        return original(command, **kwargs)
    monkeypatch.setattr(subprocess, 'run', run)
    with run_slurm.ssh_submission_session(PROFILE) as options:
        assert options
    assert len(calls) == 3


@pytest.mark.parametrize('native', [TypeError('bug'), AttributeError('bug'), RuntimeError('bug')])
def test_optional_probe_does_not_hide_programming_bugs(local_session, monkeypatch, native):
    folder, _, _ = local_session
    def run(*args, **kwargs):
        raise native
    monkeypatch.setattr(subprocess, 'run', run)
    with pytest.raises(type(native)) as stopped:
        with run_slurm.ssh_submission_session(PROFILE):
            pytest.fail('Probe bug reached body')
    assert stopped.value is native and not folder.exists()


@pytest.mark.parametrize('submission_failure', [None, 'partial', 'lost-final', 'lost-active'])
def test_real_submission_retains_primary_state_and_cleanup_after_refresh(installations, monkeypatch, submission_failure):
    _, _, planned, _, calls, _, scenario = installations
    scenario['failure'] = submission_failure
    original = subprocess.run
    def run(command, **kwargs):
        if '-G' in command:
            return subprocess.CompletedProcess(command, 0, 'controlpath none\n', '')
        if '-MNf' in command:
            return subprocess.CompletedProcess(command, 0, '', '')
        if '-O' in command:
            return subprocess.CompletedProcess(command, 255, 'retained-secret', 'retained-secret')
        if command[0] == 'ssh' and '-o' in command:
            command = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', 'laptop-only-alias', command[-1]]
        return original(command, **kwargs)
    monkeypatch.setattr(subprocess, 'run', run)
    with pytest.raises(SubmissionError) as stopped:
        submit_jobs('study', bundle_path=planned)
    error = stopped.value
    receipt = error.receipt
    assert receipt['state'] == ('submitted' if submission_failure is None else 'partial' if submission_failure == 'partial' else 'uncertain')
    assert 'session_cleanup_diagnostics' in str(error)
    assert receipt['session_cleanup_diagnostics'][0]['stage'] == 'close_session'
    assert 'retained-secret' not in json.dumps(receipt)
    if submission_failure is None:
        assert receipt['jobs']['shards']['id'] == '101' and receipt['execution_finished']
        assert error.diagnostic.stage == 'close_session'
    if submission_failure == 'partial':
        assert receipt['jobs']['shards']['id'] == '101' and receipt['jobs']['merge']['state'] == 'rejected'
        assert 'quota reached' in str(error)
    saved = load_submission(receipt['receipt_path'])
    assert saved['session_cleanup_diagnostics'] == receipt['session_cleanup_diagnostics']
    count = len([cmd for cmd in calls if cmd[0] == 'sbatch'])
    refreshed = refresh_submission(receipt['receipt_path'])
    assert refreshed['session_cleanup_diagnostics'] == saved['session_cleanup_diagnostics']
    assert refreshed['jobs']['shards']['id'] == '101'
    assert len([cmd for cmd in calls if cmd[0] == 'sbatch']) == count


def test_execution_receipt_cannot_invent_workstation_cleanup_evidence(installations):
    _, _, planned, _, _, _, _ = installations
    receipt = submit_jobs('study', bundle_path=planned)  # User-managed sharing, no cleanup issue.
    remote_path = Path(receipt['execution_receipt_path'])
    observed = json.loads(remote_path.read_text())
    observed['session_cleanup_diagnostics'] = [{'source': 'another installation'}]
    remote_path.write_text(json.dumps(observed))
    refreshed = refresh_submission(receipt['receipt_path'])
    assert 'session_cleanup_diagnostics' not in refreshed
