"""Public config failures retain exact identity and never reset existing evidence."""

import builtins
import errno
import json

import pytest

from autoslurm import ConfigurationError, load_config, save_config, machine_config, save_bundle, submit_jobs, preview_bundle
from autoslurm import config, storage
from autoslurm.apps import config as config_cli, configuration as legacy_cli, root


def invoke(route, arguments):
    if route in {"config", "configuration"}:
        return root.main([route, *arguments])
    return (config_cli.main if route == "standalone" else legacy_cli.main)(arguments)


def valid_config():
    return {"machines": {"cluster": {"ssh_alias": "research", "venv_path": "/env"}},
            "default_machine": "cluster"}


@pytest.mark.parametrize("raw,code,cause_type", [
    (b'{"password": "retained-secret",', "record_invalid", json.JSONDecodeError),
    (b'\xff', "record_invalid", UnicodeDecodeError),
])
def test_corrupt_reads_preserve_original_cause_and_hide_contents(raw, code, cause_type):
    path = storage.config_file_path()
    path.write_bytes(raw)
    with pytest.raises(ConfigurationError) as stopped:
        load_config()
    error = stopped.value
    assert isinstance(error.__cause__, cause_type)
    data = error.diagnostic.to_dict()
    assert data["code"] == code and data["context"]["path"] == str(path)
    assert data["effects"] == {"config_write": "not_started"}
    assert data["cause"]["kind"] == cause_type.__name__
    assert "retained-secret" not in json.dumps(data)
    assert path.read_bytes() == raw


@pytest.mark.parametrize("route", ["config", "configuration", "standalone", "legacy-standalone"])
@pytest.mark.parametrize("failure", ["corrupt", "denied", "directory"])
def test_cli_read_failures_never_prompt_reset_write_or_connect(monkeypatch, capsys, route, failure):
    path = storage.config_file_path()
    original = b'{"password": "retained-secret",'
    if failure == "directory":
        path.mkdir()
    else:
        path.write_bytes(original)
    real_open = builtins.open

    def read(target, *args, **kwargs):
        if failure == "denied" and target == path:
            raise PermissionError(errno.EACCES, "Permission denied", str(path))
        return real_open(target, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", read)
    monkeypatch.setattr("builtins.input", lambda *a: pytest.fail("Existing file must not trigger reset/create"))
    monkeypatch.setattr("subprocess.run", lambda *a, **k: pytest.fail("No command permitted"))
    with pytest.raises(SystemExit) as stopped:
        invoke(route, ["--interactive"])
    assert stopped.value.code == 1
    output = capsys.readouterr()
    assert output.out == "" and str(path) in output.err
    expected = "record_invalid" if failure == "corrupt" else "resource_inaccessible"
    assert expected in output.err and "config_write=not_started" in output.err
    assert "retained-secret" not in output.err and "Next:" in output.err
    assert "Traceback" not in output.err
    if failure == "directory":
        assert path.is_dir() and list(path.iterdir()) == []
    else:
        assert path.read_bytes() == original


@pytest.mark.parametrize("data,field,machine", [
    (None, "configuration", None),
    ([], "configuration", None),
    ({"machines": None}, "machines", None),
    ({"machines": []}, "machines", None),
    ({"machines": {}}, "machines", None),
    ({"machines": {"cluster": None}}, "machines", "cluster"),
    ({"machines": {"machines": {}}}, "machines", None),
    ({"machines": {"cluster": {}}, "default_machine": []}, "default_machine", None),
    ({"machines": {"cluster": {}}, "default_machine": "absent"}, "default_machine", "absent"),
    ({"machines": {"cluster": {"slurm_account": 7}}}, "slurm_account", "cluster"),
    ({"machines": {"cluster": {"venv_path": 7}}}, "venv_path", "cluster"),
    ({"machines": {"cluster": {"env_command": {"password": "retained-secret"}}}}, "env_command", "cluster"),
    ({"machines": {"cluster": {"ssh_alias": "--bad alias"}}}, "ssh_alias", "cluster"),
    ({"machines": {"cluster": {"software_root": "relative/code"}}}, "software_root", "cluster"),
    ({"machines": {"cluster": {"project_root": "/old", "results_root": "/new"}}}, "results_root", "cluster"),
])
def test_shape_and_profile_errors_name_field_and_machine_without_exposing_values(data, field, machine):
    path = storage.config_file_path()
    path.write_text(json.dumps(data))
    before = path.read_bytes()
    with pytest.raises(ConfigurationError) as stopped:
        load_config()
    diagnostic = stopped.value.diagnostic
    assert isinstance(stopped.value, ValueError)  # Common validation catches remain usable.
    assert diagnostic.code == "configuration_invalid"
    assert diagnostic.context["field"] == field
    assert diagnostic.context.get("machine") == machine
    assert diagnostic.context["path"] == str(path)
    assert "retained-secret" not in json.dumps(diagnostic.to_dict())
    assert path.read_bytes() == before


def test_invalid_save_is_diagnosed_before_any_publication(monkeypatch):
    save_config(valid_config())
    before = storage.config_file_path().read_bytes()
    monkeypatch.setattr(config, "atomic_json", lambda *a, **k: pytest.fail("Invalid input must not publish"))
    invalid = valid_config()
    invalid["default_machine"] = "absent"
    with pytest.raises(ConfigurationError) as stopped:
        save_config(invalid)
    assert stopped.value.diagnostic.context["field"] == "default_machine"
    assert stopped.value.diagnostic.effects["config_write"] == "not_started"
    assert storage.config_file_path().read_bytes() == before


def test_missing_configuration_has_a_distinct_contract_and_does_not_create_it():
    with pytest.raises(ConfigurationError) as stopped:
        load_config()
    assert isinstance(stopped.value.__cause__, FileNotFoundError)
    assert stopped.value.diagnostic.code == "resource_missing"
    assert "asl config --interactive" in stopped.value.diagnostic.next_action
    assert stopped.value.diagnostic.context["path"] == str(storage.config_file_path())
    assert not storage.config_file_path().exists()


def test_selected_root_and_unreadable_primary_never_fall_back(monkeypatch):
    path = storage.config_file_path()
    legacy = path.parent / "src" / path.name
    legacy.parent.mkdir()
    legacy.write_text(json.dumps(valid_config()))
    monkeypatch.setenv(storage.STORAGE_ROOT_ENVIRONMENT_VARIABLE, str(path.parent))
    with pytest.raises(ConfigurationError) as missing:
        load_config()
    assert missing.value.diagnostic.code == "resource_missing"
    monkeypatch.delenv(storage.STORAGE_ROOT_ENVIRONMENT_VARIABLE)
    path.write_text("original unreadable bytes")
    real_open = builtins.open
    reads = []

    def deny_primary(target, *args, **kwargs):
        reads.append(target)
        if target == path:
            raise PermissionError(errno.EACCES, "Denied", str(path))
        return real_open(target, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", deny_primary)
    with pytest.raises(ConfigurationError) as denied:
        load_config()
    assert denied.value.diagnostic.code == "resource_inaccessible"
    assert denied.value.diagnostic.cause.errno == errno.EACCES
    assert reads == [path]


def test_legacy_source_identity_survives_selection_failure_and_filter_metadata():
    primary = storage.config_file_path()
    legacy = primary.parent / "src" / primary.name
    legacy.parent.mkdir()
    legacy.write_text(json.dumps({"cluster": {"venv_path": "/env"}, "bundle_filter_mode": "all"}))
    assert load_config()["bundle_filter_mode"] == "all"
    with pytest.raises(ConfigurationError) as stopped:
        machine_config(machine="absent")
    assert stopped.value.diagnostic.context == {"machine": "absent", "field": "machine", "path": str(legacy)}
    assert not primary.exists()


def test_dangling_config_symlink_is_not_treated_as_first_use(monkeypatch):
    path = storage.config_file_path()
    target = path.parent / "missing-target.json"
    path.symlink_to(target)
    monkeypatch.setattr("builtins.input", lambda *a: pytest.fail("Do not replace dangling symlink"))
    with pytest.raises(SystemExit) as stopped:
        config_cli.main(["--interactive"])
    assert stopped.value.code == 1 and path.is_symlink() and not target.exists()


def test_entry_created_after_missing_read_is_preserved_without_creation_prompt(monkeypatch):
    path = storage.config_file_path()
    real_open = builtins.open
    original = b"concurrent operator contents"

    def appeared(target, *args, **kwargs):
        if target == path:
            with real_open(path, "wb") as stream:
                stream.write(original)
            raise FileNotFoundError(errno.ENOENT, "Changed during read", str(path))
        return real_open(target, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", appeared)
    monkeypatch.setattr("builtins.input", lambda *a: pytest.fail("Do not replace a newly present entry"))
    with pytest.raises(SystemExit) as stopped:
        config_cli.main(["--interactive"])
    assert stopped.value.code == 1 and path.read_bytes() == original


def test_profile_override_diagnosis_keeps_selected_machine_source_and_original_cause():
    save_config(valid_config())
    before = storage.config_file_path().read_bytes()
    with pytest.raises(ConfigurationError) as stopped:
        machine_config(machine="cluster", overrides={"results_root": "relative/input"})
    diagnostic = stopped.value.diagnostic
    assert diagnostic.context["source"] == "profile_overrides"
    assert diagnostic.context["machine"] == "cluster"
    assert diagnostic.context["field"] == "results_root" and diagnostic.context["logical_path"] == "relative/input"
    assert isinstance(stopped.value.__cause__, ValueError)
    assert storage.config_file_path().read_bytes() == before


@pytest.mark.parametrize("bug", [ValueError("unexpected bug"), TypeError("unexpected bug"), KeyError("unexpected bug")])
def test_programming_errors_are_not_converted_to_expected_cli_failures(monkeypatch, bug):
    save_config(valid_config())

    def fail(*args, **kwargs):
        raise bug

    monkeypatch.setattr(config, "_normalize_config", fail)
    with pytest.raises(type(bug)) as stopped:
        config_cli.main(["--summary"])
    assert stopped.value is bug


def test_cli_debug_retains_expected_exception_and_original_json_cause(capsys):
    storage.config_file_path().write_text("{")
    with pytest.raises(ConfigurationError) as stopped:
        root.main(["config", "--summary", "--debug"])
    assert isinstance(stopped.value.__cause__, json.JSONDecodeError)
    assert capsys.readouterr() == ("", "")


def test_raw_view_keeps_its_shape_and_unknown_default_edit_is_diagnosed(capsys):
    original = {"cluster": {"venv_path": "/env"}}
    storage.config_file_path().write_text(json.dumps(original))
    config_cli.main(["--view"])
    assert json.loads(capsys.readouterr().out) == original
    before = storage.config_file_path().read_bytes()
    with pytest.raises(SystemExit) as stopped:
        config_cli.main(["--set-default", "absent"])
    assert stopped.value.code == 1
    assert "Default machine" not in capsys.readouterr().out
    assert storage.config_file_path().read_bytes() == before


@pytest.mark.parametrize("name", ["", "absent"])
def test_unknown_default_never_enters_interactive_mode(monkeypatch, name):
    save_config(valid_config())
    before = storage.config_file_path().read_bytes()
    monkeypatch.setattr("builtins.input", lambda *a: pytest.fail("Bad selector must not enter the editor"))
    with pytest.raises(SystemExit) as stopped:
        config_cli.main(["--set-default", name])
    assert stopped.value.code == 1 and storage.config_file_path().read_bytes() == before


def test_debug_alone_only_shows_help(monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda *a: pytest.fail("Debug is not a request to create config"))
    config_cli.main(["--debug"])
    assert "usage:" in capsys.readouterr().out and not storage.config_file_path().exists()


@pytest.mark.parametrize("operation", ["preview", "submit"])
def test_invalid_configuration_stops_public_job_operations_before_any_command(monkeypatch, operation):
    bundle = save_bundle({"fit": {"script": "science", "slurm": {}}}, "study")
    before = bundle.read_bytes()
    storage.config_file_path().write_text(json.dumps({"machines": {"cluster": {"venv_path": []}}}))
    monkeypatch.setattr("subprocess.run", lambda *a, **k: pytest.fail("No SSH, shell validation or scheduler allowed"))
    with pytest.raises(ConfigurationError) as stopped:
        if operation == "preview":
            preview_bundle(bundle)
        else:
            submit_jobs("study", bundle_path=bundle)
    assert stopped.value.diagnostic.context["field"] == "venv_path"
    assert bundle.read_bytes() == before and list(storage.slurm_dir().iterdir()) == []
    assert not (storage.storage_root() / "submissions").exists()


def test_legacy_status_compatibility_keeps_unavailable_config_out_of_local_queries(monkeypatch):
    from autoslurm.status import _fetch_statuses_for_job_ids
    monkeypatch.setattr("subprocess.run", lambda *a, **k: pytest.fail("No local or remote scheduler fallback"))
    assert _fetch_statuses_for_job_ids(["123"], "missing-profile") == {}
