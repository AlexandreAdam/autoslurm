"""Update failures retain attempted resources, partial effects and native causes."""

import errno
import json
from pathlib import Path
import subprocess

import pytest

from autoslurm import update_software, SoftwareUpdateError, ConfigurationError, InvalidRequestError
from autoslurm import software_update_probe as probe
from autoslurm.apps import root
from autoslurm.errors import DiagnosticCause, _software_update_failure
from tests.unit.test_software_update import Git, FIRST, SECOND, checkout, remote_profile


@pytest.mark.parametrize('fault,code', [('missing', 'command_unavailable'), ('denied', 'command_unavailable'),
    ('timeout', 'command_timeout'), ('nonzero', 'command_failed'), ('signal', 'operation_interrupted'),
    ('mismatch', 'compatibility_mismatch'), ('json', 'protocol_invalid'), ('shape', 'protocol_invalid')])
def test_environment_preflight_names_attempted_python_and_stops_before_pull(checkout, monkeypatch, fault, code):
    _, path = checkout
    git = Git(path)
    native = {'missing': FileNotFoundError(errno.ENOENT, 'retained-secret'),
        'denied': PermissionError(errno.EACCES, 'retained-secret'),
        'timeout': subprocess.TimeoutExpired(['private-command'], 15)}.get(fault)
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        if command[0] != 'git':
            if native is not None: raise native
            if fault in {'nonzero', 'signal'}: return subprocess.CompletedProcess(command, -9 if fault == 'signal' else 1, '', 'retained-secret')
            if fault == 'json': return subprocess.CompletedProcess(command, 0, '{"retained-secret":', '')
            if fault == 'shape': return subprocess.CompletedProcess(command, 0, '[]', '')
            git.prefix = '/other/environment'
        return git(command, **kwargs)
    monkeypatch.setattr(subprocess, 'run', run)
    with pytest.raises(SoftwareUpdateError) as stopped: update_software(project='science')
    error, result = stopped.value, stopped.value.evidence
    python = str(path.parent.parent / 'environment/bin/python')
    assert error.diagnostic.code == code and error.diagnostic.stage == 'environment_python'
    assert error.diagnostic.context['executable'] == error.diagnostic.context['path'] == python
    assert result['installation']['python'] == python and result['installation']['state'] == 'not_started'
    assert result['stage'] == 'preflight' and error.diagnostic.effects == {'git_pull': 'not_started', 'editable_install': 'not_started'}
    assert not any('pull' in call or 'install' in call for call in calls)
    assert 'venv_path' in error.diagnostic.next_action and 'asl config' in error.diagnostic.next_action
    assert 'retained-secret' not in json.dumps(result)
    if native is not None: assert error.__cause__ is native
    if fault in {'missing', 'denied'}: assert python in str(error) and 'not started' in str(error)


@pytest.mark.parametrize('phase', ['preflight', 'pull', 'install', 'after_pull'])
@pytest.mark.parametrize('fault', ['missing', 'io', 'timeout', 'interrupt'])
def test_process_faults_report_phase_specific_effects_without_retry(checkout, monkeypatch, phase, fault):
    _, path = checkout
    git = Git(path)
    calls = []
    native = {'missing': FileNotFoundError(errno.ENOENT, 'retained-secret'),
        'io': OSError(errno.EIO, 'retained-secret'), 'timeout': subprocess.TimeoutExpired(['private-command'], 120),
        'interrupt': KeyboardInterrupt('retained-secret')}[fault]
    def run(command, **kwargs):
        calls.append(command)
        hit = (phase == 'preflight' and command[0] == 'git' or phase == 'pull' and 'pull' in command
            or phase == 'install' and 'install' in command
            or phase == 'after_pull' and command[-1] == 'HEAD^{commit}' and git.head == SECOND)
        if hit: raise native
        return git(command, **kwargs)
    monkeypatch.setattr(subprocess, 'run', run)
    with pytest.raises(SoftwareUpdateError) as stopped: update_software(project='science')
    error, result = stopped.value, stopped.value.evidence
    assert error.__cause__ is native and 'retained-secret' not in json.dumps(result)
    effects = dict(error.diagnostic.effects)
    if phase == 'preflight': assert effects == {'git_pull': 'not_started', 'editable_install': 'not_started'}
    elif phase == 'pull':
        assert effects == {'git_pull': 'not_started' if fault == 'missing' else 'unknown', 'editable_install': 'not_started'}
        assert result['state'] == ('failed' if fault == 'missing' else 'unknown')
    elif phase == 'install':
        assert effects == {'git_pull': 'succeeded', 'editable_install': 'not_started' if fault == 'missing' else 'unknown'}
        assert result['after_commit'] == SECOND
    else:
        assert effects == {'git_pull': 'succeeded', 'editable_install': 'not_started'}
        assert result['state'] == 'unknown' and result['after_commit'] is None
    assert sum('pull' in command for command in calls) <= 1 and sum('install' in command for command in calls) <= 1


def test_failed_install_keeps_pulled_commit_and_redacts_pip_tail(checkout, monkeypatch):
    _, path = checkout
    git = Git(path)
    git.install_exit = 1
    git.install_stderr = 'build failed\ntoken=retained-secret\nlast useful line'
    monkeypatch.setattr(subprocess, 'run', git)
    with pytest.raises(SoftwareUpdateError) as stopped: update_software(project='science')
    error = stopped.value
    assert error.evidence['after_commit'] == SECOND and error.evidence['before_commit'] == FIRST
    assert error.diagnostic.effects == {'git_pull': 'succeeded', 'editable_install': 'partial'}
    assert error.diagnostic.cause.returncode == 1 and 'last useful line' in error.diagnostic.cause.detail
    assert 'retained-secret' not in json.dumps(error.evidence) and 'retained-secret' not in str(error)
    assert str(error).count('Pip output (tail):') == 1


@pytest.mark.parametrize('phase', ['pull', 'install'])
def test_signalled_mutation_is_unknown_not_an_ordinary_rejection(checkout, monkeypatch, phase):
    _, path = checkout
    git = Git(path)
    if phase == 'pull': git.exit = -9
    else: git.install_exit = -9
    monkeypatch.setattr(subprocess, 'run', git)
    with pytest.raises(SoftwareUpdateError) as stopped: update_software(project='science')
    assert stopped.value.evidence['state'] == 'unknown' and stopped.value.diagnostic.code == 'operation_interrupted'
    assert stopped.value.diagnostic.effects['git_pull' if phase == 'pull' else 'editable_install'] == 'unknown'
    if phase == 'install': assert git.install_stderr in stopped.value.evidence['installation']['output_tail']


def failed_remote_payload(root, path, monkeypatch):
    git = Git(path)
    python = str(root.parent / 'environment/bin/python')
    def run(command, **kwargs):
        if command[0] == python: raise FileNotFoundError(errno.ENOENT, 'retained-secret')
        return git(command, **kwargs)
    monkeypatch.setattr(subprocess, 'run', run)
    return probe.update_checkout(str(root), 'science', str(root.parent / 'environment'))


def test_remote_failure_facts_use_same_diagnosis_without_remote_autoslurm(checkout, monkeypatch):
    folder, path = checkout
    payload = failed_remote_payload(folder, path, monkeypatch)
    remote_profile(folder)
    calls = []
    def ssh(command, **kwargs):
        calls.append(command)
        assert command[-2:] == ['research', 'python3 -B -']
        assert 'from autoslurm' not in kwargs['input']
        return subprocess.CompletedProcess(command, 0, json.dumps(payload), '')
    monkeypatch.setattr(subprocess, 'run', ssh)
    with pytest.raises(SoftwareUpdateError) as stopped: update_software(project='science')
    error = stopped.value
    assert len(calls) == 1 and error.__cause__ is None
    assert error.diagnostic.code == 'command_unavailable' and error.diagnostic.cause.kind == 'FileNotFoundError'
    assert error.diagnostic.cause.errno == errno.ENOENT and error.diagnostic.context['ssh_alias'] == 'research'
    assert error.diagnostic.context['executable'] == payload['installation']['python']
    assert error.evidence['diagnostic'] == error.diagnostic.to_dict()


@pytest.mark.parametrize('fault,code,started', [('missing', 'command_unavailable', False),
    ('denied', 'command_unavailable', False), ('io', 'transport_failed', True),
    ('timeout', 'command_timeout', True), ('interrupt', 'operation_interrupted', True),
    ('exit', 'transport_failed', True), ('json', 'protocol_invalid', True)])
def test_ssh_failures_do_not_infer_auth_or_retry(checkout, monkeypatch, fault, code, started):
    folder, path = checkout
    remote_profile(folder)
    native = {'missing': FileNotFoundError(errno.ENOENT, 'retained-secret'),
        'denied': PermissionError(errno.EACCES, 'retained-secret'), 'io': OSError(errno.EIO, 'retained-secret'),
        'timeout': subprocess.TimeoutExpired(['private'], 300), 'interrupt': KeyboardInterrupt('retained-secret')}.get(fault)
    calls = []
    def ssh(command, **kwargs):
        calls.append(command)
        if native is not None: raise native
        return subprocess.CompletedProcess(command, 255 if fault == 'exit' else 0, '{"retained-secret":', 'Permission denied token=retained-secret')
    monkeypatch.setattr(subprocess, 'run', ssh)
    with pytest.raises(SoftwareUpdateError) as stopped: update_software(project='science')
    error = stopped.value
    assert len(calls) == 1 and error.diagnostic.code == code
    assert error.evidence['state'] == ('unknown' if started else 'failed')
    assert set(error.diagnostic.effects.values()) == ({'unknown'} if started else {'not_started'})
    assert 'retained-secret' not in json.dumps(error.evidence)
    if native is not None: assert error.__cause__ is native


@pytest.mark.parametrize('fault', ['project', 'python', 'state_shape', 'failure_shape', 'errno', 'effects', 'check', 'phase',
    'error', 'oversized', 'legacy_check_shape', 'premature_install'])
def test_invalid_remote_facts_remain_unknown_without_believing_safe_effects(checkout, monkeypatch, fault):
    folder, path = checkout
    payload = failed_remote_payload(folder, path, monkeypatch)
    remote_profile(folder)
    if fault == 'project': payload['project'] = 'other'
    if fault == 'python': payload['installation']['python'] = '/other/python'
    if fault == 'state_shape': payload['state'] = []
    if fault == 'failure_shape': payload['failure']['problem'] = []
    if fault == 'errno': payload['failure']['errno'] = True
    if fault == 'effects': payload['effects']['git_pull'] = 'succeeded'
    if fault == 'check': payload['check'] = 'unknown_check'
    if fault == 'phase': payload['check'] = 'editable_install'
    if fault == 'error': payload['error'] = []
    if fault == 'legacy_check_shape':
        payload.pop('effects'); payload.pop('failure'); payload['check'] = []
    if fault == 'premature_install': payload['installation']['state'] = 'installed'
    text = json.dumps(payload) if fault != 'oversized' else 'é' * 40000
    calls = []
    monkeypatch.setattr(subprocess, 'run', lambda command, **kwargs: calls.append(command) or subprocess.CompletedProcess(command, 0, text, ''))
    with pytest.raises(SoftwareUpdateError) as stopped: update_software(project='science')
    assert len(calls) == 1 and stopped.value.diagnostic.code == 'protocol_invalid'
    assert set(stopped.value.diagnostic.effects.values()) == {'unknown'}
    assert stopped.value.evidence['after_commit'] is None


def test_legacy_failure_preserves_evidence_with_unknown_effects(checkout, monkeypatch):
    folder, path = checkout
    payload = failed_remote_payload(folder, path, monkeypatch)
    payload.pop('effects'); payload.pop('failure'); payload.pop('check')
    remote_profile(folder)
    monkeypatch.setattr(subprocess, 'run', lambda command, **kwargs: subprocess.CompletedProcess(command, 0, json.dumps(payload), ''))
    with pytest.raises(SoftwareUpdateError) as stopped: update_software(project='science')
    assert stopped.value.diagnostic.code == 'outcome_unknown'
    assert set(stopped.value.diagnostic.effects.values()) == {'unknown'}
    assert stopped.value.evidence['before_commit'] == FIRST


@pytest.mark.parametrize('mode', ['text', 'json', 'debug'])
def test_software_update_cli_exposes_stale_venv_diagnosis_once(checkout, monkeypatch, capsys, mode):
    folder, path = checkout
    git = Git(path)
    native = FileNotFoundError(errno.ENOENT, 'retained-secret')
    def run(command, **kwargs):
        if command[0] != 'git': raise native
        return git(command, **kwargs)
    monkeypatch.setattr(subprocess, 'run', run)
    args = ['software', 'update', '--project', 'science'] + (['--' + mode] if mode != 'text' else [])
    with pytest.raises(SoftwareUpdateError if mode == 'debug' else SystemExit) as stopped: root.main(args)
    output = capsys.readouterr()
    if mode == 'debug': assert stopped.value.__cause__ is native
    elif mode == 'json':
        data = json.loads(output.out)
        assert data['diagnostic']['code'] == 'command_unavailable' and data['installation']['state'] == 'not_started'
        assert output.err == ''
    else:
        assert output.out == '' and output.err.count('Operation:') == 1
        assert str(folder.parent / 'environment/bin/python') in output.err and 'venv_path' in output.err


@pytest.mark.parametrize('bug', [RuntimeError('probe bug'), ValueError('probe bug')])
def test_programming_bugs_propagate_through_python_and_cli(checkout, monkeypatch, bug):
    def broken(*args, **kwargs): raise bug
    monkeypatch.setattr(probe, '_git', broken)
    for operation in (lambda: update_software(project='science'), lambda: root.main(['software', 'update', '--project', 'science'])):
        with pytest.raises(type(bug)) as stopped: operation()
        assert stopped.value is bug


def test_missing_probe_source_does_not_dispatch_and_preserves_native_cause(checkout, monkeypatch):
    folder, path = checkout
    remote_profile(folder)
    native = PermissionError(errno.EACCES, 'retained-secret')
    original = Path.read_text
    def denied(path, *args, **kwargs):
        if path.name == 'software_update_probe.py': raise native
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'read_text', denied)
    monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: pytest.fail('Helper source failure contacted a machine'))
    with pytest.raises(SoftwareUpdateError) as stopped: update_software(project='science')
    assert stopped.value.__cause__ is native and stopped.value.diagnostic.stage == 'probe_source'
    assert set(stopped.value.diagnostic.effects.values()) == {'not_started'}


def test_update_diagnostic_constructor_is_pure_and_detaches_effects(monkeypatch):
    monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: pytest.fail('Diagnostic performed I/O'))
    effects = {'git_pull': 'not_started', 'editable_install': 'not_started'}
    facts = _software_update_failure(problem='command_unavailable', check='environment_python',
        context={'executable': '/missing/bin/python', 'field': 'venv_path'}, effects=effects,
        cause=DiagnosticCause('FileNotFoundError', errno=errno.ENOENT))
    effects['git_pull'] = 'unknown'
    assert facts.effects['git_pull'] == 'not_started' and 'venv_path' in facts.summary


@pytest.mark.parametrize('field,value,exception', [('project', '../other', InvalidRequestError),
    ('machine', 'absent', ConfigurationError), ('machine', [], ConfigurationError)])
def test_update_request_failures_are_typed_and_have_no_process_effects(checkout, monkeypatch, field, value, exception):
    monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: pytest.fail('Invalid update request started a process'))
    with pytest.raises(exception) as stopped: update_software(**{'project': 'science', field: value})
    assert set(stopped.value.diagnostic.effects.values()) == {'not_started'}


@pytest.mark.parametrize('check', ['branch', 'upstream', 'status', 'commit'])
@pytest.mark.parametrize('returncode', [128, -9])
def test_git_observation_failure_is_not_a_guessed_checkout_condition(checkout, monkeypatch, check, returncode):
    _, path = checkout
    git = Git(path)
    def run(command, **kwargs):
        hit = (check == 'branch' and 'symbolic-ref' in command or check == 'upstream' and command[-1] == '@{upstream}'
            or check == 'status' and 'status' in command or check == 'commit' and command[-1] == 'HEAD^{commit}')
        if hit: return subprocess.CompletedProcess(command, returncode, '', 'retained-secret')
        return git(command, **kwargs)
    monkeypatch.setattr(subprocess, 'run', run)
    with pytest.raises(SoftwareUpdateError) as stopped: update_software(project='science')
    error = stopped.value
    assert error.diagnostic.code == ('operation_interrupted' if returncode < 0 else 'command_failed')
    assert error.diagnostic.cause.returncode == returncode
    assert set(error.diagnostic.effects.values()) == {'not_started'}
    assert 'detached HEAD' not in str(error) and 'retained-secret' not in json.dumps(error.evidence)
