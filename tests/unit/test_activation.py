"""Machine setup precedes activation of the explicitly selected environment."""

from io import StringIO
import shlex
import subprocess

import pytest

from autoslurm.config import activation_command_from_config
from autoslurm.job_to_slurm import write_slurm_content


@pytest.mark.parametrize('profile,expected', [
    ({}, ''),
    ({'env_command': ' module load jax/0.11.0 '}, 'module load jax/0.11.0'),
    ({'venv_path': '/env'}, 'source /env/bin/activate'),
    ({'venv_path': '/env', 'env_command': 'module load jax/0.11.0'},
     'module load jax/0.11.0 && source /env/bin/activate'),
])
def test_activation_preserves_single_setting_and_composes_both(profile, expected):
    assert activation_command_from_config(profile) == expected


def test_config_editor_preserves_existing_module_setup(monkeypatch):
    from autoslurm.apps.config import _prompt_machine_details
    answers = iter(['', '', 'n', '', ''])
    monkeypatch.setattr('builtins.input', lambda prompt: next(answers))
    profile = _prompt_machine_details({'venv_path': '/env', 'env_command': 'module load jax/0.11.0'})
    assert profile == {'venv_path': '/env', 'env_command': 'module load jax/0.11.0'}


@pytest.mark.local_processes
@pytest.mark.parametrize('setup_succeeds', [True, False])
def test_rendered_job_runs_setup_before_activation_and_stops_on_failure(tmp_path, setup_succeeds):
    environment = tmp_path / 'environment with spaces'
    (environment / 'bin').mkdir(parents=True)
    (environment / 'bin/activate').write_text('test "$MODULE_LOADED" = jax || return 1\nexport ACTIVATED=yes\n')
    data = tmp_path / 'results'
    data.mkdir()
    setup = 'export MODULE_LOADED=jax' if setup_succeeds else 'false'
    profile = {'venv_path': str(environment), 'env_command': setup, 'results_root': str(data)}
    job = {'name': 'science', 'script': 'printf "%s\\n" "$ACTIVATED"', 'slurm': {}}
    output = StringIO()
    write_slurm_content(output, job, profile)
    script = output.getvalue()
    assert f'{setup} && source {shlex.quote(str(environment))}/bin/activate' in script
    result = subprocess.run(['bash', '-c', script], capture_output=True, text=True)
    if setup_succeeds:
        assert result.returncode == 0 and result.stdout.strip() == 'yes'
    else:
        assert result.returncode != 0 and 'yes' not in result.stdout
