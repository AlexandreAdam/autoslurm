import json
import pytest
from autoslurm.apps import inspect as cli
from autoslurm.storage import out_dir, slurm_dir
from autoslurm.utils import save_config
from tests.inspection_helpers import saved_run, mock_scheduler


@pytest.fixture
def run(monkeypatch):
    save_config({"machines": {"local": {}}, "default_machine": "local", "bundle_filter_mode": "all"})
    path = saved_run(jobs={"array": {"id": "101", "slurm": {"array": "0-2"}}})
    (out_dir() / "array-101_1.out").write_text("first\nsecond\nlast\n")
    (slurm_dir() / "array_20250101000000.sh").write_text("#!/bin/bash\necho scientific-script")
    mock_scheduler(monkeypatch, accounting="101_0|COMPLETED|0:0|None|500\n101_1|FAILED|1:0|None|501")
    return path


@pytest.mark.parametrize("selector", [["study"], ["--latest"], ["1"], ["--bundle-file", "PATH"]])
def test_inspect_default_table_uses_shared_status(run, capsys, selector):
    cli.main([str(run) if value == "PATH" else value for value in selector])
    text = capsys.readouterr().out
    assert "FAILED" in text and "array" in text
    assert "Observation:" in text


@pytest.mark.parametrize("flag", ["--log", "--logs", "--list-files"])
def test_log_aliases_resolve_saved_job_task_identity(run, capsys, flag):
    cli.main(["study", "--job", "array", "--array-task", "1", flag, "--tail", "1"])
    text = capsys.readouterr().out
    assert "array-101_1.out" in text
    if flag != "--list-files":
        assert "last" in text.splitlines() and "first" not in text.splitlines()


def test_job_defaults_to_bounded_logs(run, capsys):
    cli.main(["study", "--job", "array", "--array-task", "1"])
    assert "last" in capsys.readouterr().out


def test_array_display_index_selects_the_same_task_for_logs(run, capsys):
    cli.main(["study", "--array", "--job", "2"])
    assert "array-101_1.out" in capsys.readouterr().out


def test_script_view_does_not_dump_logs(run, capsys):
    cli.main(["study", "--job", "array", "--script", "--cached"])
    text = capsys.readouterr().out
    assert "scientific-script" in text
    assert "last" not in text


def test_status_view_keeps_all_declared_array_indices(run, capsys):
    cli.main(["study", "--array", "--status"])
    text = capsys.readouterr().out
    assert "101_0" in text and "101_1" in text and "101_2" in text
    assert "UNKNOWN" in text


def test_explicit_json_matches_job_and_task_identity(run, capsys):
    cli.main(["--bundle-file", str(run), "--job", "array", "--array-task", "1", "--json"])
    view = json.loads(capsys.readouterr().out)
    assert view["logs"][0]["task_index"] == 1
    assert view["jobs"][0]["tasks"][1]["job_id"] == "101_1"


def test_cached_view_never_contacts_scheduler(run, monkeypatch, capsys):
    cli.main(["study", "--json"])
    capsys.readouterr()
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: pytest.fail("Cached read made a command"))
    cli.main(["study", "--cached", "--json"])
    assert json.loads(capsys.readouterr().out)["freshness"] == "stale"


@pytest.mark.parametrize("args", [["--latest", "study"], ["study", "--cached", "--refresh"], ["study", "--array", "--job", "9"]])
def test_conflicting_or_invalid_selectors_stop(run, args):
    with pytest.raises(SystemExit):
        cli.main(args)


def test_inspect_clipboard_copies_the_same_rendered_output(run, monkeypatch, capsys):
    captured = []
    monkeypatch.setattr(cli, "_copy_to_clipboard", captured.append)
    cli.main(["study", "--cached", "--clip"])
    assert captured[0] == capsys.readouterr().out.rstrip("\n")


def test_inspect_without_selector_shows_help(capsys):
    cli.main([])
    assert "usage:" in capsys.readouterr().out
