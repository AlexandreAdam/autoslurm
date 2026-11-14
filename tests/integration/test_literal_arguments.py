"""Public preview and submit share validation before staging or dispatch."""

from io import StringIO

import pytest

from autoslurm import list_submissions, preview_bundle, save_bundle, save_config, submit_jobs
from autoslurm.bundle_preparation import prepare_bundle
from autoslurm.execution import resolve_execution_context
from autoslurm.job_to_slurm import write_slurm_content
from autoslurm.storage import slurm_dir


@pytest.mark.parametrize('remote', [False, True])
def test_compilation_uses_resolved_paths_once_per_job(monkeypatch, remote):
    import autoslurm.job_to_slurm as renderer
    real_compile = renderer.compile_script_arguments
    calls = []

    def record(values):
        calls.append(dict(values))
        return real_compile(values)

    monkeypatch.setattr(renderer, 'compile_script_arguments', record)
    config = {'results_root': '/data with spaces'}
    if remote:
        config['ssh_alias'] = 'fake-cluster'
    context = resolve_execution_context('mock', config, root_resolver=lambda *args: '/fake/helper')
    job = {'name': 'sample', 'script': 'science', 'slurm': {}, 'input_args': ['input_file'],
           'script_args': {'input_file': "inputs/a'b.json", 'output_dir': 'out $HOME', 'label': 'two words'}}
    prepared = prepare_bundle([job], {'sample': []}, context)
    assert calls == [{'input_file': "/data with spaces/inputs/a'b.json",
                      'output_dir': '/data with spaces/out $HOME', 'label': 'two words'}]
    assert job['script_args']['input_file'] == "inputs/a'b.json"
    assert "--label='two words'" in prepared.jobs[0].script
    direct = StringIO()
    write_slurm_content(direct, job, context.config, context=context)
    assert direct.getvalue() == prepared.jobs[0].script


@pytest.mark.parametrize('arguments', [
    {'label': {'hidden': 'payload'}}, {'label': 'a\nb'}, {'bad;name': 1},
    {'values': [[1, 2]]}, {'same_name': 1, 'same-name': 2},
])
def test_invalid_raw_values_fail_before_any_script_or_submission_effect(arguments, monkeypatch):
    save_config({'machines': {'mock': {'env_command': 'true'}}, 'default_machine': 'mock'})
    job = {'name': 'sample', 'script': 'science', 'slurm': {}, 'script_args': arguments}
    selected = save_bundle({'sample': job}, 'invalid-arguments')
    before = selected.read_bytes()

    def no_effects(*args, **kwargs):
        pytest.fail('Invalid argument values reached an external command')

    monkeypatch.setattr('subprocess.run', no_effects)
    for operation in [lambda: preview_bundle(selected),
                      lambda: submit_jobs('invalid-arguments', bundle_path=selected)]:
        with pytest.raises(ValueError):
            operation()
    assert selected.read_bytes() == before
    assert not list(slurm_dir().iterdir())
    assert list_submissions() == []
