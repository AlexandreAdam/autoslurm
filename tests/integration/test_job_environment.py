import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
from datetime import datetime

import pytest

from autoslurm.job_to_slurm import create_slurm_script
from autoslurm.storage import slurm_dir


@pytest.mark.local_processes
@pytest.mark.parametrize("runtime_present", [True, False])
def test_exports_are_literal_or_single_runtime_variables_after_activation(tmp_path, runtime_present):
    application = tmp_path / "inspect_environment.py"
    application.write_text('import json, os; print(json.dumps({key: os.environ[key] for key in ["OMP_NUM_THREADS", "LITERAL"]}))')
    literal = '$(touch should-not-exist); ${HOME} " spaces'
    name = create_slurm_script({
        "name": "exports", "script": shlex.join([sys.executable, str(application)]), "slurm": {},
        "environment": {"LITERAL": literal},
        "runtime_environment": {"OMP_NUM_THREADS": "SLURM_CPUS_PER_TASK"},
    }, datetime(2026, 1, 1), {"project_root": str(tmp_path), "env_command": "export OMP_NUM_THREADS=activation-default"})
    environment = dict(os.environ)
    environment.pop("SLURM_CPUS_PER_TASK", None)
    if runtime_present:
        environment["SLURM_CPUS_PER_TASK"] = "4"
    result = subprocess.run(["bash", str(slurm_dir() / name)], env=environment, capture_output=True, text=True)
    assert not (tmp_path / "should-not-exist").exists()
    if runtime_present:
        assert result.returncode == 0
        assert json.loads(result.stdout) == {"OMP_NUM_THREADS": "4", "LITERAL": literal}
    else:
        assert result.returncode != 0
        assert not result.stdout
        assert "Required runtime variable SLURM_CPUS_PER_TASK" in result.stderr


@pytest.mark.local_processes
def test_invalid_late_script_stops_before_any_scheduler_effect(tmp_path, monkeypatch):
    from autoslurm import save_bundle, submit_jobs, list_submissions
    from autoslurm.utils import save_config
    save_config({"machines": {"mock": {"env_command": "true", "slurm_account": "mock"}}, "default_machine": "mock"})
    selected = save_bundle({"A": {"script": "echo valid", "slurm": {}}, "Z": {"script": "echo 'unterminated", "slurm": {}}}, "syntax-check")
    real_run = subprocess.run
    def syntax_only(command, **kwargs):
        assert command == ["bash", "-n"], "Invalid late script reached the scheduler"
        return real_run(command, **kwargs)
    monkeypatch.setattr("subprocess.run", syntax_only)
    with pytest.raises(ValueError, match="Invalid generated shell script"):
        submit_jobs("syntax-check", bundle_path=selected)
    assert not list_submissions()
    assert not list(slurm_dir().glob("*.sh"))
