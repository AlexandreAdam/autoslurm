"""One declaration supplies CLI parsing, pre-save checks and the ordinary engine."""

import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
from typer.main import get_command

from autoslurm import load_bundle_from_path, preview_bundle, save_bundle, save_config, submit_jobs
from autoslurm.argument_compilation import compile_script_arguments
from autoslurm.storage import jobs_dir, storage_root
from autoslurm.typer_adapter import from_typer


EXAMPLE = Path(__file__).resolve().parents[2] / 'examples/reference_client'


@pytest.fixture
def typed_client(monkeypatch):
    monkeypatch.syspath_prepend(str(EXAMPLE))
    app = importlib.import_module('typed_science_demo').app
    return app, from_typer(app, script='science-typed', input_args=('input_file',))


@pytest.mark.parametrize('include_values', [False, True])
@pytest.mark.parametrize('label', ['g,r', 'two words', "a'b", '$(touch injected)', '*?[x]', '--other=value'])
def test_saved_scalar_values_round_trip_through_the_actual_cli(typed_client, include_values, label):
    app, contract = typed_client
    job = contract.job(name='sample', script_args={'input_file': 'data/measurements.json',
                       'output_dir': 'trial/run', 'repeat': 2, 'label': label, 'include_values': include_values})
    # Parameter parsing is safe for this explicitly prechecked callback-free CLI.
    # The production adapter never uses make_context to validate native values.
    tokens = [token for group in compile_script_arguments(job['script_args']) for token in group]
    with get_command(app).make_context('science-typed', tokens) as parsed:
        assert parsed.params == job['script_args']
    selected = save_bundle({'sample': job}, 'typed-proof')
    persisted = json.loads(selected.read_text())['sample']
    assert persisted['script_args'] == job['script_args']
    assert set(persisted) == {'name', 'script', 'script_args', 'slurm', 'input_args', '_autoslurm_snapshot_kind'}
    assert not any(callable(value) for value in persisted.values())


def test_bad_settings_do_not_write_a_bundle(typed_client):
    _, contract = typed_client
    before = list(jobs_dir().glob('*.json'))
    with pytest.raises(ValueError, match='repeat'):
        job = contract.job(name='sample', script_args={'input_file': 'data.json', 'output_dir': 'out', 'repeat': True})
        save_bundle({'sample': job}, 'bad')
    assert list(jobs_dir().glob('*.json')) == before


@pytest.mark.local_processes
def test_typed_job_uses_existing_preview_submission_and_scientific_execution(typed_client, tmp_path, monkeypatch):
    _, contract = typed_client
    commands = tmp_path / 'bin'
    commands.mkdir()
    launcher = commands / 'science-typed'
    launcher.write_text(f'#!{sys.executable}\nimport sys\nsys.path.insert(0, {str(EXAMPLE)!r})\nfrom typed_science_demo import app\napp()\n')
    launcher.chmod(0o755)
    monkeypatch.setenv('PATH', str(commands) + os.pathsep + os.environ['PATH'])
    monkeypatch.setenv('PYTHONDONTWRITEBYTECODE', '1')
    data = storage_root() / 'data with spaces'
    (data / 'inputs').mkdir(parents=True)
    shutil.copyfile(EXAMPLE / 'data/measurements.json', data / 'inputs/data.json')
    save_config({'machines': {'mock': {'env_command': 'true', 'results_root': str(data)}}, 'default_machine': 'mock'})
    label = "pilot's trial; $(touch injected); `touch injected-too` * $HOME"
    job = contract.job(name='sample', script_args={'input_file': 'inputs/data.json', 'output_dir': 'typed/run with spaces',
                       'repeat': 2, 'offset': 0.5, 'label': label, 'include_values': True},
                       slurm={'time': '00:01:00', 'mem': '64M'})
    selected = save_bundle({'sample': job}, 'typed-proof')
    original = selected.read_bytes()
    real_run = subprocess.run
    dispatched = []

    def scheduler(command, **kwargs):
        if command[0] == 'bash':
            return real_run(command, **kwargs)
        assert command[0] == 'sbatch'
        text = Path(command[-1]).read_text()
        dispatched.append(text)
        executed = real_run(['bash', command[-1]], capture_output=True, text=True)
        assert executed.returncode == 0, executed.stdout + executed.stderr
        return subprocess.CompletedProcess(command, 0, 'Submitted batch job 101', '')

    monkeypatch.setattr('subprocess.run', scheduler)
    preview = preview_bundle(selected)
    receipt = submit_jobs('typed-proof', bundle_path=selected)
    assert dispatched == [preview['jobs']['sample']['script']]
    assert receipt['jobs']['sample']['state'] == 'accepted' and receipt['jobs']['sample']['id'] == '101'
    assert selected.read_bytes() == original
    jobs, _, _ = load_bundle_from_path(receipt['bundle_path'])
    assert jobs[0]['script_args'] == job['script_args']
    result = json.loads((data / 'typed/run with spaces/summary.json').read_text())
    assert (result['count'], result['sum_squares'], result['label'], result['values']) == (8, 82, label, [1, 2, 3, 4])
    assert not (data / 'injected').exists() and not (data / 'injected-too').exists()
