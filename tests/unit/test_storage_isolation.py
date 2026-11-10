import json
from pathlib import Path
import shlex
from subprocess import CompletedProcess

import pytest

from autoslurm import save_bundle, submit_jobs, storage
from autoslurm.apps import bulk_submit_driver
from autoslurm.remote_fs import resolve_results_path
from autoslurm.sync import sync_machine
from autoslurm.utils import remote_storage_root_from_config, save_config


def machine():
    return {
        "hostname": "mock-cluster",
        "venv_path": "/remote/development env",
        "storage_root": "/remote/development state",
        "path": "/remote/stable",
        "slurm_account": "mock",
    }


def test_selected_root_agrees_across_submit_sync_and_results(monkeypatch, isolate_storage):
    cfg = machine()
    save_config({"machines": {"mock": cfg}, "default_machine": "mock"})
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        text = " ".join(command)
        assert "/remote/stable" not in text
        if command[0] == "ssh" and command[-1].startswith("bash -lc "):
            shell = shlex.split(command[-1])[-1]
            assert "AUTOSLURM_STORAGE_ROOT=" in shell
            assert "STORAGE_ROOT_ENVIRONMENT_VARIABLE" in shell
            return CompletedProcess(command, 0, cfg["storage_root"] + "\n", "")
        if command[0] == "ssh" and "autoslurm.apps.bulk_submit_driver" in command[-1]:
            helper = shlex.split(command[-1])
            assert helper[:3] == ["env", "AUTOSLURM_STORAGE_ROOT=" + cfg["storage_root"], cfg["venv_path"] + "/bin/python"]
            payload = json.loads(kwargs["input"])
            assert payload["slurm_dir"] == cfg["storage_root"] + "/slurm"
            return CompletedProcess(command, 0, json.dumps({"ok": True, "job_ids": {"prepare": "101", "analyze": "102"}}), "")
        if command[0] == "rsync":
            target = Path(command[-1])
            assert target.is_relative_to(isolate_storage)
            if target.name == "out":
                (target / "prepare-101.out").write_text("mock computation finished")
        elif command[0] == "scp":
            for local in command[1:-1]:
                assert Path(local).is_relative_to(isolate_storage)
        elif command[0] != "ssh":
            raise AssertionError(command)
        return CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("subprocess.run", fake_run)
    jobs = {
        name: {"name": name, "script": "echo result", "dependencies": dependencies,
               "slurm": {}, "script_args": {"output_dir": "study"}}
        for name, dependencies in [("prepare", []), ("analyze", ["prepare"]) ]
    }
    save_bundle(jobs, "study")
    submit_jobs("study", machine="mock")
    saved = json.loads(next(storage.jobs_dir().glob("*.json")).read_text())
    assert saved["prepare"]["id"] == "101"
    assert saved["analyze"]["id"] == "102"
    for script in storage.slurm_dir().glob("*.sh"):
        content = script.read_text()
        assert cfg["storage_root"] + "/out/%x-%j.out" in content
        assert cfg["storage_root"] + "/results/study" in content
        assert "/remote/stable" not in content
    sync_machine("mock")
    assert (storage.out_dir() / "prepare-101.out").read_text() == "mock computation finished"
    assert resolve_results_path("study/result.txt", machine_name="mock") == cfg["storage_root"] + "/results/study/result.txt"
    assert len([c for c in calls if c[0] == "rsync"]) == 3


@pytest.mark.parametrize("returncode,reported", [(0, "/remote/stable"), (0, ""), (1, "ImportError: old helper")])
def test_unknown_or_mismatched_helper_stops_before_submission(monkeypatch, returncode, reported):
    cfg = machine()
    save_config({"machines": {"mock": cfg}, "default_machine": "mock"})
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return CompletedProcess(command, returncode, reported, "")

    monkeypatch.setattr("subprocess.run", fake_run)
    with pytest.raises(RuntimeError):
        submit_jobs("does-not-exist", machine="mock")
    assert len(calls) == 1
    assert calls[0][-1].startswith("bash -lc ")
    assert not list(storage.jobs_dir().iterdir())
    assert not list(storage.slurm_dir().iterdir())
    with pytest.raises(RuntimeError):
        sync_machine("mock")
    assert all(c[0] == "ssh" and c[-1].startswith("bash -lc ") for c in calls)


@pytest.mark.parametrize("root", [None, "", "relative/state"])
def test_invalid_remote_selector_does_not_use_legacy_path(root):
    cfg = machine()
    cfg["storage_root"] = root
    with pytest.raises(ValueError, match="absolute POSIX path"):
        remote_storage_root_from_config(cfg)


def test_helper_rejects_payload_outside_selected_root(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("AUTOSLURM_STORAGE_ROOT", str(storage.storage_root()))
    payload = tmp_path / "payload.json"
    payload.write_text(json.dumps({"children_by_job": {"a": []}, "slurm_names": {"a": "a.sh"}, "slurm_dir": "/remote/stable/slurm"}))

    def must_not_submit(*args, **kwargs):
        pytest.fail("Helper submitted outside selected state")

    monkeypatch.setattr(bulk_submit_driver, "submit_payload", must_not_submit)
    with pytest.raises(SystemExit) as error:
        bulk_submit_driver.main(["--payload-file", str(payload)])
    assert error.value.code == 1
    result = json.loads(capsys.readouterr().out)
    assert not result["ok"]
    assert "selected storage root" in result["error"]


def test_configuration_editor_preserves_selected_remote_root(monkeypatch):
    from autoslurm.apps import configuration

    cfg = machine()
    monkeypatch.setattr(configuration, "_prompt_text", lambda prompt, default=None, required=False: default or "")
    monkeypatch.setattr(configuration, "_prompt_yes_no", lambda *args, **kwargs: True)
    monkeypatch.setattr("builtins.input", lambda *args: "1")
    assert configuration._prompt_machine_details(cfg)["storage_root"] == cfg["storage_root"]


def test_configuration_validation_reports_mismatched_root(monkeypatch, capsys):
    from autoslurm.apps import configuration

    monkeypatch.setattr("subprocess.run", lambda command, **kwargs: CompletedProcess(command, 0, "/remote/stable", ""))
    assert not configuration._validate_machine(machine(), "mock")
    assert "Storage root check: failed" in capsys.readouterr().out
