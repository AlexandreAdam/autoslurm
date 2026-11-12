import json
import os
from pathlib import Path
import shutil
import shlex
import subprocess

import pytest

from autoslurm import preview_bundle, save_bundle, submit_jobs, list_saved_bundles, load_bundle_from_path
from autoslurm import resolve_results_path, path_exists, recorded_execution
from autoslurm.storage import storage_root, slurm_dir
from autoslurm.utils import save_config
from tests.integration.test_reference_client import science_client, EXAMPLE
from tests.submission_helpers import accepted_receipt


@pytest.mark.local_processes
@pytest.mark.parametrize("profile", ["workstation", "other-machine"])
def test_relative_science_under_two_profiles_from_unrelated_directory(profile, tmp_path, monkeypatch, science_client):
    project = tmp_path / profile / "project with spaces"
    (project / "data").mkdir(parents=True)
    shutil.copyfile(EXAMPLE / "data/measurements.json", project / "data/measurements.json")
    results = tmp_path / profile / "results with spaces"
    activation = "true" if profile == "workstation" else "cd " + shlex.quote(str(tmp_path))
    save_config({"machines": {profile: {"project_root": str(project), "results_root": str(results), "env_command": activation, "slurm_account": "mock"}}, "default_machine": profile})
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    monkeypatch.chdir(unrelated)
    definitions = json.loads((EXAMPLE / "bundles/array.json").read_text())
    original = json.loads(json.dumps(definitions))
    selected = save_bundle(definitions, "study")
    before = selected.read_bytes()
    preview = preview_bundle(selected, machine=profile)
    assert not list(slurm_dir().glob("*.sh"))
    real_run = subprocess.run
    calls = []

    def mock_scheduler(command, **kwargs):
        if command[0] == "bash":
            return real_run(command, **kwargs)
        if command[0] == "test":
            return subprocess.CompletedProcess(command, 0 if Path(command[-1]).exists() else 1, "", "")
        assert command[0] == "sbatch", command
        script = Path(command[-1])
        job_name = "reduce" if "--job-name=reduce\n" in script.read_text() else "shards"
        job_id = str(101 + len(calls))
        if job_name == "reduce":
            assert command[command.index("--dependency") + 1] == "afterok:101"
        for index in range(4) if job_name == "shards" else [None]:
            env = dict(os.environ)
            if index is not None:
                env["SLURM_ARRAY_TASK_ID"] = str(index)
            executed = real_run(["bash", "-c", 'source "$1"; result=$?; pwd; exit "$result"', "--", str(script)], cwd=unrelated, env=env, capture_output=True, text=True)
            assert executed.returncode == 0, executed.stderr
            assert executed.stdout.strip() == str(project)
        calls.append(job_name)
        return subprocess.CompletedProcess(command, 0, f"Submitted batch job {job_id}\n", "")

    monkeypatch.setattr("subprocess.run", mock_scheduler)
    submit_jobs("study", machine=profile, bundle_path=selected)
    assert selected.read_bytes() == before
    assert calls == ["shards", "reduce"]
    records = []
    for entry in list_saved_bundles(bundle_name="study"):
        jobs, _, _ = load_bundle_from_path(entry["path"])
        if any(job.get("id") for job in jobs):
            records.append((entry["path"], jobs))
    assert len(records) == 1
    submission, jobs = records[0]
    for job in jobs:
        evidence = recorded_execution(submission, job["name"])
        assert evidence["resolved_paths"] == preview["jobs"][job["name"]]["resolved_paths"]
        assert evidence["working_directory"] == str(project)
        assert evidence["logical_paths"]["input_file"] == "data/measurements.json"
        assert job["script_args"] == original[job["name"]]["script_args"]
    result = results / "reference-array/summary/summary.json"
    assert json.loads(result.read_text())["sum_squares"] == 30
    # A renamed profile/root must not redirect artifacts from an old submission.
    save_config({"machines": {profile: {"project_root": str(unrelated), "results_root": str(tmp_path / "replacement"), "env_command": "true", "slurm_account": "mock"}}, "default_machine": profile})
    relative = "reference-array/summary/summary.json"
    assert resolve_results_path(relative, bundle_path=submission, job_name="reduce") == str(result)
    assert path_exists(relative, bundle_path=submission, job_name="reduce")
    assert resolve_results_path(relative, machine_name=profile) != str(result)


@pytest.mark.parametrize("problem", ["missing-root", "missing-input", "missing-project-setting", "absolute-input", "traversal", "missing-working-directory"])
def test_invalid_project_paths_stop_before_submission(problem, tmp_path, monkeypatch):
    project = tmp_path / "project"
    (project / "data").mkdir(parents=True)
    (project / "data/input.json").write_text("[1]")
    config = {"project_root": str(project), "slurm_account": "mock", "env_command": "true"}
    job = {"name": "sample", "script": "science-demo", "input_args": ["input_file"], "script_args": {"input_file": "data/input.json", "output_dir": "study"}, "slurm": {}}
    if problem == "missing-root":
        config["project_root"] = str(tmp_path / "missing")
    elif problem == "missing-input":
        job["script_args"]["input_file"] = "data/missing.json"
    elif problem == "missing-project-setting":
        config.pop("project_root")
    elif problem == "absolute-input":
        job["script_args"]["input_file"] = str(project / "data/input.json")
    elif problem == "traversal":
        job["script_args"]["input_file"] = "../outside.json"
    else:
        job["working_directory"] = "missing-directory"
    save_config({"machines": {"mock": config}, "default_machine": "mock"})
    selected = save_bundle({"sample": job}, "invalid")
    before = selected.read_bytes()
    def no_effects(*args, **kwargs):
        pytest.fail("Invalid paths reached an external command")
    monkeypatch.setattr("subprocess.run", no_effects)
    for operation in [lambda: preview_bundle(selected, machine="mock"), lambda: submit_jobs("invalid", machine="mock", bundle_path=selected)]:
        with pytest.raises((ValueError, FileNotFoundError), match="unavailable|project_root|relative|traverse"):
            operation()
    assert selected.read_bytes() == before
    assert not list(slurm_dir().iterdir())


@pytest.mark.parametrize("missing_input", [False, True])
def test_remote_operation_discovers_root_once_and_batches_input_validation(tmp_path, monkeypatch, missing_input):
    config = {"hostname": "mock-host", "storage_root": "/remote/development", "project_root": "/remote/project", "venv_path": "/remote/env", "slurm_account": "mock"}
    save_config({"machines": {"remote": config}, "default_machine": "remote"})
    definitions = json.loads((EXAMPLE / "bundles/array.json").read_text())
    selected = save_bundle(definitions, "remote-study")
    calls = []
    def fake_remote(command, **kwargs):
        if command[0] == "bash":
            return subprocess.CompletedProcess(command, 0, "", "")
        calls.append(command)
        if command[0] == "ssh" and command[-1].startswith("bash -lc "):
            return subprocess.CompletedProcess(command, 0, "/remote/development\n", "")
        if command[0] == "ssh" and command[-1].startswith("test ") and missing_input:
            return subprocess.CompletedProcess(command, 1, "", "Required input input_file is unavailable: /remote/project/data/measurements.json")
        if command[0] == "ssh" and "autoslurm.apps.bulk_submit_driver" in command[-1]:
            if "--capabilities" in command[-1]:
                return subprocess.CompletedProcess(command, 0, '{"submission_protocol": 1}', "")
            payload = json.loads(kwargs["input"])
            assert payload["slurm_dir"] == "/remote/development/slurm"
            return subprocess.CompletedProcess(command, 0, json.dumps({"ok": True, "receipt": accepted_receipt(payload, {"shards": "201", "reduce": "202"})}), "")
        assert command[0] in {"ssh", "scp"}
        return subprocess.CompletedProcess(command, 0, "", "")
    monkeypatch.setattr("subprocess.run", fake_remote)
    if missing_input:
        with pytest.raises(FileNotFoundError, match="Required input input_file is unavailable"):
            submit_jobs("remote-study", machine="remote", bundle_path=selected)
        assert not list(slurm_dir().glob("*.sh"))
        assert all(c[0] == "ssh" for c in calls)
        assert not any("autoslurm.apps.bulk_submit_driver" in c[-1] for c in calls)
    else:
        submit_jobs("remote-study", machine="remote", bundle_path=selected)
    probes = [c for c in calls if c[0] == "ssh" and c[-1].startswith("bash -lc ")]
    inputs = [c for c in calls if c[0] == "ssh" and c[-1].startswith("test ")]
    assert len(probes) == 1
    assert len(inputs) == 1
    assert "/remote/project/data/measurements.json" in inputs[0][-1]


@pytest.mark.local_processes
def test_failed_environment_activation_does_not_run_application(tmp_path):
    from datetime import datetime
    from autoslurm.job_to_slurm import create_slurm_script
    script = create_slurm_script(
        {"name": "environment-check", "script": "echo must-not-run", "slurm": {}},
        datetime(2026, 1, 1), {"project_root": str(tmp_path), "env_command": "false"},
    )
    result = subprocess.run(["bash", str(slurm_dir() / script)], capture_output=True, text=True)
    assert result.returncode == 1
    assert "must-not-run" not in result.stdout
    assert "environment activation failed" in result.stderr
