"""Public Python, client CLI, ordinary arrays/reduction and durable receipts."""

import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from autoslurm import inspect_bundle, load_bundle_from_path, preview_bundle, save_config, submit_jobs
from autoslurm.storage import jobs_dir, storage_root

EXAMPLE = Path(__file__).resolve().parents[2] / 'examples/reference_client'


@pytest.fixture
def client(monkeypatch):
    monkeypatch.syspath_prepend(str(EXAMPLE))
    return importlib.import_module('jobs_demo')


def test_client_plan_and_revalidate_are_local_json_routes(client, monkeypatch, capsys):
    monkeypatch.setattr('subprocess.run', lambda *args, **kwargs: pytest.fail('Planning contacted a process'))
    assert client.main(['plan', '--bundle', 'typed-array', '--output-dir', 'study with spaces']) == 0
    planned = json.loads(capsys.readouterr().out)
    selected = Path(planned['bundle_path'])
    before = selected.read_bytes()
    assert client.main(['validate', '--bundle-path', str(selected)]) == 0
    validated = json.loads(capsys.readouterr().out)
    assert set(validated['jobs']) == {'shards', 'reduce'}
    assert validated['jobs']['reduce']['dependencies'] == ['shards']
    assert selected.read_bytes() == before
    before_files = set(jobs_dir().iterdir())
    with pytest.raises(SystemExit) as error:
        client.main(['plan', '--input-file', ''])
    assert error.value.code == 1
    assert set(jobs_dir().iterdir()) == before_files
    assert 'input_file' in capsys.readouterr().err


def test_saved_command_drift_stops_client_before_preview(client, monkeypatch, capsys):
    client.main(['plan'])
    selected = Path(json.loads(capsys.readouterr().out)['bundle_path'])
    data = json.loads(selected.read_text())
    data['reduce']['script_args']['obsolete_option'] = 3
    selected.write_text(json.dumps(data))
    before = selected.read_bytes()
    monkeypatch.setattr(client, 'preview_bundle', lambda *args, **kwargs: pytest.fail('Invalid job reached readiness'))
    with pytest.raises(SystemExit) as error:
        client.main(['preview', '--bundle-path', str(selected)])
    assert error.value.code == 1
    assert 'Unknown command arguments' in capsys.readouterr().err
    assert selected.read_bytes() == before


@pytest.mark.local_processes
def test_public_typed_array_reducer_preview_submission_and_inspection(client, tmp_path, monkeypatch, capsys):
    commands = tmp_path / 'bin'
    commands.mkdir()
    for name, app in [('science-typed-shard', 'shard_app'), ('science-typed-reduce', 'reduce_app')]:
        launcher = commands / name
        launcher.write_text(f'#!{sys.executable}\nimport sys\nsys.path.insert(0, {str(EXAMPLE)!r})\nfrom typed_science_demo import {app}\n{app}()\n')
        launcher.chmod(0o755)
    monkeypatch.setenv('PATH', str(commands) + os.pathsep + os.environ['PATH'])
    monkeypatch.setenv('PYTHONDONTWRITEBYTECODE', '1')
    data = storage_root() / "data with spaces and 'quotes'"
    (data / 'inputs').mkdir(parents=True)
    shutil.copyfile(EXAMPLE / 'data/measurements.json', data / 'inputs/data.json')
    save_config({'machines': {'mock': {'env_command': 'true', 'results_root': str(data)}}, 'default_machine': 'mock'})
    client.main(['plan', '--input-file', 'inputs/data.json', '--output-dir', 'study with spaces'])
    selected = Path(json.loads(capsys.readouterr().out)['bundle_path'])
    original = selected.read_bytes()
    checked = client.validate_saved_bundle(selected)
    assert checked['shards']['slurm']['array'] == '0-3%2'
    real_run = subprocess.run
    dispatched = {}

    def scheduler(command, **kwargs):
        if command[0] == 'bash':
            return real_run(command, **kwargs)
        assert command[0] == 'sbatch'
        text = Path(command[-1]).read_text()
        name = 'reduce' if '#SBATCH --job-name=reduce\n' in text else 'shards'
        if name == 'reduce':
            assert command[command.index('--dependency') + 1] == 'afterok:301'
            assert '#SBATCH --kill-on-invalid-dep=yes' in text
        for index in range(4) if name == 'shards' else [None]:
            environment = dict(os.environ)
            if index is not None:
                environment['SLURM_ARRAY_TASK_ID'] = str(index)
            executed = real_run(['bash', command[-1]], env=environment, capture_output=True, text=True)
            assert executed.returncode == 0, executed.stdout + executed.stderr
        dispatched[name] = text
        return subprocess.CompletedProcess(command, 0, f'Submitted batch job {301 if name == "shards" else 302}', '')

    monkeypatch.setattr('subprocess.run', scheduler)
    client.main(['preview', '--bundle-path', str(selected)])
    preview = json.loads(capsys.readouterr().out)
    receipt = submit_jobs('typed-array', bundle_path=selected)
    assert receipt['state'] == 'submitted'
    assert {name: result['id'] for name, result in receipt['jobs'].items()} == {'shards': '301', 'reduce': '302'}
    assert dispatched == {name: details['script'] for name, details in preview['jobs'].items()}
    assert selected.read_bytes() == original
    snapshot, _, _ = load_bundle_from_path(receipt['bundle_path'])
    assert {job['name']: job['script_args'] for job in snapshot} == {name: job['script_args'] for name, job in checked.items()}
    result = json.loads((data / 'study with spaces/summary/summary.json').read_text())
    assert (result['count'], result['sum_squares']) == (4, 30)
    assert len(list((data / 'study with spaces/parts').glob('part-*.json'))) == 4
    monkeypatch.setattr('subprocess.run', lambda *args, **kwargs: pytest.fail('Cached inspection contacted scheduler'))
    view = inspect_bundle(receipt_path=receipt['receipt_path'], refresh=False)
    assert {job['name']: job['id'] for job in view['jobs']} == {'shards': '301', 'reduce': '302'}
