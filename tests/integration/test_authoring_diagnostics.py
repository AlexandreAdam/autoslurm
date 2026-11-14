"""Authoring failures retain identities and cannot become external effects."""

import builtins
import copy
from graphlib import CycleError
import json
from typing import Annotated

import pytest
import typer

from autoslurm import (CommandContract, CommandOption, InvalidRequestError,
                      dependency_graph, from_typer, load_bundle_from_path,
                      preview_bundle, save_bundle, schedule_job, submit_jobs)
from autoslurm.apps import root, schedule
from autoslurm.apps.error_output import render_diagnostic
from autoslurm.argument_compilation import compile_script_arguments
from autoslurm.errors import DiagnosticCause, DiagnosticError, invalid_argument
from autoslurm.software_manifest import bundle_software_manifest
from autoslurm.storage import jobs_dir, slurm_dir, storage_root
from autoslurm.config import save_config


def contract():
    return CommandContract('science fit', (
        CommandOption('count', 'int', True, minimum=1),
        CommandOption('label', 'str', False, 'trial'),
        CommandOption('enabled', 'bool', False, False),
    ))


@pytest.mark.parametrize('settings,field,option', [
    ([], 'script_args', None), ({}, 'script_args', 'count'),
    ({'count': '1'}, 'script_args', 'count'),
    ({'count': 0}, 'script_args', 'count'),
    ({'count': 1, 'label': 'a\nb'}, 'script_args', 'label'),
    ({'count': 1, 'label': ['a']}, 'script_args', 'label'),
    ({'count': 1, 'unknown': 'retained-secret'}, 'script_args', None),
])
def test_job_validation_reports_named_context_without_values_or_effects(settings, field, option):
    before = copy.deepcopy(settings)
    with pytest.raises(InvalidRequestError) as stopped:
        contract().job(name='fit', script_args=settings)
    error = stopped.value
    assert isinstance(error, (ValueError, DiagnosticError))
    facts = error.diagnostic.to_dict()
    assert facts['code'] == 'invalid_argument' and facts['operation'] == 'authoring'
    assert facts['context']['job'] == 'fit' and facts['context']['command'] == 'science fit'
    assert facts['context']['field'] == field
    if option:
        assert facts['context']['option'] == option
    assert facts['effects'] == {} and facts['next_action']
    assert 'retained-secret' not in json.dumps(facts)
    assert settings == before and not list(jobs_dir().glob('*.json'))


def test_saved_revalidation_does_not_inject_new_defaults_or_change_evidence():
    job = contract().job(name='fit', script_args={'count': 1})
    path = save_bundle({'fit': job}, 'study')
    before = path.read_bytes()
    del job['script_args']['enabled']
    with pytest.raises(InvalidRequestError) as stopped:
        contract().validate_job(job)
    assert stopped.value.diagnostic.context['job'] == 'fit'
    assert stopped.value.diagnostic.context['field'] == 'script_args'
    assert 'enabled' in str(stopped.value) and 'enabled' not in job['script_args']
    assert path.read_bytes() == before


def test_plain_words_and_literal_values_keep_readable_saved_settings():
    job = contract().job(name='fit', script_args={'count': 2, 'label': 'a b; $(ignored)'})
    path = save_bundle({'fit': job}, 'study')
    saved = json.loads(path.read_text())['fit']['script_args']
    assert saved == {'count': 2, 'label': 'a b; $(ignored)', 'enabled': False}
    assert compile_script_arguments(saved) == (('--count=2',), ('--label=a b; $(ignored)',))


@pytest.mark.parametrize('values,option', [
    ({'label': {'encoded': 'retained-secret'}}, 'label'),
    ({'label': ['a', 'b\nc']}, 'label[1]'),
    ({'value': float('inf')}, 'value'),
    ({'__positionals__': ['a', {}]}, '__positionals__[1]'),
])
def test_literal_compiler_reports_the_option_without_serializing_bad_values(values, option):
    with pytest.raises(InvalidRequestError) as stopped:
        compile_script_arguments(values)
    assert stopped.value.diagnostic.stage == 'compile_arguments'
    assert stopped.value.diagnostic.context['option'] == option
    assert 'retained-secret' not in json.dumps(stopped.value.diagnostic.to_dict())


@pytest.mark.parametrize('jobs,field', [
    ([], 'bundle'), ({'fit': []}, 'job'), ({'fit': {'name': 'other'}}, 'name'),
    ({'fit': {'dependencies': False}}, 'dependencies'),
    ({'fit': {'dependencies': ['absent']}}, 'dependencies'),
    ({'fit': {'dependencies': [{}]}}, 'dependencies'),
])
def test_graph_input_failures_are_explicit(jobs, field):
    with pytest.raises(InvalidRequestError) as stopped:
        dependency_graph(jobs)
    assert stopped.value.diagnostic.context['field'] == field
    assert stopped.value.diagnostic.stage == 'validate_graph'


def test_cycle_retains_original_cause_and_exact_bundle_path_without_commands(monkeypatch):
    jobs = {'A': {'script': 'science', 'dependencies': ['B']},
            'B': {'script': 'science', 'dependencies': ['A']}}
    path = jobs_dir() / 'study_20261114000000.json'
    path.write_text(json.dumps(jobs))
    before = path.read_bytes()
    monkeypatch.setattr('subprocess.run', lambda *a, **kw: pytest.fail('No commands for an invalid graph'))
    with pytest.raises(InvalidRequestError) as stopped:
        load_bundle_from_path(path)
    assert isinstance(stopped.value.__cause__, CycleError)
    facts = stopped.value.diagnostic.to_dict()
    assert facts['context']['bundle_path'] == str(path)
    assert facts['context']['field'] == 'dependencies'
    assert facts['cause']['kind'] == 'CycleError' and 'A' in facts['summary'] and 'B' in facts['summary']
    assert path.read_bytes() == before


@pytest.mark.parametrize('job,field', [(None, 'job'), ({}, 'script'), ({'script': ''}, 'script'),
                                      ({'script': 3}, 'script')])
def test_schedule_invalid_input_does_not_create_any_record(job, field, monkeypatch):
    monkeypatch.setattr('autoslurm.save_load_jobs.atomic_json', lambda *a, **kw: pytest.fail('No publication'))
    with pytest.raises(InvalidRequestError) as stopped:
        schedule_job(job, 'study')
    assert stopped.value.diagnostic.context['field'] == field
    assert stopped.value.diagnostic.effects == {'bundle_write': 'not_started'}
    assert not list(jobs_dir().glob('*.json'))


@pytest.mark.parametrize('bad', [[], {'fit': []}, {'fit': {}}, {'fit': {'script': ''}},
                               {1: {'script': 'science'}}, {'': {'script': 'science'}}])
def test_bad_append_preserves_original_record(bad, monkeypatch):
    selected = save_bundle({'fit': {'script': 'science'}}, 'study')
    before = selected.read_bytes()
    monkeypatch.setattr('autoslurm.save_load_jobs.atomic_json', lambda *a, **kw: pytest.fail('No publication'))
    with pytest.raises(InvalidRequestError) as stopped:
        save_bundle(bad, 'study', append=True)
    assert stopped.value.diagnostic.effects == {'bundle_write': 'not_started'}
    assert selected.read_bytes() == before


@pytest.mark.parametrize('operation', ['preview', 'submit'])
@pytest.mark.parametrize('bad', ['arguments', 'shape', 'script', 'graph'])
def test_public_engine_rejects_saved_invalid_authoring_before_commands(operation, bad, monkeypatch):
    save_config({'machines': {'mock': {'env_command': 'true'}}, 'default_machine': 'mock'})
    job = {'script': 'science', 'script_args': {'label': 'a\nb'}, 'slurm': {}}
    jobs = {'fit': job}
    if bad == 'shape': jobs['fit'] = []
    if bad == 'script': job['script'] = ''
    if bad == 'graph': job['dependencies'] = ['missing']
    path = jobs_dir() / 'study_20261114000000.json'
    path.write_text(json.dumps(jobs))
    before = path.read_bytes()
    monkeypatch.setattr('subprocess.run', lambda *a, **kw: pytest.fail('Validation must precede external commands'))
    with pytest.raises(InvalidRequestError) as stopped:
        preview_bundle(path) if operation == 'preview' else submit_jobs('study', bundle_path=path)
    context = stopped.value.diagnostic.context
    assert context['bundle_path'] == str(path) and context['machine'] == 'mock'
    assert context.get('job') == 'fit'
    assert path.read_bytes() == before and not list(slurm_dir().glob('*.sh'))
    assert not list((storage_root() / 'submissions').glob('*.json'))


def test_bad_manifest_keeps_job_field_and_safe_parser_cause():
    jobs = [{'name': 'fit', 'software': {'projects': [{'name': 'science', 'repository': 'https://[retained-secret'}]}}]
    with pytest.raises(InvalidRequestError) as stopped:
        bundle_software_manifest(jobs)
    facts = stopped.value.diagnostic.to_dict()
    assert facts['context']['field'] == 'repository' and facts['context']['job'] == 'fit'
    assert facts['context']['project'] == 'science'
    assert facts['cause']['kind'] == 'ValueError' and isinstance(stopped.value.__cause__, ValueError)
    assert 'retained-secret' not in json.dumps(facts)


def test_literal_command_syntax_error_keeps_native_cause():
    with pytest.raises(InvalidRequestError) as stopped:
        CommandContract("science 'unterminated", ())
    assert stopped.value.diagnostic.context['field'] == 'script'
    assert stopped.value.diagnostic.cause.kind == 'ValueError'
    assert isinstance(stopped.value.__cause__, ValueError)


def test_typer_option_rejection_never_executes_scientific_callback():
    app = typer.Typer(add_completion=False)
    @app.command()
    def run(count: Annotated[int, typer.Option(callback=lambda value: pytest.fail('No option callback'))] = 1):
        pytest.fail('No science callback')
    with pytest.raises(InvalidRequestError) as stopped:
        from_typer(app, script='science')
    assert stopped.value.diagnostic.context['option'] == 'count'
    assert stopped.value.diagnostic.stage == 'derive_command'


def test_optional_typer_absence_retains_import_cause(monkeypatch):
    real_import = builtins.__import__
    original = ImportError('Typer unavailable')
    def missing(name, *args, **kw):
        if name == 'typer': raise original
        return real_import(name, *args, **kw)
    monkeypatch.setattr(builtins, '__import__', missing)
    with pytest.raises(InvalidRequestError) as stopped:
        from_typer(None, script='science')
    assert stopped.value.__cause__ is original
    assert stopped.value.diagnostic.cause.kind == 'ImportError'


def test_unsupported_typer_reports_observed_and_supported_versions(monkeypatch):
    monkeypatch.setattr(typer, '__version__', '0.28.0')
    with pytest.raises(InvalidRequestError) as stopped:
        from_typer(None, script='science')
    facts = stopped.value.diagnostic.to_dict()
    assert facts['context']['field'] == 'typer'
    assert '0.28.0' in facts['summary'] and '0.27' in facts['summary']


@pytest.mark.parametrize('entry', [schedule.main, lambda args: root.main(['schedule', *args])])
def test_schedule_cli_expected_error_uses_shared_text_and_debug_keeps_original(entry, monkeypatch, capsys):
    monkeypatch.setattr(schedule, 'parse_script_args', lambda *args: {})
    error = InvalidRequestError('Invalid named setting.', field='script_args', context={'option': 'count'})
    def reject(*a, **kw): raise error
    monkeypatch.setattr(schedule, 'schedule_job', reject)
    with pytest.raises(SystemExit) as stopped:
        entry(['science', '--time', '1:00'])
    assert stopped.value.code == 1
    assert capsys.readouterr() == ('', render_diagnostic(error.diagnostic) + '\n')
    with pytest.raises(InvalidRequestError) as debug:
        entry(['science', '--time', '1:00', '--autoslurm-debug'])
    assert debug.value is error and capsys.readouterr() == ('', '')


@pytest.mark.parametrize('bug', [ValueError('bug'), TypeError('bug'), KeyError('bug')])
def test_programming_bugs_are_not_reclassified_or_hidden(bug, monkeypatch):
    def fail(*a, **kw): raise bug
    declaration = contract()
    monkeypatch.setattr(CommandOption, 'validate', fail)
    with pytest.raises(type(bug)) as stopped:
        declaration.job(name='fit', script_args={'count': 1})
    assert stopped.value is bug
    monkeypatch.setattr(schedule, 'parse_script_args', lambda *args: {})
    monkeypatch.setattr(schedule, 'schedule_job', fail)
    with pytest.raises(type(bug)) as stopped:
        schedule.main(['science', '--time', '1:00'])
    assert stopped.value is bug


def test_invalid_argument_cause_effects_are_explicit_and_detached():
    cause = DiagnosticCause.from_exception(ValueError('known validation'))
    effects = {'bundle_write': 'not_started'}
    diagnostic = invalid_argument(operation='authoring', stage='save_bundle', field='script',
                                  explanation='Invalid command.', cause=cause, effects=effects)
    effects['bundle_write'] = 'unknown'
    assert diagnostic.cause is cause and diagnostic.effects['bundle_write'] == 'not_started'


def test_long_identity_enrichment_keeps_the_original_expected_failure():
    name = 'x' * 600
    with pytest.raises(InvalidRequestError, match='depend on itself') as stopped:
        contract().job(name=name, script_args={'count': 1}, dependencies=[name])
    diagnostic = stopped.value.diagnostic
    assert len(diagnostic.context['job'].encode()) == 512
    assert diagnostic.with_context(job=name).context == diagnostic.context
    with pytest.raises(ValueError, match='conflicts'):
        diagnostic.with_context(job='different')


@pytest.mark.parametrize('jobs', [None, 1, 'jobs', {'fit': {}}])
def test_manifest_collection_shape_is_an_expected_request_failure(jobs):
    with pytest.raises(InvalidRequestError) as stopped:
        bundle_software_manifest(jobs)
    assert stopped.value.diagnostic.context['field'] == 'jobs'
