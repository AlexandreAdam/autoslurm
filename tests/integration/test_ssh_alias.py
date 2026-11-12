"""Current profiles use SSH aliases; historical transports retain their evidence."""

import json
from subprocess import CompletedProcess

import pytest

from autoslurm import load_config, save_config
from autoslurm.config import normalize_machine_profile
from autoslurm.execution import resolve_execution_context, execution_context_from_snapshot, EXECUTION_METADATA_KEY
from autoslurm.storage import config_file_path
from autoslurm.transport import ssh_command


def test_ssh_alias_is_a_single_argument_and_saved_transport_has_no_credentials(tmp_path):
    context = resolve_execution_context("cluster", {"ssh_alias": "research-gpu", "path": "/state"})
    assert context.is_remote
    assert ssh_command(context.config, remote_command="true") == ["ssh", "research-gpu", "true"]
    assert context.resolve_job({})["transport"] == {"ssh_alias": "research-gpu"}


def test_old_hostname_alias_normalizes_and_drops_duplicate_ssh_settings():
    profile = normalize_machine_profile({"hostname": "research-gpu", "hosturl": "old-host", "username": "old-user", "key_path": "/old/key", "results_root": "/data"})
    assert profile == {"ssh_alias": "research-gpu", "results_root": "/data"}


def test_explicit_host_profile_requires_an_alias_without_overwriting_saved_config():
    save_config({"machines": {"mock": {}}, "default_machine": "mock"})
    before = config_file_path().read_bytes()
    with pytest.raises(ValueError, match="ssh_alias"):
        save_config({"machines": {"remote": {"hosturl": "cluster", "username": "user"}}, "default_machine": "remote"})
    assert config_file_path().read_bytes() == before


@pytest.mark.parametrize("alias", ["", " ", "-oProxyCommand=cmd", "user@cluster", "cluster true", "cluster\nother", "cluster:/path"])
def test_invalid_alias_fails_before_remote_discovery(alias):
    with pytest.raises(ValueError, match="ssh_alias"):
        resolve_execution_context("remote", {"ssh_alias": alias}, root_resolver=lambda *a: pytest.fail("Invalid alias must not discover hosts"))


def test_config_alias_edit_is_local_and_replaces_legacy_connection_fields(monkeypatch):
    from autoslurm.apps.config import main
    config_file_path().write_text(json.dumps({"machines": {"remote": {"hostname": "mistaken-user", "username": "user", "hosturl": "actual-host", "key_path": "/key", "results_root": "/data"}}, "default_machine": "remote"}))
    monkeypatch.setattr("subprocess.run", lambda *a, **kw: pytest.fail("Alias edit must not contact cluster"))
    main(["--machine", "remote", "--ssh-alias", "research-gpu"])
    assert load_config()["machines"]["remote"] == {"ssh_alias": "research-gpu", "results_root": "/data"}


def test_editor_only_prompts_for_alias_and_summary_shows_it(monkeypatch, capsys):
    from autoslurm.apps import config
    prompts = []
    values = iter(["/env", "account", "/software", "/data", "research-gpu"])
    def prompt(text, *args, **kwargs):
        prompts.append(text)
        return next(values)
    monkeypatch.setattr(config, "_prompt_text", prompt)
    monkeypatch.setattr(config, "_prompt_yes_no", lambda *a, **kw: True)
    monkeypatch.setattr("builtins.input", lambda *a: pytest.fail("No connection-mode question"))
    profile = config._prompt_machine_details()
    assert profile["ssh_alias"] == "research-gpu"
    assert not {"hostname", "username", "hosturl", "key_path"} & set(profile)
    assert not any("username" in p.lower() or "private key" in p.lower() for p in prompts)
    save_config({"machines": {"remote": profile}, "default_machine": "remote"})
    config.main(["--summary"])
    assert "ssh_alias" in capsys.readouterr().out


def test_alias_copies_and_sync_use_ssh_config_without_identity_flags(monkeypatch, tmp_path):
    from autoslurm.file_transfer import transfer_slurms_to_remote, pull_storage_directory
    context = resolve_execution_context("remote", {"ssh_alias": "research-gpu", "path": "/state"})
    commands = []
    monkeypatch.setattr("subprocess.run", lambda cmd, **kw: commands.append(cmd) or CompletedProcess(cmd, 0, "", ""))
    transfer_slurms_to_remote(["a.sh", "b.sh"], context=context)
    pull_storage_directory(context, "out", tmp_path / "logs", mutable=True)
    assert [cmd[0] for cmd in commands] == ["ssh", "scp", "ssh", "rsync"]
    assert commands[0][1] == "research-gpu"
    assert commands[1][-1] == "research-gpu:/state/slurm/"
    assert commands[-1][-2] == "research-gpu:/state/out/"
    assert all("-i" not in cmd for cmd in commands)
    assert commands[-1][commands[-1].index("-e") + 1] == "ssh"


def test_alias_saved_run_is_not_redirected_by_profile_edits(tmp_path):
    evidence = resolve_execution_context("remote", {"ssh_alias": "original", "path": "/state"}).resolve_job({})
    path = tmp_path / "run_20260101000000.json"
    path.write_text(json.dumps({"sample": {"name": "sample", "script": "science", EXECUTION_METADATA_KEY: evidence}}))
    save_config({"machines": {"remote": {"ssh_alias": "replacement"}}, "default_machine": "remote"})
    context = execution_context_from_snapshot(path)
    assert ssh_command(context.config, remote_command="true") == ["ssh", "original", "true"]


def test_historical_explicit_transport_keeps_original_user_and_key(tmp_path):
    evidence = {"machine": "old", "storage_root": "/old/state", "results_root": "/old/data", "project_root": None,
                "is_remote": True, "transport": {"username": "old-user", "hosturl": "old-host", "key_path": "/keys/old key"}}
    path = tmp_path / "run_20260101000000.json"
    path.write_text(json.dumps({"sample": {"name": "sample", "script": "science", EXECUTION_METADATA_KEY: evidence}}))
    assert ssh_command(execution_context_from_snapshot(path).config, remote_command="true") == ["ssh", "-i", "/keys/old key", "old-user@old-host", "true"]


@pytest.mark.parametrize("flag", ["--hostname", "--hosturl", "--username", "--key_path", "--key-path"])
def test_retired_schedule_connection_flags_do_not_become_application_arguments(monkeypatch, flag):
    from autoslurm.apps import schedule
    monkeypatch.setattr(schedule, "parse_script_args", lambda *a, **kw: pytest.fail("Retired flags must stop before application discovery"))
    with pytest.raises(SystemExit):
        schedule.parse_args(["science", "--time", "00:01:00", flag, "old-value"])


def test_schedule_and_submit_expose_ssh_alias_without_credential_flags(monkeypatch):
    from autoslurm.apps import schedule, submit
    monkeypatch.setattr(schedule, "parse_script_args", lambda *a, **kw: {})
    args, _ = schedule.parse_args(["science", "--time", "00:01:00", "--ssh-alias", "research-gpu"])
    assert args.ssh_alias == "research-gpu"
    args = submit.parse_args(["study", "--ssh-alias", "research-gpu"])
    assert args.ssh_alias == "research-gpu"
    for flag in ("hostname", "hosturl", "username", "key_path"):
        assert not hasattr(args, flag)


def test_alias_submission_session_reuses_the_alias_without_identity_options(monkeypatch):
    from autoslurm.run_slurm import ssh_submission_session
    commands = []
    monkeypatch.setattr("subprocess.run", lambda cmd, **kw: commands.append(cmd) or CompletedProcess(cmd, 0, "", ""))
    with ssh_submission_session({"ssh_alias": "research-gpu"}, "remote") as options:
        assert options
    assert len(commands) == 3
    assert all(cmd[-1] == "research-gpu" and "-i" not in cmd for cmd in commands)
    assert "-G" in commands[0]
    assert "-MNf" in commands[1] and "exit" in commands[2]
