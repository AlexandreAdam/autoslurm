"""The proof derives one typed leaf contract without parsing or executing it."""

import builtins
import json
from typing import Annotated

import pytest
import typer

from autoslurm import CommandContract, CommandOption, from_typer


@pytest.fixture
def command():
    app = typer.Typer(add_completion=False)

    @app.command()
    def run(input_file: Annotated[str, typer.Option()], output_dir: Annotated[str, typer.Option()],
            repeat: Annotated[int, typer.Option(min=1, max=10)] = 1,
            offset: float = 0.0, label: str = 'trial', enabled: bool = False):
        pytest.fail('Discovery or validation executed the scientific callback')

    return app, from_typer(app, script='science-typed', input_args=('input_file',))


def test_contract_has_plain_metadata_and_materializes_supported_defaults(command):
    _, contract = command
    values = contract.validate({'input_file': 'data/input.json', 'output_dir': 'study/run'})
    assert values == {'input_file': 'data/input.json', 'output_dir': 'study/run', 'repeat': 1,
                      'offset': 0.0, 'label': 'trial', 'enabled': False}
    description = json.loads(json.dumps(contract.describe()))
    assert description['options'][0]['required'] is True
    assert description['options'][2]['minimum'] == 1
    assert description['options'][2]['maximum'] == 10
    assert 'callback' not in json.dumps(description)
    values['repeat'] = 9
    assert contract.validate({'input_file': 'x', 'output_dir': 'y'})['repeat'] == 1


@pytest.mark.parametrize('values,match', [
    ({'unknown': 2}, 'Unknown'), ({'repeat': True}, 'repeat'), ({'repeat': '2'}, 'repeat'),
    ({'repeat': 0}, 'at least'), ({'repeat': 11}, 'at most'),
    ({'enabled': 1}, 'enabled'), ({'enabled': 'false'}, 'enabled'),
    ({'offset': True}, 'offset'), ({'offset': float('nan')}, 'finite'),
    ({'offset': float('inf')}, 'finite'), ({'label': ['g', 'r']}, 'label'),
    ({'label': 'a\nb'}, 'control'), ({'label': 'a\x00b'}, 'control'),
    ({'label': ''}, 'nonempty'), ({'input_file': None}, 'input_file'),
])
def test_native_values_fail_locally_and_specifically(command, values, match):
    _, contract = command
    with pytest.raises(ValueError, match=match):
        contract.validate({'input_file': 'data.json', 'output_dir': 'study', **values})


def test_required_options_paths_csv_and_numeric_normalization(command):
    _, contract = command
    with pytest.raises(ValueError, match='input_file.*required'):
        contract.validate({})
    values = contract.validate({'input_file': 'inputs/data with spaces.json', 'output_dir': 'outputs/with spaces',
                                'label': 'g,r', 'offset': 2})
    assert type(values['offset']) is float
    assert values['label'] == 'g,r'


@pytest.mark.parametrize('option', [
    {'callback': lambda value: pytest.fail('Option callback ran')},
    {'default_factory': lambda: pytest.fail('Default factory ran')},
    {'parser': lambda value: pytest.fail('Custom parser ran')},
    {'prompt': True}, {'envvar': 'DYNAMIC_COUNT'}, {'clamp': True}, {'count': True},
])
def test_dynamic_or_unsupported_option_behaviors_are_rejected_without_running(option):
    app = typer.Typer(add_completion=False)
    information = typer.Option(**option)

    @app.command()
    def run(count: Annotated[int, information] = 1):
        pytest.fail('Scientific callback ran')

    with pytest.raises(ValueError, match='unsupported Typer option behavior'):
        from_typer(app, script='science')


@pytest.mark.parametrize('annotation,default', [
    (list[str], []), (tuple[int, int], (1, 2)), (bool, True), (str, None), ('int', 1),
    (int, lambda: pytest.fail('Callable default ran')),
])
def test_unsupported_annotations_and_defaults_never_execute(annotation, default):
    app = typer.Typer(add_completion=False)

    def run(value=default):
        pytest.fail('Scientific callback ran')

    run.__annotations__ = {'value': annotation}
    app.command()(run)
    with pytest.raises(ValueError):
        from_typer(app, script='science')


def test_app_callbacks_and_completion_are_outside_the_proof():
    app = typer.Typer(add_completion=False)

    @app.callback()
    def setup():
        pytest.fail('App callback ran')

    @app.command()
    def run(count: int = 1):
        pytest.fail('Science ran')

    with pytest.raises(ValueError, match='leaf command'):
        from_typer(app, script='science')
    app = typer.Typer()
    app.command()(run)
    with pytest.raises(ValueError, match='add_completion=False'):
        from_typer(app, script='science')


def test_adapter_version_and_flag_capability_gates(monkeypatch):
    app = typer.Typer(add_completion=False)

    @app.command()
    def run(count: int = typer.Option(1, '--other')):
        pytest.fail('Science ran')

    with pytest.raises(ValueError, match='custom flag'):
        from_typer(app, script='science')
    monkeypatch.setattr(typer, '__version__', '0.28.0')
    with pytest.raises(ValueError, match='0.27 only'):
        from_typer(app, script='science')


def test_parser_flag_capability_mismatch_is_rejected(command, monkeypatch):
    app, _ = command
    from typer.main import get_command
    compiled = get_command(app)
    compiled.params[-1].is_flag = False
    monkeypatch.setattr('typer.main.get_command', lambda app: compiled)
    with pytest.raises(ValueError, match='enabled.*parser semantics'):
        from_typer(app, script='science')


def test_optional_typer_absence_is_an_explicit_error(monkeypatch):
    original = builtins.__import__

    def without_typer(name, *args, **kwargs):
        if name == 'typer' or name.startswith('typer.'):
            raise ImportError('Typer is absent')
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', without_typer)
    with pytest.raises(ValueError, match='optional Typer'):
        from_typer(None, script='science')


def test_saved_job_validation_is_pure_detached_and_keeps_explicit_values(command, monkeypatch):
    from pathlib import Path
    _, contract = command
    job = contract.job(name='sample', script_args={'input_file': 'data.json', 'output_dir': 'study'},
                       dependencies=('parent',), slurm={'array': '0-3'})
    job['environment'] = {'MODE': 'original'}
    job['_autoslurm_execution'] = {'logical_paths': {'input_file': 'data.json'}}

    def no_effects(*args, **kwargs):
        pytest.fail('Saved-job validation performed I/O or executed a command')

    monkeypatch.setattr('subprocess.run', no_effects)
    monkeypatch.setattr(Path, 'open', no_effects)
    checked = contract.validate_job(job)
    assert checked == job and checked is not job
    checked['environment']['MODE'] = 'changed'
    checked['_autoslurm_execution']['logical_paths']['input_file'] = 'other'
    checked['dependencies'].append('other-parent')
    assert job['environment']['MODE'] == 'original'
    assert job['_autoslurm_execution']['logical_paths']['input_file'] == 'data.json'
    assert job['dependencies'] == ['parent']


@pytest.mark.parametrize('field,value,match', [
    ('script', 'different-command', 'command'), ('input_args', [], 'input_args'),
    ('path_args', ['input_file'], 'path_args'), ('input_args', 'input_file', 'names'),
    ('slurm', None, 'mapping'), ('dependencies', ['sample'], 'itself'),
    ('name', 'bad name', 'simple'), ('script_args', {}, 'missing explicit'),
])
def test_saved_job_mismatches_are_explicit(command, field, value, match):
    _, contract = command
    job = contract.job(name='sample', script_args={'input_file': 'data.json', 'output_dir': 'study'})
    job[field] = value
    with pytest.raises(ValueError, match=match):
        contract.validate_job(job)


def test_changed_defaults_never_silently_replace_saved_settings():
    original = CommandContract('science', (CommandOption('count', 'int', False, 1),))
    job = original.job(name='sample', script_args={})
    current = CommandContract('science', (CommandOption('count', 'int', False, 9),))
    assert current.validate_job(job)['script_args']['count'] == 1
    added = CommandContract('science', (CommandOption('count', 'int', False, 9), CommandOption('label', 'str', False, 'new')))
    with pytest.raises(ValueError, match='missing explicit.*label'):
        added.validate_job(job)
    removed = CommandContract('science', ())
    with pytest.raises(ValueError, match='Unknown.*count'):
        removed.validate_job(job)
    changed = CommandContract('science', (CommandOption('count', 'str', False, 'one'),))
    with pytest.raises(ValueError, match='count.*str'):
        changed.validate_job(job)
    job['script_args'].pop('count')
    with pytest.raises(ValueError, match='missing explicit.*count'):
        current.validate_job(job)
    assert current.job(name='new-definition', script_args={})['script_args'] == {'count': 9}


def test_public_contract_owns_immutable_option_and_path_declarations():
    options = [CommandOption('input_file', 'str', True)]
    roles = ['input_file']
    contract = CommandContract('science', options, input_args=roles)
    options.clear()
    roles.clear()
    assert len(contract.options) == 1 and contract.input_args == ('input_file',)
    with pytest.raises(ValueError, match='both'):
        CommandContract('science', contract.options, input_args=('input_file',), path_args=('input_file',))
    with pytest.raises(ValueError, match='strings'):
        CommandContract('science', (CommandOption('output_dir', 'int', False, 1),))


@pytest.mark.parametrize('parents', ['parent', ['sample'], ['parent', 'parent'], ['bad/name']])
def test_public_builder_rejects_invalid_dependencies(command, parents):
    _, contract = command
    with pytest.raises(ValueError):
        contract.job(name='sample', script_args={'input_file': 'x', 'output_dir': 'y'}, dependencies=parents)
