"""Managed jobs select exact verified code and retain producing evidence."""

import copy
from dataclasses import replace
from io import StringIO

import pytest

from autoslurm import ExecutionContext
from autoslurm.bundle_preparation import prepare_bundle
from autoslurm.software_execution import select_software_release, validate_release_manifest
from autoslurm.software_manifest import normalize_software_manifest


COMMIT = 'a' * 40


@pytest.fixture
def release():
    manifest = normalize_software_manifest({'projects': [{'name': 'science', 'repository': 'https://example.invalid/science.git'}]})
    return {'release_id': 'b' * 32, 'state': 'ready', 'observation': {'state': 'observed'},
            'verification': {'state': 'verified'}, 'installation': '/code/releases/id/site-packages',
            'installation_hash': 'digest', 'base_pythonpath': '', 'base_environment': {'prefix': '/runtime'},
            'commands': ['science-command'], 'projects': [{'name': 'science', 'commit': COMMIT, 'modules': ['science']}],
            'request': {'machine': 'fixture', 'software_root': '/code', 'transport': {'ssh_alias': 'research'},
                        'manifest': manifest, 'policy': {'python': '/runtime/bin/python'}}}


@pytest.fixture
def context():
    profile = {'ssh_alias': 'research', 'venv_path': '/helper', 'results_root': '/data', 'software_root': '/code'}
    return ExecutionContext('fixture', profile, '/tracking', '/data', '/data', True, '/code')


def test_explicit_selection_rechecks_exact_release_without_changing_helper_environment(context, release, monkeypatch):
    calls = []
    def inspect(identity, **kwargs):
        calls.append((identity, kwargs))
        return release
    monkeypatch.setattr('autoslurm.software_preparation.inspect_software_release', inspect)
    selected = select_software_release(context, release['release_id'])
    assert calls == [(release['release_id'], {'machine': 'fixture', 'verify': True})]
    assert selected.config == context.config and selected.config['venv_path'] == '/helper'
    assert context.software_release is None


@pytest.mark.parametrize('field,value', [('machine', 'other'), ('software_root', '/different'), ('transport', {'ssh_alias': 'other'})])
def test_release_cannot_be_used_on_another_machine_or_root(context, release, monkeypatch, field, value):
    release['request'][field] = value
    monkeypatch.setattr('autoslurm.software_preparation.inspect_software_release', lambda *a, **kw: release)
    with pytest.raises(ValueError, match='does not match'):
        select_software_release(context, release['release_id'])


@pytest.mark.parametrize('field,value', [('state', 'failed'), ('verification', {'state': 'invalid'}), ('observation', {'state': 'unavailable'})])
def test_ready_or_saved_state_alone_is_insufficient(context, release, monkeypatch, field, value):
    release[field] = value
    monkeypatch.setattr('autoslurm.software_preparation.inspect_software_release', lambda *a, **kw: release)
    with pytest.raises(ValueError, match='freshly verified'):
        select_software_release(context, release['release_id'])


@pytest.mark.parametrize('field,value', [('runtime', 'gpu'), ('repository', 'https://other.invalid/project.git'), ('revision', 'b' * 40)])
def test_bundle_request_must_match_selected_runtime_and_sources(release, field, value):
    manifest = copy.deepcopy(release['request']['manifest'])
    if field == 'runtime':
        manifest[field] = value
    else:
        manifest['projects'][0][field] = value
    with pytest.raises(ValueError, match='does not match'):
        validate_release_manifest(manifest, release)


def test_missing_revision_stays_bound_to_selected_commit_without_upstream_lookup(release):
    validate_release_manifest(release['request']['manifest'], release)
    pinned = copy.deepcopy(release['request']['manifest'])
    pinned['projects'][0]['revision'] = COMMIT
    validate_release_manifest(pinned, release)


@pytest.mark.parametrize('script', ['science.py', './science-command', 'bash something.sh', 'python -m other', 'science-command ; bad'])
def test_managed_jobs_cannot_silently_run_unprepared_source(context, release, script):
    selected = replace(context, software_release=release)
    with pytest.raises(ValueError, match='installed application'):
        prepare_bundle([{'name': 'job', 'script': script}], {'job': []}, selected)


@pytest.mark.parametrize('variable', ['PATH', 'PYTHONPATH', 'PYTHONHOME', 'VIRTUAL_ENV', 'PYTHONSAFEPATH'])
def test_managed_runtime_cannot_be_overridden_in_application_environment(context, release, variable):
    selected = replace(context, software_release=release)
    with pytest.raises(ValueError, match='cannot override'):
        prepare_bundle([{'name': 'job', 'script': 'science-command', 'environment': {variable: 'other'}}], {'job': []}, selected)


def test_managed_script_and_execution_receipt_pin_application_but_keep_data_paths(context, release):
    selected = replace(context, software_release=release)
    job = {'name': 'job', 'script': 'python -m science.run', 'software': release['request']['manifest'],
           'script_args': {'output_dir': 'experiment/run'}, 'environment': {'JAX_ENABLE_X64': '1'}}
    prepared = prepare_bundle([job], {'job': []}, selected).jobs[0]
    assert prepared.execution['resolved_paths']['output_dir'] == '/data/experiment/run'
    assert prepared.execution['software_release']['release_id'] == release['release_id']
    assert '/runtime/bin/python -P -m science.run' in prepared.script
    assert 'PYTHONSAFEPATH=1' in prepared.script
    assert '/helper/bin/activate' not in prepared.script
    assert 'git ' not in prepared.script and 'pip ' not in prepared.script
    assert prepared.definition['script'] == job['script']


def test_job_data_cannot_overwrite_managed_installations(context, release):
    context = replace(context, results_root='/code', project_root='/code', software_release=release)
    job = {'name': 'job', 'script': 'science-command', 'script_args': {'output_dir': 'releases/id'}}
    with pytest.raises(ValueError, match='outside managed'):
        prepare_bundle([job], {'job': []}, context)


def test_supplied_context_does_not_bypass_fresh_release_verification(context, release, monkeypatch):
    from autoslurm import submit_jobs
    context = replace(context, software_release=release)
    calls = []
    def failed_check(actual, identity):
        calls.append(identity)
        raise ValueError('invalid release')
    monkeypatch.setattr('autoslurm.job_runner.select_software_release', failed_check)
    with pytest.raises(ValueError, match='invalid release'):
        submit_jobs('study', context=context)
    assert calls == [release['release_id']]
