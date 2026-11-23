"""Pre-dispatch root/helper observations with no live SSH or scheduler effects."""

import copy
import errno
import json
import subprocess

import pytest

from autoslurm import (ConfigurationError, save_bundle, save_config,
                      remote_storage_root_from_config, probe_submission_helper)
from autoslurm.errors import DiagnosticError
from autoslurm.apps import root, submit
from autoslurm.execution import resolve_execution_context
from autoslurm.remote_readiness import MAX_READINESS_RESPONSE_BYTES
from autoslurm.storage import storage_root


PROFILE = {'ssh_alias': 'research-gpu', 'venv_path': '/site/env with spaces', 'env_command': 'true'}
CAPABILITIES = {'submission_protocol': 1, 'execution_tracking': 1}


def operation(kind):
    if kind == 'root':
        return lambda: remote_storage_root_from_config({**PROFILE, 'storage_root': '/selected/state'}, 'cluster')
    context = resolve_execution_context('cluster', {**PROFILE, 'path': '/selected/state'})
    return lambda: probe_submission_helper(context)


@pytest.mark.parametrize('kind', ['root', 'helper'])
@pytest.mark.parametrize('fault,expected', [
    ('missing', 'command_unavailable'), ('denied', 'command_unavailable'), ('io', 'transport_failed'),
    ('timeout', 'command_timeout'), ('decode', 'protocol_invalid'), ('ssh255', 'transport_failed'),
    ('remote127', 'command_failed'), ('signal', 'operation_interrupted'), ('not-text', 'protocol_invalid'),
    ('oversized', 'protocol_invalid'), ('bad-returncode', 'protocol_invalid'), ('surrogate', 'protocol_invalid')])
def test_process_failures_retain_attempted_context_and_no_submission_effects(monkeypatch, kind, fault, expected):
    native = {'missing': FileNotFoundError(errno.ENOENT, 'retained-secret'),
              'denied': PermissionError(errno.EACCES, 'retained-secret'),
              'io': OSError(errno.EIO, 'retained-secret'),
              'timeout': subprocess.TimeoutExpired(['retained-secret'], 30, output='retained-secret'),
              'decode': UnicodeDecodeError('utf-8', b'\xffretained-secret', 0, 1, 'bad')}.get(fault)
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        assert command[:6] == ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', 'research-gpu'] and kwargs['timeout'] == 30
        if native is not None:
            raise native
        code = {'ssh255': 255, 'remote127': 127, 'signal': -15, 'bad-returncode': True}.get(fault, 0)
        stdout = {'not-text': None, 'oversized': 'x' * (MAX_READINESS_RESPONSE_BYTES + 1),
                  'surrogate': '\ud800'}.get(fault, 'retained-secret')
        return subprocess.CompletedProcess(command, code, stdout, 'retained-secret')
    monkeypatch.setattr(subprocess, 'run', run)
    with pytest.raises(DiagnosticError) as stopped:
        operation(kind)()
    error = stopped.value
    diagnostic = error.diagnostic
    assert diagnostic.code == expected and diagnostic.operation == 'remote_readiness'
    assert diagnostic.context['machine'] == 'cluster' and diagnostic.context['ssh_alias'] == 'research-gpu'
    assert diagnostic.context['command'] == 'ssh'
    assert diagnostic.context['storage_root'] == '/selected/state'
    assert diagnostic.context['field'] == ('storage_root' if kind == 'root' else 'venv_path')
    assert diagnostic.context['executable'] == ('python' if kind == 'root' else '/site/env with spaces/bin/python')
    assert diagnostic.effects == {'script_transfer': 'not_started', 'submission_dispatch': 'not_started',
                                  'scheduler_submission': 'not_started'}
    assert 'retained-secret' not in json.dumps(diagnostic.to_dict())
    if native is not None:
        assert error.__cause__ is native
    if fault in {'ssh255', 'remote127', 'signal'}:
        assert diagnostic.cause.returncode == {'ssh255': 255, 'remote127': 127, 'signal': -15}[fault]
    assert len(calls) == 1


@pytest.mark.parametrize('value', [None, '', 'relative', '/state/../other', '/state\nother'])
def test_invalid_explicit_root_stops_locally_without_legacy_fallback(monkeypatch, value):
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: pytest.fail('Invalid selection contacted SSH'))
    with pytest.raises(ConfigurationError) as stopped:
        remote_storage_root_from_config({**PROFILE, 'storage_root': value, 'path': '/legacy/state'}, 'cluster')
    assert stopped.value.diagnostic.code == 'configuration_invalid'
    assert stopped.value.diagnostic.context['field'] == 'storage_root'


@pytest.mark.parametrize('value', [None, '', 'relative', '/env/../other', '/env\x00bad'])
def test_invalid_helper_environment_stops_locally(monkeypatch, value):
    context = resolve_execution_context('cluster', {**PROFILE, 'path': '/state'})
    context.config['venv_path'] = value  # Exercise the direct public helper guard too.
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: pytest.fail('Invalid helper contacted SSH'))
    with pytest.raises(ConfigurationError) as stopped:
        probe_submission_helper(context)
    assert stopped.value.diagnostic.code == 'configuration_invalid'
    assert 'venv_path' in str(stopped.value)


@pytest.mark.parametrize('text', ['', 'relative', 'startup message\n/selected/state',
    '/selected/state\nstartup message', '/selected/../other', '/selected/\x00state'])
def test_invalid_root_response_is_unavailable_not_a_fallback(monkeypatch, text):
    monkeypatch.setattr(subprocess, 'run', lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, text, ''))
    with pytest.raises(DiagnosticError) as stopped:
        operation('root')()
    assert stopped.value.diagnostic.code == 'protocol_invalid'
    assert stopped.value.diagnostic.stage == 'read_storage_root'
    assert text not in str(stopped.value) or not text


def test_mismatched_root_retains_expected_and_observed_paths(monkeypatch):
    monkeypatch.setattr(subprocess, 'run', lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, '/other/state\n', ''))
    with pytest.raises(DiagnosticError) as stopped:
        operation('root')()
    assert stopped.value.diagnostic.code == 'compatibility_mismatch'
    assert stopped.value.diagnostic.context['path'] == '/selected/state'
    assert stopped.value.diagnostic.context['resolved_path'] == '/other/state'
    assert 'storage_root' in stopped.value.diagnostic.next_action


@pytest.mark.parametrize('text,code', [
    ('garbled retained-secret', 'protocol_invalid'), ('[]', 'protocol_invalid'), ('null', 'protocol_invalid'),
    ('{"submission_protocol":1,"submission_protocol":0,"execution_tracking":1}', 'protocol_invalid'),
    ('{"submission_protocol":1,"execution_tracking":1,"extra":NaN}', 'protocol_invalid'),
    ('[' * 2000 + ']' * 2000, 'protocol_invalid'), ('{}', 'compatibility_mismatch'),
    ('{"submission_protocol":true,"execution_tracking":1}', 'compatibility_mismatch'),
    ('{"submission_protocol":1,"execution_tracking":true}', 'compatibility_mismatch'),
    ('{"submission_protocol":"1","execution_tracking":1}', 'compatibility_mismatch'),
    ('{"submission_protocol":1,"execution_tracking":0}', 'compatibility_mismatch')])
def test_capability_protocol_and_version_errors_are_distinct(monkeypatch, text, code):
    monkeypatch.setattr(subprocess, 'run', lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, text, 'retained-secret'))
    with pytest.raises(DiagnosticError) as stopped:
        operation('helper')()
    assert stopped.value.diagnostic.code == code
    assert 'retained-secret' not in json.dumps(stopped.value.diagnostic.to_dict())
    assert 'update AutoSlurm' in stopped.value.diagnostic.next_action


def test_valid_probes_preserve_command_policy_and_unknown_capabilities(monkeypatch):
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        text = json.dumps({**CAPABILITIES, 'future': {'extra': 'allowed'}}) if '--capabilities' in command[-1] else '/selected/state\n'
        return subprocess.CompletedProcess(command, 0, text, '')
    monkeypatch.setattr(subprocess, 'run', run)
    before = copy.deepcopy(PROFILE)
    assert operation('root')() == '/selected/state'
    assert operation('helper')() is None
    assert PROFILE == before
    assert calls[0][-1].startswith('bash -lc ') and 'STORAGE_ROOT_ENVIRONMENT_VARIABLE' in calls[0][-1]
    assert 'source ' in calls[0][-1]  # Existing trusted operator setup, no launch-policy change.
    assert calls[1][-1].startswith('env AUTOSLURM_STORAGE_ROOT=')
    assert "'/site/env with spaces/bin/python'" in calls[1][-1]
    assert len(calls) == 2


def test_legacy_selected_path_remains_no_contact(monkeypatch):
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: pytest.fail('Legacy path selection contacted SSH'))
    assert remote_storage_root_from_config({**PROFILE, 'path': '/legacy/state'}, 'cluster') == '/legacy/state'


@pytest.mark.parametrize('kind', ['root', 'helper'])
@pytest.mark.parametrize('native', [RuntimeError('unexpected bug'), TypeError('unexpected bug'),
                                   AttributeError('unexpected bug'), KeyboardInterrupt()])
def test_unexpected_probe_bugs_and_keyboard_interrupt_propagate(monkeypatch, kind, native):
    def run(*args, **kwargs):
        raise native
    monkeypatch.setattr(subprocess, 'run', run)
    with pytest.raises(type(native)) as stopped:
        operation(kind)()
    assert stopped.value is native


@pytest.mark.parametrize('entry', [submit.main, lambda args: root.main(['submit', *args])])
@pytest.mark.parametrize('failure', ['root', 'helper'])
@pytest.mark.parametrize('debug', [False, True])
def test_submit_cli_readiness_errors_render_once_before_effects(monkeypatch, capsys, entry, failure, debug):
    profile = {**PROFILE, **({'storage_root': '/selected/state'} if failure == 'root' else {'path': '/selected/state'})}
    save_config({'machines': {'cluster': profile}, 'default_machine': 'cluster'})
    path = save_bundle({'sample': {'name': 'sample', 'script': 'echo science', 'slurm': {}}}, 'study')
    capsys.readouterr()
    calls = []
    native = subprocess.TimeoutExpired(['retained-secret'], 30, output='retained-secret')
    def run(command, **kwargs):
        calls.append(command)
        if command[0] == 'bash':
            return subprocess.CompletedProcess(command, 0, '', '')
        assert command[:6] == ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', 'research-gpu']
        raise native
    monkeypatch.setattr(subprocess, 'run', run)
    args = ['study', '--bundle-file', str(path), *(['--debug'] if debug else [])]
    if debug:
        with pytest.raises(DiagnosticError) as stopped:
            entry(args)
        assert stopped.value.__cause__ is native
    else:
        with pytest.raises(SystemExit) as stopped:
            entry(args)
        assert stopped.value.code == 1
        captured = capsys.readouterr()
        assert not captured.out and captured.err.count('[command_timeout]') == 1
        assert 'research-gpu' in captured.err and 'Next:' in captured.err
        assert 'retained-secret' not in captured.err and 'Traceback' not in captured.err
    assert not list((storage_root() / 'submissions').glob('*'))
    assert not list((storage_root() / 'slurm').glob('*'))
    assert len(list((storage_root() / 'jobs').glob('*.json'))) == 1
    assert sum(command[0] == 'ssh' for command in calls) == 1
