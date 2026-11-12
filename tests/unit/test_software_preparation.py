"""Preparation identity, immutable-base policy, recovery and CLI safety."""

import copy
import json
from pathlib import Path
from subprocess import CompletedProcess, TimeoutExpired
from types import SimpleNamespace

import pytest

from autoslurm import prepare_software, inspect_software_release, SoftwarePreparationError, save_config, storage
from autoslurm.apps import software
from autoslurm.software_policy import runtime_policy, release_identifier
from autoslurm.software_manifest import normalize_software_manifest
from autoslurm.software_worker import launcher_script
from autoslurm import software_preparation as preparation
from autoslurm import software_releases as releases


ID = 'a' * 32
COMMIT = 'b' * 40


def manifest():
    return normalize_software_manifest({'projects': [{'name': 'science', 'repository': 'https://example.invalid/science.git'}]})


@pytest.fixture
def profile(tmp_path):
    value = {'software_root': str(tmp_path / 'software'), 'venv_path': '/science/env', 'ssh_alias': 'research'}
    save_config({'default_machine': 'fixture', 'machines': {'fixture': value}})
    return value


def request(tmp_path):
    return {'protocol': 1, 'release_id': ID, 'machine': 'fixture', 'transport': {},
            'software_root': str(tmp_path / 'software'), 'manifest': manifest(),
            'policy': {'name': 'default', 'python': '/science/env/bin/python', 'dependency_mode': 'existing_environment'}}


def test_runtime_policy_preserves_machine_base_and_supports_named_policy():
    assert runtime_policy({'venv_path': '/env'})['python'] == '/env/bin/python'
    policy = runtime_policy({'software_runtimes': {'gpu': {'python': '/gpu/bin/python', 'constraints': '/gpu/pins.txt'}}}, 'gpu')
    assert policy['constraints'] == '/gpu/pins.txt'
    assert policy['dependency_mode'] == 'existing_environment'


@pytest.mark.parametrize('profile,runtime', [({}, 'default'), ({'venv_path': '/env'}, 'absent'),
    ({'software_runtimes': {'default': {'python': 'relative'}}}, 'default'),
    ({'software_runtimes': {'default': {'python': '/env/python', 'install': True}}}, 'default'),
    ({'software_runtimes': []}, 'default'), ({'software_runtimes': {'default': None}}, 'default')])
def test_invalid_runtime_policy_cannot_select_a_fallback(profile, runtime):
    with pytest.raises(ValueError):
        runtime_policy(profile, runtime)


@pytest.mark.parametrize('value', ['../other', 'latest', '', 'a' * 31, 'A' * 32, None])
def test_release_selector_requires_exact_identity(value):
    with pytest.raises(ValueError):
        release_identifier(value)


@pytest.mark.parametrize('argv', [[], ['prepare'], ['status']])
def test_incomplete_software_commands_show_help_without_loading_config(monkeypatch, capsys, argv):
    monkeypatch.setattr(preparation, 'load_config', lambda: pytest.fail('Help must not discover machines'))
    software.main(argv)
    assert 'usage:' in capsys.readouterr().out


def test_local_origin_is_literal_and_missing_revision_is_latest(tmp_path, monkeypatch):
    (tmp_path / 'pyproject.toml').write_text('[project]\nname="science"\n')
    def git(command, **options):
        if '--get' in command:
            assert command[-1] == 'remote.origin.url'
            return CompletedProcess(command, 0, 'https://example.invalid/science.git\n', '')
        return CompletedProcess(command, 0, str(tmp_path) + '\n', '')
    monkeypatch.setattr(preparation.subprocess, 'run', git)
    result = preparation._local_project_manifest(tmp_path, None)
    assert result['projects'][0]['revision'] is None
    assert result['projects'][0]['subdirectory'] == '.'


def test_identity_is_durable_before_dispatch_and_ready_result_is_saved(profile, monkeypatch):
    def dispatch(req, action):
        saved = json.loads(preparation._reference_path(req['release_id']).read_text())
        assert saved['state'] == 'requested' and saved['request'] == req
        assert action == 'prepare' and req['transport'] == {'ssh_alias': 'research'}
        return {**saved, 'state': 'ready'}
    monkeypatch.setattr(preparation, '_dispatch', dispatch)
    result = prepare_software(manifest())
    assert result['state'] == 'ready'
    assert json.loads(preparation._reference_path(result['release_id']).read_text()) == result


@pytest.mark.parametrize('failure', [TimeoutExpired('ssh', 10), KeyboardInterrupt(), ValueError('bad packet')])
def test_lost_response_retains_unknown_identity_and_does_not_retry(profile, monkeypatch, failure):
    calls = []
    def lost(req, action):
        calls.append((req, action))
        raise failure
    monkeypatch.setattr(preparation, '_dispatch', lost)
    with pytest.raises(SoftwarePreparationError) as caught:
        prepare_software(manifest())
    record = caught.value.evidence
    assert record['state'] == 'unknown'
    assert json.loads(preparation._reference_path(record['release_id']).read_text()) == record
    assert len(calls) == 1


def test_exact_inspection_uses_recorded_alias_and_root_after_profile_changes(profile, monkeypatch):
    req = request(Path(profile['software_root']).parent)
    req['transport'] = {'ssh_alias': 'original-alias'}
    preparation.atomic_json(preparation._reference_path(ID), {'version': 1, 'state': 'unknown', 'request': req, 'release_id': ID})
    seen = []
    def dispatch(actual, action):
        seen.append((actual, action))
        return {'version': 1, 'release_id': ID, 'request': actual, 'state': 'ready'}
    monkeypatch.setattr(preparation, '_dispatch', dispatch)
    result = inspect_software_release(ID, verify=True)
    assert seen == [(req, 'verify')]
    assert result['observation']['state'] == 'observed'
    with pytest.raises(ValueError, match='another machine'):
        inspect_software_release(ID, machine='other')


def test_failed_inspection_reports_stale_evidence_without_retry(tmp_path, monkeypatch):
    req = request(tmp_path)
    saved = {'version': 1, 'state': 'ready', 'request': req, 'release_id': ID}
    preparation.atomic_json(preparation._reference_path(ID), saved)
    monkeypatch.setattr(preparation, '_dispatch', lambda *args: (_ for _ in ()).throw(OSError('offline')))
    result = inspect_software_release(ID, verify=True)
    assert result['state'] == 'ready'
    assert result['observation']['state'] == 'unavailable'
    assert json.loads(preparation._reference_path(ID).read_text()) == saved


def test_local_tracking_failure_prevents_dispatch(profile, monkeypatch):
    monkeypatch.setattr(preparation, 'atomic_json', lambda *a, **kw: (_ for _ in ()).throw(OSError('disk full')))
    monkeypatch.setattr(preparation, '_dispatch', lambda *args: pytest.fail('Cannot dispatch without durable identity'))
    with pytest.raises(OSError):
        prepare_software(manifest())


def test_remote_worker_uses_one_alias_and_no_installed_autoslurm(tmp_path, monkeypatch):
    req = request(tmp_path)
    req['transport'] = {'ssh_alias': 'research'}
    calls = []
    def ssh(command, **options):
        calls.append(command)
        assert command[-2:] == ['research', 'python3 -B -']
        assert 'from autoslurm ' not in options['input']
        assert 'autoslurm_worker.software_releases' in options['input']
        return CompletedProcess(command, 0, json.dumps({'version': 1, 'release_id': ID, 'request': req, 'state': 'building'}), '')
    monkeypatch.setattr(preparation.subprocess, 'run', ssh)
    assert preparation._dispatch(req, 'prepare')['state'] == 'building'
    assert len(calls) == 1


@pytest.mark.parametrize('reply', ['{}', 'not JSON', '{"state":"ready"}'])
def test_invalid_remote_payload_does_not_become_ready(tmp_path, monkeypatch, reply):
    monkeypatch.setattr(preparation.subprocess, 'run', lambda command, **kw: CompletedProcess(command, 0, reply, ''))
    with pytest.raises(ValueError):
        preparation._dispatch(request(tmp_path), 'prepare')


def test_failed_cli_preserves_id_and_prints_recovery_command(monkeypatch, capsys):
    def failed(**kw):
        raise SoftwarePreparationError('interrupted', {'release_id': ID, 'state': 'unknown'})
    monkeypatch.setattr(software, 'prepare_software', failed)
    with pytest.raises(SystemExit) as caught:
        software.main(['prepare', '--local-project', '.', '--machine', 'fixture'])
    assert caught.value.code == 1
    output = capsys.readouterr().out
    assert ID in output and 'status --release' in output and 'Traceback' not in output


def test_failed_cli_json_is_structured_evidence(monkeypatch, capsys):
    monkeypatch.setattr(software, 'prepare_software', lambda **kw: (_ for _ in ()).throw(
        SoftwarePreparationError('build failed', {'release_id': ID, 'state': 'failed'})))
    with pytest.raises(SystemExit):
        software.main(['prepare', '--local-project', '.', '--json'])
    assert json.loads(capsys.readouterr().out)['release_id'] == ID


@pytest.fixture
def host(tmp_path, monkeypatch):
    req = request(tmp_path)
    baseline = {'python': req['policy']['python'], 'prefix': '/science/env', 'inventory': {}, 'commands': [], 'errors': []}
    artifact = {**req['manifest']['projects'][0], 'commit': COMMIT, 'distribution': 'science', 'version': '1', 'modules': ['science']}
    monkeypatch.setattr(releases, '_inspect', lambda *a, **kw: {**baseline, 'commands': ['science'] if kw.get('artifacts') else []})
    monkeypatch.setattr(releases, 'prepare_software_sources', lambda *a, **kw: {'preparation_id': 's', 'projects': [artifact]})
    def build(projects, directory, policy, progress):
        progress('building', 'science')
        return projects
    monkeypatch.setattr(releases, 'build_wheels', build)
    def install(*args):
        path = Path(args[1]) / 'site-packages'
        path.mkdir()
        (path / 'science.py').write_text('code')
        return path
    monkeypatch.setattr(releases, 'install_wheels', install)
    return req


def test_host_readiness_is_published_after_installation_and_never_replays(host, monkeypatch):
    record = releases.operate_release(host, 'prepare', '')
    assert record['state'] == 'ready'
    assert record['installation_hash']
    monkeypatch.setattr(releases, 'build_wheels', lambda *a, **kw: pytest.fail('No replays'))
    assert releases.operate_release(host, 'prepare', '') == record
    assert releases.operate_release(host, 'verify', '')['verification']['state'] == 'verified'


@pytest.mark.parametrize('stage,owner', [('preparing_sources', 'prepare_software_sources'), ('building', 'build_wheels'), ('installing', 'install_wheels')])
def test_host_failure_preserves_stage_and_partial_evidence(host, monkeypatch, stage, owner):
    def fail(*args):
        if owner == 'build_wheels':
            args[-1]('building', 'science')
        raise OSError('private raw output')
    monkeypatch.setattr(releases, owner, fail)
    result = releases.operate_release(host, 'prepare', '')
    assert result['state'] == 'failed' and result['error']['stage'] == stage
    assert 'private raw output' not in json.dumps(result)
    assert releases.operate_release(host, 'inspect', '') == result


def test_existing_identity_collision_cannot_replace_evidence(host):
    record = releases.operate_release(host, 'prepare', '')
    conflict = copy.deepcopy(host)
    conflict['policy']['python'] = '/other/python'
    with pytest.raises(ValueError, match='another request'):
        releases.operate_release(conflict, 'prepare', '')
    assert releases.operate_release(host, 'inspect', '') == record


def test_missing_record_inspection_creates_no_remote_directories(tmp_path):
    result = releases.operate_release(request(tmp_path), 'inspect', '')
    assert result['state'] == 'missing'
    assert not (tmp_path / 'software').exists()


def test_content_and_base_changes_invalidate_ready_release(host, monkeypatch):
    record = releases.operate_release(host, 'prepare', '')
    (Path(record['installation']) / 'science.py').write_text('changed')
    checked = releases.verify_release(record, '')
    assert checked['verification']['state'] == 'invalid'
    assert 'content has changed' in checked['verification']['errors'][0]
    monkeypatch.setattr(releases, '_inspect', lambda *a, **kw: {'changed': True, 'errors': []})
    checked = releases.verify_release(record, '')
    assert any('base Python' in error for error in checked['verification']['errors'])


def test_ready_record_publication_failure_is_not_reported_as_success(host, monkeypatch):
    real_write = releases.atomic_json
    def write(path, record, **options):
        if record['state'] == 'ready':
            raise OSError('disk full')
        return real_write(path, record, **options)
    monkeypatch.setattr(releases, 'atomic_json', write)
    result = releases.operate_release(host, 'prepare', '')
    assert result['state'] == 'failed' and result['error']['stage'] == 'publication'
    assert releases.operate_release(host, 'inspect', '')['state'] == 'failed'


def test_competing_request_observes_progress_and_cannot_start_second_build(host, monkeypatch):
    seen = []
    def sources(*a, **kw):
        seen.append(releases.operate_release(host, 'prepare', '')['state'])
        return {'preparation_id': 's', 'projects': []}
    monkeypatch.setattr(releases, 'prepare_software_sources', sources)
    releases.operate_release(host, 'prepare', '')
    assert seen == ['preparing_sources']


def test_invalid_saved_reference_cannot_redirect_inspection(monkeypatch):
    preparation.atomic_json(preparation._reference_path(ID), {'version': 1, 'release_id': ID, 'request': {}})
    monkeypatch.setattr(preparation, '_dispatch', lambda *a: pytest.fail('Invalid reference must not dispatch'))
    with pytest.raises(ValueError, match='Invalid saved preparation'):
        inspect_software_release(ID)
