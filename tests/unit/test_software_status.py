"""Read-only inspection keeps missing, failed and observed evidence distinct."""

import json
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from autoslurm import save_config, inspect_software, software_expectations
from autoslurm.apps.software import main
from autoslurm.software_probe import inspect_software_root
from autoslurm.environment_probe import inspect_environment


def profile(tmp_path, remote=False):
    value = {"software_root": str(tmp_path / "projects"), "venv_path": "/runtime"}
    if remote:
        value["ssh_alias"] = "research-gpu"
    save_config({"machines": {"mock": value}, "default_machine": "mock"})
    return value


def test_missing_root_is_distinct_from_no_repositories_and_does_not_create_it(tmp_path):
    profile(tmp_path)
    assert inspect_software()["state"] == "missing"
    root = tmp_path / "projects"
    assert not root.exists()
    root.mkdir()
    assert inspect_software()["state"] == "observed"
    assert inspect_software()["projects"] == []


@pytest.mark.parametrize("project", ["/absolute", "../other", "a/../b", "x\\y", "x\ncommand"])
def test_unsafe_project_selector_is_rejected_before_ssh(tmp_path, project):
    profile(tmp_path, True)
    with pytest.raises(ValueError, match="relative"):
        inspect_software(project=project)


def test_remote_inspection_is_one_alias_ssh_with_no_installation_or_activation(tmp_path, monkeypatch):
    config = profile(tmp_path, True)
    commands = []
    def ssh(command, **options):
        commands.append(command)
        assert command[-2:] == ["research-gpu", "python3 -B -"]
        assert "BatchMode=yes" in command
        assert "GIT_OPTIONAL_LOCKS" in options["input"]
        assert "autoslurm" not in command[-1] and "source " not in command[-1]
        assert options["timeout"] == 60
        return CompletedProcess(command, 0, json.dumps({"version": 1, "software_root": config["software_root"],
            "state": "observed", "observed_at": "now", "projects": [], "truncated": False}), "")
    monkeypatch.setattr("subprocess.run", ssh)
    assert inspect_software()["ssh_alias"] == "research-gpu"
    assert len(commands) == 1


@pytest.mark.parametrize("reply", ["not json", "{}", '{"version":1,"projects":[]}'])
def test_bad_remote_evidence_cannot_fall_back_to_local_status(tmp_path, monkeypatch, reply):
    profile(tmp_path, True)
    monkeypatch.setattr("subprocess.run", lambda command, **kw: CompletedProcess(command, 0, reply, ""))
    with pytest.raises(RuntimeError, match="invalid evidence"):
        inspect_software()


def test_ssh_failure_is_an_error_and_not_an_empty_clean_directory(tmp_path, monkeypatch):
    profile(tmp_path, True)
    monkeypatch.setattr("subprocess.run", lambda command, **kw: CompletedProcess(command, 255, "", "failed"))
    with pytest.raises(RuntimeError, match="SSH software inspection failed"):
        inspect_software()


def test_git_status_is_read_only_and_reports_dirty_checkout(tmp_path, monkeypatch):
    root = tmp_path / "projects"
    (root / "science" / ".git").mkdir(parents=True)
    calls = []
    def git(command, **options):
        calls.append(command)
        assert options["env"]["GIT_OPTIONAL_LOCKS"] == "0"
        if "--is-bare-repository" in command:
            output = "false\n"
        elif "rev-parse" in command:
            output = "a" * 40 + "\n"
        elif "symbolic-ref" in command:
            output = "dev\n"
        else:
            output = " M science.py\n?? new.py\n"
        return CompletedProcess(command, 0, output, "")
    monkeypatch.setattr("subprocess.run", git)
    result = inspect_software_root(str(root))
    assert result["projects"][0]["dirty"] is True
    assert result["projects"][0]["branch"] == "dev"
    assert all(not {"fetch", "pull", "clone", "checkout", "install"} & set(command) for command in calls)


def test_failed_git_query_never_becomes_clean_and_other_projects_survive(tmp_path, monkeypatch):
    root = tmp_path / "projects"
    (root / "broken" / ".git").mkdir(parents=True)
    monkeypatch.setattr("subprocess.run", lambda command, **kw: CompletedProcess(command, 128, "", "bad repo"))
    result = inspect_software_root(str(root))
    assert result["projects"][0]["state"] == "unavailable"
    assert result["projects"][0]["dirty"] is None


def test_status_cannot_follow_a_project_symlink_outside_software_root(tmp_path):
    root, outside = tmp_path / "projects", tmp_path / "outside"
    root.mkdir()
    (outside / ".git").mkdir(parents=True)
    (root / "linked").symlink_to(outside, target_is_directory=True)
    assert inspect_software_root(str(root), "linked")["projects"][0]["state"] == "outside_root"


def test_environment_probe_reads_metadata_without_importing_scientific_packages(monkeypatch):
    class Distribution:
        version = "1.26.4"
        def locate_file(self, path): return Path("/env/site-packages")
        def read_text(self, path): return None
    monkeypatch.setattr("importlib.metadata.distribution", lambda name: Distribution())
    monkeypatch.setattr("subprocess.run", lambda *a, **kw: pytest.fail("Wheel metadata should need no process"))
    result = inspect_environment(["numpy"])
    assert result["packages"]["numpy"]["version"] == "1.26.4"
    assert result["prefix"]


def test_remote_environment_checks_use_profile_interpreter_and_report_mismatch(tmp_path, monkeypatch):
    config = profile(tmp_path, True)
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("numpy<2\n")
    expected = software_expectations(requirements=requirements)
    def ssh(command, **options):
        assert "/runtime/bin/python" in options["input"]
        assert "importlib.metadata" in options["input"]
        return CompletedProcess(command, 0, json.dumps({"version": 1, "software_root": config["software_root"],
            "state": "observed", "projects": [], "observed_at": "now", "truncated": False,
            "environment": {"state": "observed", "markers": {"python_version": "3.11"},
                            "packages": {"numpy": {"state": "installed", "version": "2.0"}}}}), "")
    monkeypatch.setattr("subprocess.run", ssh)
    assert inspect_software(expectations=expected)["compatibility"]["state"] == "potential_problem"


def test_missing_environment_never_silently_uses_system_python(tmp_path, monkeypatch):
    monkeypatch.setattr("subprocess.run", lambda *a, **kw: pytest.fail("Missing profile environment must not use another Python"))
    result = inspect_software_root(str(tmp_path), environment_script="should not run")
    assert result["environment"]["state"] == "unavailable"


def test_wrong_environment_interpreter_cannot_be_reported_as_compatible(tmp_path, monkeypatch):
    def wrong_environment(command, **options):
        assert command == ["/configured/env/bin/python", "-B", "-c", "probe"]
        return CompletedProcess(command, 0, json.dumps({"state": "observed", "prefix": "/wrong/env", "packages": {}, "markers": {}}), "")
    monkeypatch.setattr("subprocess.run", wrong_environment)
    result = inspect_software_root(str(tmp_path), python_path="/configured/env/bin/python", environment_script="probe")
    assert result["environment"]["state"] == "unavailable"
    assert "identity" in result["environment"]["error"]


def test_malformed_remote_rows_fail_without_claiming_a_clean_project(tmp_path, monkeypatch):
    config = profile(tmp_path, True)
    response = {"version": 1, "software_root": config["software_root"], "state": "observed",
                "observed_at": "now", "truncated": False, "projects": [{"state": "observed"}]}
    monkeypatch.setattr("subprocess.run", lambda command, **kw: CompletedProcess(command, 0, json.dumps(response), ""))
    with pytest.raises(RuntimeError, match="invalid evidence"):
        inspect_software()


def test_cli_reports_potential_problem_and_returns_nonzero(tmp_path, monkeypatch, capsys):
    root = profile(tmp_path)["software_root"]
    Path(root).mkdir()
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("numpy<2\n")
    monkeypatch.setattr("autoslurm.apps.software.inspect_software", lambda **kwargs: {
        "machine": "mock", "software_root": root, "state": "observed", "projects": [],
        "observed_at": "now", "truncated": False,
        "compatibility": {"state": "potential_problem", "checks": [
            {"name": "numpy", "state": "mismatch", "message": "Version mismatch", "requirement": "numpy<2", "installed": "2"}]}})
    with pytest.raises(SystemExit) as error:
        main(["status", "--requirements", str(requirements)])
    assert error.value.code == 1
    assert "potential_problem" in capsys.readouterr().out
