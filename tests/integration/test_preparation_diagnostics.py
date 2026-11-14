"""Pure path/render failures retain identity without publishing or dispatching."""

import copy
from datetime import datetime
from io import StringIO
import json
import subprocess

import pytest

from autoslurm import (InvalidRequestError, SelectionError, execution_context_from_snapshot,
                      path_exists, preview_bundle, recorded_execution, resolve_results_path,
                      save_bundle, submit_jobs)
from autoslurm.apps import root, submit
from autoslurm.bundle_preparation import prepare_bundle
from autoslurm.config import save_config
from autoslurm.execution import EXECUTION_METADATA_KEY, ExecutionContext, resolve_execution_context
from autoslurm.job_to_slurm import create_slurm_script, validate_slurm_content, write_slurm_content
from autoslurm.storage import jobs_dir, slurm_dir, storage_root


def context():
    return resolve_execution_context('mock', {'results_root': '/science', 'env_command': 'true'})


def job():
    return {'name': 'fit', 'script': 'science fit', 'slurm': {},
            'script_args': {'input': 'data/input', 'output_dir': 'run/fit'}, 'input_args': ['input']}


def forbidden(*args, **kwargs):
    pytest.fail('Pure validation reached an external command')


@pytest.mark.parametrize('value,base', [(None, 'results'), ('', 'results'), (3, 'results'),
    ('../escape', 'results'), ('a\nb', 'results'), ('a\x00b', 'results'),
    ('file', 'unknown'), ('file', [])])
def test_path_validation_has_machine_and_named_field_without_commands(value, base, monkeypatch):
    monkeypatch.setattr(subprocess, 'run', forbidden)
    with pytest.raises(InvalidRequestError) as stopped:
        context().resolve_path(value, base)
    diagnostic = stopped.value.diagnostic
    assert diagnostic.code == 'invalid_argument' and diagnostic.stage == 'resolve_path'
    assert diagnostic.context['machine'] == 'mock' and diagnostic.context['field'] == 'path'
    assert diagnostic.effects == {}
    if isinstance(value, str):
        assert 'logical_path' in diagnostic.context


@pytest.mark.parametrize('change,field,option', [
    ({'script_args': {'input': '../outside'}}, 'script_args', 'input'),
    ({'script_args': {'input': '/outside'}}, 'script_args', 'input'),
    ({'script_args': {}}, 'script_args', 'input'),
    ({'working_directory': '../outside'}, 'working_directory', None),
    ({'slurm': {'output': '../outside'}}, 'slurm.output', None),
    ({'slurm': {'output': 1}}, 'slurm.output', None),
    ({'slurm': {'chdir': 'other'}}, 'slurm.chdir', None),
    ({'path_args': ['input']}, 'input_args', 'input'),
    ({'input_args': 'input'}, 'input_args', None),
    ({'script_args': []}, 'script_args', None),
    ({'slurm': []}, 'slurm', None),
])
def test_job_resolution_reports_precise_field_and_does_not_mutate(change, field, option, monkeypatch):
    definition = {**job(), **change}
    before = copy.deepcopy(definition)
    monkeypatch.setattr(subprocess, 'run', forbidden)
    with pytest.raises(InvalidRequestError) as stopped:
        context().resolve_job(definition)
    facts = stopped.value.diagnostic.to_dict()
    assert facts['context']['job'] == 'fit' and facts['context']['machine'] == 'mock'
    assert facts['context']['field'] == field
    if option:
        assert facts['context']['option'] == option
    assert definition == before and facts['effects'] == {}


def test_path_error_retains_logical_and_candidate_resolved_path():
    definition = job()
    definition['script_args']['input'] = '../outside'
    with pytest.raises(InvalidRequestError) as stopped:
        context().resolve_job(definition)
    assert stopped.value.diagnostic.context['logical_path'] == '../outside'
    assert stopped.value.diagnostic.context['resolved_path'] == '/science/../outside'


@pytest.mark.parametrize('root', [None, 'relative', '/science/../other', '/science\nother'])
def test_manually_constructed_context_rejects_unusable_path_base(root):
    selected = ExecutionContext('mock', {}, '/state', root, root, False)
    with pytest.raises(InvalidRequestError):
        selected.resolve_path('file')


@pytest.mark.parametrize('change,field', [
    ({'environment': {'KEY': 'retained-secret\nother'}}, 'environment'),
    ({'runtime_environment': {'KEY': '${retained-secret}'}}, 'runtime_environment'),
    ({'environment': {'KEY': 'retained-secret'}, 'runtime_environment': {'KEY': 'SOURCE'}}, 'environment'),
    ({'slurm': {'time': {'hidden': 'retained-secret'}}}, 'slurm.time'),
    ({'slurm': {'time': 'retained-secret\n#SBATCH --other=1'}}, 'slurm.time'),
    ({'slurm': {1: 'retained-secret'}}, 'slurm'),
    ({'script_args': {'input': 'data/input', 'label': {'hidden': 'retained-secret'}}}, 'script_args'),
])
def test_direct_render_and_preparation_share_diagnostics_without_values(change, field, monkeypatch):
    definition = {**job(), **change}
    monkeypatch.setattr(subprocess, 'run', forbidden)
    for invoke in (lambda: write_slurm_content(StringIO(), definition, {}, context=context()),
                   lambda: prepare_bundle([definition], {'fit': []}, context())):
        with pytest.raises(InvalidRequestError) as stopped:
            invoke()
        facts = stopped.value.diagnostic.to_dict()
        assert facts['context']['job'] == 'fit' and facts['context']['machine'] == 'mock'
        assert facts['context']['field'] == field and 'retained-secret' not in json.dumps(facts)


@pytest.mark.parametrize('operation', ['preview', 'submit'])
@pytest.mark.parametrize('change', [{'working_directory': '../outside'}, {'environment': {'BAD-NAME': 'secret'}}])
def test_public_engine_retains_exact_bundle_and_does_not_stage(change, operation, monkeypatch):
    save_config({'machines': {'mock': {'results_root': '/science', 'env_command': 'true'}}, 'default_machine': 'mock'})
    selected = save_bundle({'fit': {**job(), **change}}, 'study')
    before = selected.read_bytes()
    monkeypatch.setattr(subprocess, 'run', forbidden)
    with pytest.raises(InvalidRequestError) as stopped:
        preview_bundle(selected) if operation == 'preview' else submit_jobs('study', bundle_path=selected)
    facts = stopped.value.diagnostic.context
    assert facts['bundle_path'] == str(selected) and facts['job'] == 'fit' and facts['machine'] == 'mock'
    assert selected.read_bytes() == before
    assert not list(slurm_dir().glob('*.sh')) and not list((storage_root() / 'submissions').glob('*.json'))


@pytest.mark.local_processes
@pytest.mark.parametrize('operation', ['preview', 'submit'])
def test_shell_rejection_identifies_late_job_without_leaking_script(operation, monkeypatch):
    save_config({'machines': {'mock': {'env_command': 'true'}}, 'default_machine': 'mock'})
    selected = save_bundle({'A': {'script': 'science'}, 'Z': {'script': "echo 'retained-secret"}}, 'study')
    before = selected.read_bytes()
    real_run = subprocess.run
    def syntax_only(command, **kwargs):
        assert command == ['bash', '-n']
        return real_run(command, **kwargs)
    monkeypatch.setattr(subprocess, 'run', syntax_only)
    with pytest.raises(InvalidRequestError) as stopped:
        preview_bundle(selected) if operation == 'preview' else submit_jobs('study', bundle_path=selected)
    facts = stopped.value.diagnostic.to_dict()
    assert facts['stage'] == 'validate_shell' and facts['context']['job'] == 'Z'
    assert facts['context']['machine'] == 'mock' and facts['context']['bundle_path'] == str(selected)
    assert facts['cause']['returncode'] != 0 and facts['cause']['kind'] == 'ShellSyntaxError'
    assert 'retained-secret' not in json.dumps(facts)
    assert selected.read_bytes() == before and not list(slurm_dir().glob('*.sh'))
    assert not list((storage_root() / 'submissions').glob('*.json'))


def test_invalid_render_preserves_existing_script_and_absent_destination(monkeypatch):
    monkeypatch.setattr(subprocess, 'run', forbidden)
    date = datetime(2026, 11, 14)
    good = {'name': 'fit', 'script': 'science', 'slurm': {}}
    name = create_slurm_script(good, date, {}, context=context())
    selected = slurm_dir() / name
    before = selected.read_bytes()
    with pytest.raises(InvalidRequestError):
        create_slurm_script({**good, 'environment': {'BAD-NAME': 'secret'}}, date, {}, context=context())
    assert selected.read_bytes() == before
    with pytest.raises(InvalidRequestError):
        create_slurm_script({**good, 'name': 'new', 'working_directory': '../outside'}, date, {}, context=context())
    assert list(slurm_dir().glob('*.sh')) == [selected]


def saved_execution(evidence):
    path = jobs_dir() / 'study_20261114000000.json'
    path.write_text(json.dumps({'fit': {'script': 'science', EXECUTION_METADATA_KEY: evidence}}))
    return path


@pytest.mark.parametrize('change,field', [
    ({'storage_root': 'relative'}, 'storage_root'), ({'results_root': None}, 'results_root'),
    ({'project_root': '/old/../other'}, 'project_root'), ({'software_root': []}, 'software_root'),
    ({'transport': []}, 'transport'), ({'transport': {'ssh_alias': None}, 'is_remote': True}, 'transport'),
    ({'transport': {'ssh_alias': '-bad'}, 'is_remote': True}, 'transport'),
    ({'is_remote': True}, 'transport'), ({'machine': []}, 'machine'),
])
def test_invalid_saved_paths_are_record_errors_without_discovery(change, field, monkeypatch):
    evidence = {**context().resolve_job(job()), **change}
    selected = saved_execution(evidence)
    before = selected.read_bytes()
    monkeypatch.setattr(subprocess, 'run', forbidden)
    monkeypatch.setattr('autoslurm.execution.select_machine', forbidden)
    for invoke in (lambda: recorded_execution(selected), lambda: execution_context_from_snapshot(selected),
                   lambda: resolve_results_path('result', bundle_path=selected)):
        with pytest.raises(SelectionError) as stopped:
            invoke()
        facts = stopped.value.diagnostic.to_dict()
        assert facts['code'] == 'record_invalid' and facts['stage'] == 'read_execution'
        assert facts['context']['job'] == 'fit' and facts['context']['bundle_path'] == str(selected)
        assert facts['context']['field'] == f'{EXECUTION_METADATA_KEY}.{field}'
    assert selected.read_bytes() == before


def test_legacy_roots_and_transport_are_preserved_without_current_profile(monkeypatch):
    evidence = context().resolve_job(job())
    evidence.update(project_root='/old/inputs', results_root='/old/results', is_remote=True,
                    transport={'hosturl': 'old-host', 'username': 'scientist'})
    selected = saved_execution(evidence)
    monkeypatch.setattr(subprocess, 'run', forbidden)
    producing = execution_context_from_snapshot(selected)
    assert producing.resolve_path('file', 'project') == '/old/inputs/file'
    assert producing.resolve_path('file') == '/old/results/file'
    assert producing.config == evidence['transport']


@pytest.mark.parametrize('kind,code', [('absent', 'resource_missing'), ('malformed', 'record_invalid'),
                                      ('job-missing', 'resource_missing'), ('ambiguous', 'invalid_argument')])
def test_recorded_execution_selection_has_distinct_failures(kind, code, monkeypatch):
    selected = saved_execution(context().resolve_job(job()))
    payload = json.loads(selected.read_text())
    if kind == 'absent':
        del payload['fit'][EXECUTION_METADATA_KEY]
    elif kind == 'malformed':
        payload['fit'][EXECUTION_METADATA_KEY] = None
    elif kind == 'ambiguous':
        payload['other'] = payload['fit']
    selected.write_text(json.dumps(payload))
    monkeypatch.setattr(subprocess, 'run', forbidden)
    with pytest.raises(SelectionError) as stopped:
        recorded_execution(selected, 'absent' if kind == 'job-missing' else None)
    assert stopped.value.diagnostic.code == code
    assert stopped.value.diagnostic.context['bundle_path'] == str(selected)


@pytest.mark.parametrize('invoke', [resolve_results_path, path_exists])
def test_lookup_selector_conflict_is_a_named_error(invoke, tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess, 'run', forbidden)
    with pytest.raises(InvalidRequestError) as stopped:
        invoke('file', context=context(), bundle_path=tmp_path / 'selected.json')
    assert stopped.value.diagnostic.context['field'] == 'bundle_path'


@pytest.mark.parametrize('entry', [submit.main, lambda args: root.main(['submit', *args])])
def test_submit_cli_renders_preparation_failure_once_and_debug_keeps_original(entry, monkeypatch, capsys):
    save_config({'machines': {'mock': {'results_root': '/science', 'env_command': 'true'}}, 'default_machine': 'mock'})
    selected = save_bundle({'fit': {**job(), 'working_directory': '../outside'}}, 'study')
    capsys.readouterr()
    monkeypatch.setattr(subprocess, 'run', forbidden)
    with pytest.raises(SystemExit) as stopped:
        entry(['--bundle-file', str(selected)])
    assert stopped.value.code == 1
    output = capsys.readouterr()
    assert output.out == '' and 'invalid_argument' in output.err and 'working_directory' in output.err
    with pytest.raises(InvalidRequestError):
        entry(['--bundle-file', str(selected), '--debug'])
    assert capsys.readouterr() == ('', '')


@pytest.mark.parametrize('bug', [KeyError('bug'), TypeError('bug'), ValueError('bug')])
def test_unexpected_renderer_bugs_are_not_reclassified(bug, monkeypatch):
    def fail(*args, **kwargs):
        raise bug
    monkeypatch.setattr('autoslurm.job_to_slurm.compile_script_arguments', fail)
    with pytest.raises(type(bug)) as stopped:
        prepare_bundle([job()], {'fit': []}, context())
    assert stopped.value is bug


def test_shell_launch_failure_is_left_for_process_adoption(monkeypatch):
    original = FileNotFoundError('bash unavailable')
    def fail(*args, **kwargs):
        raise original
    monkeypatch.setattr(subprocess, 'run', fail)
    with pytest.raises(FileNotFoundError) as stopped:
        validate_slurm_content('science')
    assert stopped.value is original


def test_interrupted_shell_checker_is_not_invalid_user_syntax(monkeypatch):
    monkeypatch.setattr(subprocess, 'run', lambda command, **kw: subprocess.CompletedProcess(command, -9, '', ''))
    with pytest.raises(subprocess.CalledProcessError) as stopped:
        validate_slurm_content('science')
    assert stopped.value.returncode == -9
