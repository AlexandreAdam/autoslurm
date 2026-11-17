"""Status failures are bounded observations, not clean code or compatible runtimes."""

import copy
import errno
import json
from pathlib import Path
import subprocess

import pytest

from autoslurm import inspect_software, software_expectations, save_config
from autoslurm.apps import root as cli
from autoslurm.errors import DiagnosticError, InvalidRequestError
from autoslurm.environment_probe import inspect_environment


@pytest.fixture
def selected(tmp_path):
    directory = tmp_path / 'software'
    directory.mkdir()
    profile = {'software_root': str(directory), 'venv_path': '/selected/env', 'ssh_alias': 'research-cluster'}
    save_config({'machines': {'cluster': profile}, 'default_machine': 'cluster'})
    return directory, profile


def observation(directory, *, projects=None):
    return {'version': 1, 'software_root': str(directory), 'state': 'observed',
            'observed_at': '2026-11-17T12:00:00+00:00', 'projects': projects or [], 'truncated': False}


def checkout(directory, name, **values):
    return {'name': name, 'path': str(directory / name), 'state': 'observed',
            'commit': 'a' * 40, 'branch': 'main', 'dirty': False, 'bare': False, **values}


def environment():
    return {'state': 'observed', 'prefix': '/selected/env', 'selected_python': '/selected/env/bin/python',
            'identity_verified': True, 'python_version': '3.13.1',
            'markers': {'python_version': '3.13', 'sys_platform': 'linux'},
            'packages': {name: {'state': 'missing'} for name in ('numpy', 'jax', 'jaxlib', 'torch', 'scipy')}}


def reply(monkeypatch, data):
    monkeypatch.setattr(subprocess, 'run', lambda command, **kw: subprocess.CompletedProcess(command, 0, json.dumps(data), ''))


@pytest.mark.parametrize('fault,code', [('missing', 'command_unavailable'), ('denied', 'command_unavailable'),
    ('io', 'transport_failed'), ('timeout', 'command_timeout'), ('encoding', 'protocol_invalid'),
    ('ssh255', 'transport_failed'), ('remote127', 'command_failed'), ('signal', 'operation_interrupted'),
    ('bool', 'protocol_invalid')])
def test_whole_probe_failures_retain_native_cause_and_no_mutation(selected, monkeypatch, fault, code):
    natives = {'missing': FileNotFoundError(errno.ENOENT, 'retained-secret'),
        'denied': PermissionError(errno.EACCES, 'retained-secret'), 'io': OSError(errno.EIO, 'retained-secret'),
        'timeout': subprocess.TimeoutExpired(['retained-secret'], 60),
        'encoding': UnicodeDecodeError('utf-8', b'\xff', 0, 1, 'retained-secret')}
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        assert kwargs['timeout'] == 60 and 'BatchMode=yes' in command
        if fault in natives:
            raise natives[fault]
        return subprocess.CompletedProcess(command, {'ssh255': 255, 'remote127': 127, 'signal': -15, 'bool': True}[fault], '', 'retained-secret')
    monkeypatch.setattr(subprocess, 'run', run)
    with pytest.raises(DiagnosticError) as stopped:
        inspect_software()
    diagnostic = stopped.value.diagnostic
    assert diagnostic.code == code and diagnostic.context['ssh_alias'] == 'research-cluster'
    assert diagnostic.effects == {'git_pull': 'not_started', 'editable_install': 'not_started'}
    assert 'retained-secret' not in json.dumps(diagnostic.to_dict())
    assert len(calls) == 1 and calls[0][-1] == 'python3 -B -'
    if fault in natives:
        assert stopped.value.__cause__ is natives[fault]


@pytest.mark.parametrize('fault', ['garbage', 'duplicate', 'bool-version', 'wrong-root', 'list-state',
    'too-many', 'deep', 'oversized', 'surrogate', 'not-text'])
def test_invalid_whole_identity_never_falls_back(selected, monkeypatch, fault):
    directory, _ = selected
    data = observation(directory)
    if fault == 'bool-version': data['version'] = True
    if fault == 'wrong-root': data['software_root'] = '/another/root'
    if fault == 'list-state': data['state'] = []
    if fault == 'too-many': data['projects'] = [checkout(directory, str(i)) for i in range(21)]
    text = json.dumps(data)
    text = {'garbage': 'banner', 'duplicate': text[:-1] + ', "version": 1}',
            'deep': '[' * 1500 + ']' * 1500, 'oversized': 'x' * (1048576 + 1),
            'surrogate': '\ud800', 'not-text': None}.get(fault, text)
    monkeypatch.setattr(subprocess, 'run', lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, text, 'retained-secret'))
    with pytest.raises(DiagnosticError) as stopped:
        inspect_software()
    assert stopped.value.diagnostic.code == 'protocol_invalid'


@pytest.mark.parametrize('bad', [None, [], {}, {'name': '../escape'}, {'name': 'bad', 'path': '/wrong'},
    {'name': 'bad', 'commit': 'not-a-commit'}, {'name': 'bad', 'dirty': 'false'}])
def test_bad_project_rows_preserve_healthy_neighbours(selected, monkeypatch, bad):
    directory, _ = selected
    reply(monkeypatch, observation(directory, projects=[checkout(directory, 'healthy'), bad]))
    result = inspect_software()
    assert result['projects'][0]['dirty'] is False and result['projects'][0]['commit'] == 'a' * 40
    assert result['projects'][1]['state'] == 'unavailable'
    assert result['projects'][1]['dirty'] is None and result['projects'][1]['diagnostic']['code'] == 'protocol_invalid'
    json.dumps(result)


@pytest.mark.parametrize('number', [errno.EACCES, errno.EIO, errno.ELOOP])
def test_root_metadata_failure_is_not_missing(selected, monkeypatch, number):
    directory, profile = selected
    profile.pop('ssh_alias')
    save_config({'machines': {'cluster': profile}, 'default_machine': 'cluster'})
    original = Path.stat
    def stat(path, *a, **kw):
        if path == directory:
            raise OSError(number, 'retained-secret')
        return original(path, *a, **kw)
    monkeypatch.setattr(Path, 'stat', stat)
    result = inspect_software()
    assert result['state'] == 'unavailable'
    assert result['diagnostic']['code'] == 'resource_inaccessible'
    assert result['diagnostic']['cause']['errno'] == number
    assert 'retained-secret' not in json.dumps(result)


@pytest.mark.parametrize('stage', ['repository', 'commit', 'branch', 'status'])
@pytest.mark.parametrize('fault', ['missing', 'timeout', 'exit', 'encoding'])
def test_git_failure_preserves_known_commit_and_other_projects(selected, monkeypatch, stage, fault):
    directory, profile = selected
    profile.pop('ssh_alias')
    save_config({'machines': {'cluster': profile}, 'default_machine': 'cluster'})
    for name in ('bad', 'healthy'):
        (directory / name / '.git').mkdir(parents=True)
    calls = []
    def git(command, **kwargs):
        calls.append(command)
        current = 'repository' if '--is-bare-repository' in command else 'commit' if 'rev-parse' in command else 'branch' if 'symbolic-ref' in command else 'status'
        if command[2].endswith('/bad') and current == stage:
            if fault == 'missing': raise FileNotFoundError(errno.ENOENT, 'retained-secret')
            if fault == 'timeout': raise subprocess.TimeoutExpired(command, 5)
            if fault == 'encoding': raise UnicodeDecodeError('utf-8', b'\xff', 0, 1, 'retained-secret')
            return subprocess.CompletedProcess(command, 128, '', 'retained-secret')
        text = {'repository': 'false', 'commit': 'a' * 40, 'branch': 'main', 'status': ''}[current]
        return subprocess.CompletedProcess(command, 0, text, '')
    monkeypatch.setattr(subprocess, 'run', git)
    result = inspect_software()
    bad, healthy = result['projects']
    assert bad['state'] == 'unavailable' and bad['dirty'] is None
    assert bad['diagnostic']['stage'] == 'git_' + stage
    assert bad['commit'] == ('a' * 40 if stage in ('branch', 'status') else None)
    assert healthy['state'] == 'observed' and healthy['dirty'] is False
    assert all(cmd[0] == 'git' and not set(cmd) & {'pull', 'fetch', 'install', 'checkout'} for cmd in calls)
    assert 'retained-secret' not in json.dumps(result)


@pytest.mark.parametrize('bad', [None, [], {'state': 'installed', 'version': None},
                               {'state': 'installed', 'version': True}, {'state': 'missing', 'source_dirty': 'false'}])
def test_bad_package_metadata_retains_good_versions(selected, monkeypatch, tmp_path, bad):
    directory, _ = selected
    requirements = tmp_path / 'requirements.txt'
    requirements.write_text('numpy<2\njax>=0.4\n')
    expected = software_expectations(requirements=requirements)
    before = copy.deepcopy(expected)
    data = observation(directory)
    data['environment'] = environment()
    data['environment']['packages'].update(numpy={'state': 'installed', 'version': '1.26.4'}, jax=bad)
    reply(monkeypatch, data)
    result = inspect_software(expectations=expected)
    assert result['environment']['packages']['numpy']['version'] == '1.26.4'
    assert result['environment']['packages']['jax']['diagnostic']['code'] in ('protocol_invalid', 'observation_unavailable')
    assert result['compatibility']['state'] == 'unknown'
    assert expected == before


def test_bad_source_metadata_retains_installed_version(selected, monkeypatch, tmp_path):
    directory, _ = selected
    data = observation(directory)
    data['environment'] = environment()
    data['environment']['packages']['numpy'] = {'state': 'installed', 'version': '1.26.4', 'source_commit': 'invalid'}
    reply(monkeypatch, data)
    expected = software_expectations(package='numpy', expected_version='1.26.4')
    result = inspect_software(expectations=expected)
    assert result['environment']['packages']['numpy']['version'] == '1.26.4'
    assert result['compatibility']['state'] == 'unknown'


@pytest.mark.parametrize('identity', ['wrong', 'absent', 'bool'])
def test_unverified_environment_keeps_git_evidence(selected, monkeypatch, identity):
    directory, _ = selected
    data = observation(directory, projects=[checkout(directory, 'healthy')])
    data['environment'] = environment()
    if identity == 'wrong': data['environment']['selected_python'] = '/another/env/bin/python'
    if identity == 'absent': data['environment'].pop('identity_verified')
    if identity == 'bool': data['environment']['identity_verified'] = 1
    reply(monkeypatch, data)
    result = inspect_software(expectations=software_expectations())
    assert result['projects'][0]['commit'] == 'a' * 40
    assert result['environment']['state'] == 'unavailable' and result['compatibility']['state'] == 'unknown'


@pytest.mark.parametrize('part', ['lookup', 'version', 'source'])
def test_distribution_worker_retains_partial_metadata_without_imports(monkeypatch, part):
    class Distribution:
        @property
        def version(self):
            if part == 'version': raise OSError(errno.EIO, 'retained-secret')
            return '1.26.4'
        def locate_file(self, path): return '/selected/env/site-packages'
        def read_text(self, path): return '[]' if part == 'source' else None
    def distribution(name):
        if name == 'bad' and part == 'lookup': raise PermissionError(errno.EACCES, 'retained-secret')
        return Distribution()
    monkeypatch.setattr('importlib.metadata.distribution', distribution)
    result = inspect_environment(['bad', 'healthy'])
    bad = result['packages']['bad']
    assert bad['state'] == ('installed' if part == 'source' else 'unavailable')
    if part == 'source': assert bad['version'] == '1.26.4' and bad['metadata_warning']
    assert 'retained-secret' not in json.dumps(result)


@pytest.mark.parametrize('fault', ['missing', 'encoding', 'toml', 'shape'])
def test_local_declarations_report_exact_path_and_native_causes(tmp_path, fault):
    path = tmp_path / ('pyproject.toml' if fault in ('toml', 'shape') else 'requirements.txt')
    if fault == 'encoding': path.write_bytes(b'\xff')
    if fault == 'toml': path.write_text('[broken')
    if fault == 'shape': path.write_text('[project]\ndependencies="numpy"\n')
    with pytest.raises(DiagnosticError) as stopped:
        software_expectations(local_project=tmp_path) if fault in ('toml', 'shape') else software_expectations(requirements=path)
    assert stopped.value.diagnostic.context['path'] == str(path)
    if fault != 'shape': assert stopped.value.__cause__ is not None


@pytest.mark.parametrize('kwargs', [{'limit': True}, {'limit': 0}, {'machine': ''}, {'expectations': []},
    {'expectations': {}}, {'project': '../escape'}])
def test_bad_inspection_requests_stop_before_any_query(selected, monkeypatch, kwargs):
    monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: pytest.fail('Invalid input reached SSH'))
    with pytest.raises(InvalidRequestError): inspect_software(**kwargs)


@pytest.mark.parametrize('as_json,debug', [(False, False), (True, False), (False, True)])
def test_status_cli_has_shared_error_json_and_debug(selected, monkeypatch, capsys, as_json, debug):
    native = FileNotFoundError(errno.ENOENT, 'retained-secret')
    def run(*a, **kw): raise native
    monkeypatch.setattr(subprocess, 'run', run)
    with pytest.raises(DiagnosticError if debug else SystemExit) as stopped:
        cli.main(['software', 'status', '--machine', 'cluster', *(['--json'] if as_json else []), *(['--debug'] if debug else [])])
    if debug:
        assert stopped.value.__cause__ is native
    else:
        assert stopped.value.code == 1
        output = capsys.readouterr()
        if as_json: assert json.loads(output.out)['diagnostic']['code'] == 'command_unavailable' and not output.err
        else: assert output.err.count('[command_unavailable]') == 1 and 'Next:' in output.err and not output.out
        assert 'retained-secret' not in output.out + output.err


@pytest.mark.parametrize('native', [TypeError('bug'), KeyboardInterrupt('interrupted')])
def test_status_does_not_hide_programming_errors_or_interrupts(selected, monkeypatch, native):
    def run(*a, **kw): raise native
    monkeypatch.setattr(subprocess, 'run', run)
    with pytest.raises(type(native)) as stopped:
        cli.main(['software', 'status', '--machine', 'cluster'])
    assert stopped.value is native


@pytest.mark.parametrize('fault,code', [('missing', 'command_unavailable'), ('timeout', 'command_timeout'),
    ('encoding', 'protocol_invalid'), ('exit', 'command_failed'), ('identity', 'compatibility_mismatch'),
    ('bad-json', 'protocol_invalid'), ('duplicate', 'protocol_invalid')])
def test_environment_failure_keeps_git_and_names_attempted_python(selected, monkeypatch, fault, code):
    directory, profile = selected
    profile.pop('ssh_alias')
    save_config({'machines': {'cluster': profile}, 'default_machine': 'cluster'})
    (directory / 'healthy' / '.git').mkdir(parents=True)
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        if command[0] == '/selected/env/bin/python':
            if fault == 'missing': raise FileNotFoundError(errno.ENOENT, 'retained-secret')
            if fault == 'timeout': raise subprocess.TimeoutExpired(command, 25)
            if fault == 'encoding': raise UnicodeDecodeError('utf-8', b'\xff', 0, 1, 'retained-secret')
            value = environment()
            if fault == 'identity': value['prefix'] = '/another/env'
            text = 'invalid' if fault == 'bad-json' else json.dumps(value)
            if fault == 'duplicate': text = text[:-1] + ', "prefix": "/selected/env"}'
            return subprocess.CompletedProcess(command, 1 if fault == 'exit' else 0, text, 'retained-secret')
        assert command[0] == 'git'
        text = 'false' if '--is-bare-repository' in command else 'a' * 40 if 'rev-parse' in command else 'main' if 'symbolic-ref' in command else ''
        return subprocess.CompletedProcess(command, 0, text, '')
    monkeypatch.setattr(subprocess, 'run', run)
    result = inspect_software(expectations=software_expectations())
    assert result['projects'][0]['dirty'] is False
    diagnostic = result['environment']['diagnostic']
    assert diagnostic['code'] == code and diagnostic['context']['executable'] == '/selected/env/bin/python'
    assert result['compatibility']['state'] == 'unknown'
    assert len([command for command in calls if command[0] != 'git']) == 1
    assert 'retained-secret' not in json.dumps(result)


@pytest.mark.parametrize('as_json', [False, True])
def test_cli_keeps_partial_evidence_and_actionable_reason(selected, monkeypatch, capsys, as_json):
    directory, _ = selected
    reply(monkeypatch, observation(directory, projects=[checkout(directory, 'healthy'), {'state': 'observed'}]))
    with pytest.raises(SystemExit) as stopped:
        cli.main(['software', 'status', '--machine', 'cluster', *(['--json'] if as_json else [])])
    assert stopped.value.code == 1
    output = capsys.readouterr()
    assert not output.err
    if as_json:
        result = json.loads(output.out)
        assert result['projects'][0]['commit'] == 'a' * 40
        assert result['projects'][1]['diagnostic']['code'] == 'protocol_invalid'
    else:
        assert 'healthy: main' in output.out and output.out.count('[protocol_invalid]') == 1 and 'Next:' in output.out


def test_mismatch_is_a_finding_with_diagnostic_not_a_failed_request(selected, monkeypatch, tmp_path):
    directory, _ = selected
    path = tmp_path / 'requirements.txt'
    path.write_text('numpy<2\n')
    data = observation(directory)
    data['environment'] = environment()
    data['environment']['packages']['numpy'] = {'state': 'installed', 'version': '2.0'}
    reply(monkeypatch, data)
    result = inspect_software(expectations=software_expectations(requirements=path))
    assert result['compatibility']['state'] == 'potential_problem'
    check = result['compatibility']['checks'][0]
    assert check['installed'] == '2.0' and check['diagnostic']['code'] == 'compatibility_mismatch'


def test_bad_target_marker_version_is_unknown_without_workstation_fallback(selected, monkeypatch, tmp_path):
    directory, _ = selected
    path = tmp_path / 'requirements.txt'
    path.write_text('numpy<2; python_version < "3.12"\n')
    data = observation(directory)
    data['environment'] = environment()
    data['environment']['markers']['python_version'] = 'unreadable-version'
    reply(monkeypatch, data)
    result = inspect_software(expectations=software_expectations(requirements=path))
    assert result['compatibility']['state'] == 'unknown'


@pytest.mark.parametrize('where', ['root', 'project', 'package'])
def test_missing_state_with_failed_observation_is_unavailable(selected, monkeypatch, where):
    directory, _ = selected
    data = observation(directory)
    failure = {'stage': 'read_software_root' if where == 'root' else 'read_project' if where == 'project' else 'read_distribution',
               'problem': 'resource_inaccessible', 'kind': 'PermissionError', 'errno': 13, 'returncode': None}
    expected = None
    if where == 'root':
        data.update(state='missing', failure=failure)
    elif where == 'project':
        data['projects'] = [checkout(directory, 'bad', state='missing', commit=None, branch=None, dirty=None, failure=failure)]
    else:
        data['environment'] = environment()
        data['environment']['packages']['numpy'] = {'state': 'missing', 'failure': failure}
        expected = software_expectations(package='numpy')
    reply(monkeypatch, data)
    result = inspect_software(expectations=expected)
    item = result if where == 'root' else result['projects'][0] if where == 'project' else result['environment']['packages']['numpy']
    assert item['state'] == 'unavailable' and item['diagnostic']['code'] == 'protocol_invalid'
    if where == 'package': assert result['compatibility']['state'] == 'unknown'
