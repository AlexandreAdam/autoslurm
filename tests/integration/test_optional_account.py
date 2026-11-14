"""Account selection and clearing through public config/preview/submission paths."""

import json
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from autoslurm import load_config, preview_bundle, save_bundle, save_config, submit_jobs
from autoslurm.apps import config, root
from autoslurm.config import machine_config, set_machine_settings
from autoslurm.storage import config_file_path


def save_profiles():
    data = {
        "machines": {
            "remote": {"ssh_alias": "cluster", "venv_path": "/env", "slurm_account": "old",
                       "software_root": "/software", "results_root": "/data", "storage_root": "/state"},
            "local": {"env_command": "true", "slurm_account": "local-account"},
        },
        "default_machine": "remote", "bundle_filter_mode": "all",
    }
    save_config(data)
    return data


@pytest.mark.parametrize("account", [None, "", "  ", "\t"])
def test_unset_account_is_normalized_on_read_save_and_selection(account):
    # Read old hand-edited profiles too, rather than normalizing the fixture first.
    data = {"machines": {"mock": {"env_command": "true", "slurm_account": account}},
            "default_machine": "mock"}
    config_file_path().write_text(json.dumps(data))
    loaded = load_config()
    assert "slurm_account" not in loaded["machines"]["mock"]
    assert "slurm_account" not in machine_config()[1]
    save_config(loaded)
    assert "slurm_account" not in json.loads(config_file_path().read_text())["machines"]["mock"]


def test_config_set_clear_and_summary_are_local_and_preserve_other_settings(monkeypatch, capsys):
    expected = save_profiles()
    monkeypatch.setattr("subprocess.run", lambda *a, **k: pytest.fail("Config must not contact a machine"))
    # Default selection and the canonical root command exercise the daily interface.
    root.main(["config", "--clear-slurm-account"])
    expected["machines"]["remote"].pop("slurm_account")
    assert json.loads(config_file_path().read_text()) == expected
    root.main(["config", "--summary"])
    assert "remote remote yes cluster - /env" in capsys.readouterr().out
    # Clearing an already absent account is harmless; the compatibility command works too.
    root.main(["configuration", "--machine", "remote", "--clear-slurm-account"])
    assert json.loads(config_file_path().read_text()) == expected
    root.main(["config", "--machine", "remote", "--slurm-account", "new-account"])
    expected["machines"]["remote"]["slurm_account"] = "new-account"
    assert json.loads(config_file_path().read_text()) == expected


@pytest.mark.parametrize("args", [
    ["--slurm-account", "new", "--clear-slurm-account"],
    ["--clear-slurm-account", "--view"],
    ["--machine", "missing", "--clear-slurm-account"],
])
def test_invalid_account_edit_preserves_file(args):
    save_profiles()
    before = config_file_path().read_bytes()
    with pytest.raises(SystemExit):
        config.main(args)
    assert config_file_path().read_bytes() == before


def test_setting_other_fields_keeps_account_and_empty_account_override_clears_only_in_memory():
    save_profiles()
    set_machine_settings("remote", software_root="/new-software")
    before = config_file_path().read_bytes()
    assert machine_config(machine="remote")[1]["slurm_account"] == "old"
    assert "slurm_account" not in machine_config(machine="remote", overrides={"slurm_account": ""})[1]
    assert machine_config(machine="remote", overrides={"slurm_account": "override"})[1]["slurm_account"] == "override"
    assert config_file_path().read_bytes() == before
    with pytest.raises(ValueError, match="not both"):
        set_machine_settings("remote", slurm_account="new", clear_slurm_account=True)
    assert config_file_path().read_bytes() == before


@pytest.mark.parametrize("answer,cleared", [("", False), ("-", True)])
def test_interactive_editor_can_keep_or_clear_optional_fields(monkeypatch, answer, cleared):
    existing = save_profiles()["machines"]["remote"]
    answers = iter(["", "", answer, "", answer, answer, ""])
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    monkeypatch.setattr("subprocess.run", lambda *a, **k: pytest.fail("Prompting must not connect"))
    edited = config._prompt_machine_details(existing)
    expected = dict(existing)
    if cleared:
        for key in ("slurm_account", "software_root", "results_root"):
            expected.pop(key)
    assert edited == expected


def test_new_profile_can_omit_account_and_required_fields_cannot_be_cleared(monkeypatch):
    answers = iter(["-", "/env", "", "", "n", "", ""])
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    assert config._prompt_machine_details() == {"venv_path": "/env"}


@pytest.mark.parametrize("account", [None, "configured-account"])
def test_preview_and_mock_submission_agree_after_account_clear(account, monkeypatch):
    save_config({"machines": {"mock": {"env_command": "true", "slurm_account": "old"}},
                 "default_machine": "mock"})
    config.main(["--clear-slurm-account"] if account is None else ["--slurm-account", account])
    selected = save_bundle({"sample": {"script": "science", "slurm": {"partition": "gpu"}}}, "study")
    submitted = []

    def scheduler(command, **kwargs):
        if command == ["bash", "-n"]:
            return CompletedProcess(command, 0, "", "")
        assert command[0] == "sbatch"
        submitted.append(Path(command[-1]).read_text())
        return CompletedProcess(command, 0, "Submitted batch job 101", "")

    monkeypatch.setattr("subprocess.run", scheduler)
    script = preview_bundle(selected)["jobs"]["sample"]["script"]
    receipt = submit_jobs("study", bundle_path=selected)
    assert receipt["jobs"]["sample"]["id"] == "101"
    assert submitted == [script]
    assert "#SBATCH --partition=gpu\n" in script
    assert ([line for line in script.splitlines() if line.startswith("#SBATCH --account")]
            == ([] if account is None else [f"#SBATCH --account={account}"]))


def test_explicit_job_account_remains_supported_when_profile_account_is_unset(monkeypatch):
    save_config({"machines": {"mock": {"env_command": "true"}}, "default_machine": "mock"})
    monkeypatch.setattr("subprocess.run", lambda command, **kw: CompletedProcess(command, 0, "", ""))
    selected = save_bundle({"sample": {"script": "science", "slurm": {"account": "job-account"}}}, "study")
    assert "#SBATCH --account=job-account\n" in preview_bundle(selected)["jobs"]["sample"]["script"]


def test_remote_script_omits_account_without_requiring_a_connection(monkeypatch):
    from io import StringIO
    from autoslurm.execution import resolve_execution_context
    from autoslurm.job_to_slurm import write_slurm_content

    save_profiles()
    config.main(["--clear-slurm-account"])
    name, profile = machine_config()
    monkeypatch.setattr("subprocess.run", lambda *a, **k: pytest.fail("Render must use the resolved context"))
    context = resolve_execution_context(name, profile, root_resolver=lambda *a: "/state")
    content = StringIO()
    write_slurm_content(content, {"name": "env", "script": "science", "slurm": {"partition": "gpu"}}, profile, context=context)
    assert "--account" not in content.getvalue()
    assert "#SBATCH --partition=gpu\n" in content.getvalue()


def test_interactive_edit_saves_account_removal_and_retains_validation(monkeypatch):
    expected = save_profiles()
    answers = iter(["1", "1", "", "", "-", "", "", "", "", "6"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    validated = []
    monkeypatch.setattr(config, "_validate_machine", lambda profile, name: validated.append((name, dict(profile))))
    config.main(["--interactive"])
    expected["machines"]["remote"].pop("slurm_account")
    assert json.loads(config_file_path().read_text()) == expected
    assert validated == [("remote", expected["machines"]["remote"])]
