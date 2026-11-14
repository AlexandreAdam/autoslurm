import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from autoslurm import storage, ConfigurationError
from autoslurm.utils import load_config


def test_selector_precedence_and_reset(tmp_path, monkeypatch):
    environment_root = tmp_path / "environment"
    monkeypatch.setenv("AUTOSLURM_STORAGE_ROOT", str(environment_root))
    storage.set_storage_root(None)
    assert storage.storage_root() == environment_root
    storage.set_storage_root(tmp_path / "process")
    assert storage.storage_root() == tmp_path / "process"
    storage.set_storage_root(None)
    assert storage.storage_root() == environment_root
    monkeypatch.delenv("AUTOSLURM_STORAGE_ROOT")
    assert storage.storage_root() == Path(storage.__file__).resolve().parents[2]


@pytest.mark.parametrize("value", ["", "   ", "relative/state"])
def test_invalid_selector_never_falls_back(value, monkeypatch):
    storage.set_storage_root(None)
    monkeypatch.setenv("AUTOSLURM_STORAGE_ROOT", value)
    with pytest.raises(ValueError, match="absolute path"):
        storage.config_file_path()


def test_explicit_root_does_not_load_legacy_configuration(tmp_path, monkeypatch):
    storage.set_storage_root(None)
    monkeypatch.setenv("AUTOSLURM_STORAGE_ROOT", str(tmp_path))
    (tmp_path / "src").mkdir()
    (tmp_path / "src/config.json").write_text('{"local": {}}')
    with pytest.raises(ConfigurationError, match="Configuration file not found"):
        load_config()


@pytest.mark.local_processes
def test_fresh_processes_share_selected_state_outside_checkout(tmp_path):
    selected = tmp_path / "development state"
    env = dict(os.environ, AUTOSLURM_STORAGE_ROOT=str(selected), PYTHONDONTWRITEBYTECODE="1")
    create = '''
from datetime import datetime
from autoslurm.utils import save_config
from autoslurm import save_bundle
from autoslurm.job_to_slurm import create_slurm_script
from autoslurm.storage import storage_root, out_dir
machine = {"path": "/stable-state", "slurm_account": "mock"}
save_config({"machines": {"local": machine}, "default_machine": "local"})
job = {"name": "sample", "script": "echo scientific-result", "slurm": {}, "script_args": {"output_dir": "study"}}
save_bundle({"sample": job}, "study")
create_slurm_script(job, datetime(2026, 1, 1), machine)
(out_dir() / "sample-1.out").write_text("complete")
result = storage_root() / "results/study/result.txt"
result.parent.mkdir(parents=True)
result.write_text("scientific-result")
'''
    subprocess.run([sys.executable, "-B", "-c", create], env=env, cwd=tmp_path, check=True, capture_output=True, text=True)
    inspect = '''
import json
from autoslurm.storage import storage_root, jobs_dir, slurm_dir, out_dir
from autoslurm.utils import load_config
print(json.dumps({"root": str(storage_root()), "config": load_config()["default_machine"], "jobs": len(list(jobs_dir().glob("*.json"))), "script": next(slurm_dir().glob("*.sh")).read_text(), "log": (out_dir()/"sample-1.out").read_text(), "result": (storage_root()/"results/study/result.txt").read_text()}))
'''
    result = subprocess.run([sys.executable, "-B", "-c", inspect], env=env, cwd=tmp_path, check=True, capture_output=True, text=True)
    report = json.loads(result.stdout)
    assert report["root"] == str(selected)
    assert report["config"] == "local"
    assert report["jobs"] == 1
    assert str(selected / "out/%x-%j.out") in report["script"]
    assert str(selected / "results/study") in report["script"]
    assert "/stable-state" not in report["script"]
    assert report["log"] == "complete"
    assert report["result"] == "scientific-result"


@pytest.mark.local_processes
def test_generated_job_keeps_selected_path_with_spaces_as_one_argument(tmp_path, monkeypatch):
    from datetime import datetime
    from autoslurm.job_to_slurm import create_slurm_script

    selected = tmp_path / "development state"
    storage.set_storage_root(None)
    monkeypatch.setenv("AUTOSLURM_STORAGE_ROOT", str(selected))
    name = create_slurm_script(
        {"name": "sample", "script": "printf '%s\\n'", "slurm": {}, "script_args": {"output_dir": "study"}},
        datetime(2026, 1, 1), {"path": "/stable-state"},
    )
    result = subprocess.run(["bash", str(storage.slurm_dir() / name)], capture_output=True, text=True, check=True)
    assert result.stdout.splitlines() == [f"--output-dir={selected}/results/study"]
