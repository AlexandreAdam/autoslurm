"""Two scientific roots, canonical config command and producing-path evidence."""

import json
from pathlib import Path

import pytest

from autoslurm import load_config, save_config, recorded_execution
from autoslurm.execution import resolve_execution_context, EXECUTION_METADATA_KEY
from autoslurm.storage import config_file_path


def test_inputs_working_directory_and_outputs_share_results_root(tmp_path):
    root = tmp_path / "study data"
    (root / "inputs").mkdir(parents=True)
    (root / "work").mkdir()
    (root / "inputs/data.json").write_text("[]")
    context = resolve_execution_context("mock", {"software_root": str(tmp_path / "software"), "results_root": str(root)})
    job = {"name": "sample", "working_directory": "work", "input_args": ["input"],
           "script_args": {"input": "inputs/data.json", "output_dir": "outputs/run-1"}}
    context.validate_jobs([job])
    evidence = context.resolve_job(job)
    assert evidence["working_directory"] == str(root / "work")
    assert evidence["resolved_paths"] == {"input": str(root / "inputs/data.json"), "output_dir": str(root / "outputs/run-1")}
    assert evidence["software_root"] == str(tmp_path / "software")
    assert "project_root" not in evidence


def test_software_root_is_recorded_without_clone_or_discovery(tmp_path, monkeypatch):
    monkeypatch.setattr("subprocess.run", lambda *a, **kw: pytest.fail("Configuration must not run commands"))
    context = resolve_execution_context("mock", {"software_root": "/software", "results_root": str(tmp_path)})
    evidence = context.resolve_job({"script_args": {"output_dir": "run"}})
    assert evidence["software_root"] == "/software"
    assert evidence["working_directory"] == str(tmp_path)


def test_project_only_profile_is_normalized_to_one_data_root():
    save_config({"machines": {"mock": {"project_root": "/data"}}, "default_machine": "mock"})
    profile = load_config()["machines"]["mock"]
    assert profile == {"results_root": "/data"}
    assert "project_root" not in config_file_path().read_text()


def test_conflicting_legacy_roots_are_rejected_without_overwriting_config():
    save_config({"machines": {"mock": {"results_root": "/data"}}, "default_machine": "mock"})
    before = config_file_path().read_bytes()
    with pytest.raises(ValueError, match="project_root.*results_root"):
        save_config({"machines": {"mock": {"project_root": "/old-inputs", "results_root": "/old-results"}}, "default_machine": "mock"})
    assert config_file_path().read_bytes() == before


def test_config_is_canonical_action_with_legacy_alias():
    from autoslurm.apps import root
    assert "config" in root.ACTION_HANDLERS
    assert "config" in root.ACTION_HELP
    assert root.ACTION_ALIASES["configuration"] == "config"
    assert "project_root" not in __import__("autoslurm").MACHINE_KEYS
    assert "software_root" in __import__("autoslurm").MACHINE_KEYS


def test_config_editor_and_summary_expose_only_two_scientific_roots(tmp_path, monkeypatch, capsys):
    from autoslurm.apps import config
    answers = iter(["/env", "account", str(tmp_path / "software"), str(tmp_path / "data")])
    monkeypatch.setattr(config, "_prompt_text", lambda *a, **k: next(answers))
    monkeypatch.setattr(config, "_prompt_yes_no", lambda *a, **k: False)
    profile = config._prompt_machine_details()
    save_config({"machines": {"mock": profile}, "default_machine": "mock"})
    config.main(["--summary"])
    text = capsys.readouterr().out
    assert "software_root" in text and "results_root" in text
    assert "project_root" not in text
    assert profile["software_root"] == str(tmp_path / "software")
    assert profile["results_root"] == str(tmp_path / "data")


@pytest.mark.parametrize("value", ["", "relative/code", "  "])
def test_invalid_software_root_fails_before_remote_discovery(value):
    with pytest.raises(ValueError, match="software_root"):
        resolve_execution_context("remote", {"hostname": "cluster", "software_root": value},
                                  root_resolver=lambda *a: pytest.fail("Invalid root must fail before discovery"))


def test_historical_split_roots_remain_readable_without_profile_reinterpretation(tmp_path):
    from autoslurm.execution import execution_context_from_snapshot
    evidence = {"machine": "old", "storage_root": "/old/state", "project_root": "/old/inputs",
                "results_root": "/old/outputs", "is_remote": False, "transport": {}}
    path = tmp_path / "historical_20260101000000.json"
    path.write_text(json.dumps({"sample": {"name": "sample", "script": "science", EXECUTION_METADATA_KEY: evidence}}))
    context = execution_context_from_snapshot(path)
    assert context.resolve_path("measurements", "project") == "/old/inputs/measurements"
    assert context.resolve_path("summary", "results") == "/old/outputs/summary"
    assert recorded_execution(path) == evidence


def test_config_flags_resolve_old_split_and_preserve_other_fields(monkeypatch):
    from autoslurm.apps import root
    config_file_path().write_text(json.dumps({"machines": {"cluster": {"hostname": "saved-host", "venv_path": "/env", "project_root": "/old-inputs", "results_root": "/old-outputs"}}, "default_machine": "cluster"}))
    monkeypatch.setattr("subprocess.run", lambda *a, **kw: pytest.fail("Root edit must not contact cluster"))
    root.main(["config", "--machine", "cluster", "--software-root", "/software", "--results-root", "/study"])
    profile = load_config()["machines"]["cluster"]
    assert profile == {"ssh_alias": "saved-host", "venv_path": "/env", "software_root": "/software", "results_root": "/study"}


def test_config_invalid_edit_and_unknown_machine_preserve_file():
    from autoslurm.apps.config import main
    save_config({"machines": {"mock": {"results_root": "/data"}}, "default_machine": "mock"})
    before = config_file_path().read_bytes()
    for args in (["--software-root", "relative"], ["--machine", "missing", "--results-root", "/data"]):
        with pytest.raises(SystemExit):
            main(args)
        assert config_file_path().read_bytes() == before


def test_new_saved_execution_uses_two_roots_after_profile_edits(tmp_path, monkeypatch):
    from autoslurm.execution import execution_context_from_snapshot
    evidence = resolve_execution_context("mock", {"results_root": "/data", "software_root": "/software"}).resolve_job({})
    path = tmp_path / "run_20260101000000.json"
    path.write_text(json.dumps({"sample": {"name": "sample", "script": "science", EXECUTION_METADATA_KEY: evidence}}))
    save_config({"machines": {"mock": {"results_root": "/replacement", "software_root": "/other-code"}}, "default_machine": "mock"})
    monkeypatch.setattr("subprocess.run", lambda *a, **kw: pytest.fail("Saved paths must not discover machine"))
    context = execution_context_from_snapshot(path)
    assert context.resolve_path("inputs/data", "project") == "/data/inputs/data"
    assert context.resolve_path("outputs/summary") == "/data/outputs/summary"
    assert context.software_root == "/software"
    assert "project_root" not in recorded_execution(path)
