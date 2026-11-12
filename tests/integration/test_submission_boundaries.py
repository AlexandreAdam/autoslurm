"""Public workflow regressions for shared preparation and explicit dispatch phases."""

import json
from pathlib import Path
import subprocess

import pytest

from autoslurm import preview_bundle, save_bundle, submit_jobs
from autoslurm.storage import slurm_dir, storage_root
from autoslurm.utils import save_config


@pytest.fixture
def local_profile():
    save_config({"machines": {"mock": {"env_command": "true", "slurm_account": "mock"}},
                 "default_machine": "mock"})


def test_software_opt_in_cannot_fall_back_to_operator_runtime(local_profile, monkeypatch):
    from autoslurm import attach_software_manifest, load_bundle_from_path
    software = {"projects": [{"name": "science", "repository": "https://example.invalid/science.git"}]}
    selected = save_bundle(attach_software_manifest({"science": {"script": "science", "slurm": {}}}, software), "study")
    assert load_bundle_from_path(selected)[0][0]["software"]["projects"][0]["revision"] is None
    before = selected.read_bytes()
    monkeypatch.setattr("subprocess.run", lambda *a, **k: pytest.fail("Managed request ran an external command"))
    for operation in (lambda: preview_bundle(selected), lambda: submit_jobs("study", bundle_path=selected)):
        with pytest.raises(ValueError, match="runtime readiness"):
            operation()
    assert selected.read_bytes() == before
    assert not list(slurm_dir().glob("*.sh"))
    assert not list((storage_root() / "submissions").glob("*.json"))


@pytest.mark.parametrize("problem", ["empty", "missing-command", "invalid-name", "already-submitted"])
def test_preview_and_submission_reject_the_same_invalid_definition(problem, local_profile, monkeypatch):
    jobs = {"sample": {"name": "sample", "script": "echo science", "slurm": {}}}
    if problem == "empty":
        jobs = {}
    elif problem == "missing-command":
        jobs["sample"]["script"] = ""
    elif problem == "invalid-name":
        jobs = {"bad/name": {"name": "bad/name", "script": "echo science", "slurm": {}}}
    else:
        jobs["sample"]["id"] = "101"
    path = save_bundle(jobs, "study")
    before = path.read_bytes()
    def shell_check_only(command, **kwargs):
        assert command == ["bash", "-n"]
        return subprocess.CompletedProcess(command, 0, "", "")
    monkeypatch.setattr("subprocess.run", shell_check_only)
    for operation in (lambda: preview_bundle(path), lambda: submit_jobs("study", bundle_path=path)):
        with pytest.raises(ValueError):
            operation()
        assert path.read_bytes() == before
        assert not list(slurm_dir().glob("*.sh"))
        assert not list((storage_root() / "submissions").glob("*.json"))


def test_dispatch_uses_exact_preview_scripts_and_prepared_execution_paths(local_profile, monkeypatch):
    jobs = {
        "A": {"name": "A", "script": "echo first", "slurm": {}, "script_args": {"output_dir": "study/A"}},
        "B": {"name": "B", "script": "echo second", "slurm": {}, "dependencies": ["A"]},
    }
    selected = save_bundle(jobs, "study")
    before = selected.read_bytes()
    checked = []
    submitted = {}
    commands = []
    def scheduler(command, **kwargs):
        if command == ["bash", "-n"]:
            checked.append(kwargs["input"])
            return subprocess.CompletedProcess(command, 0, "", "")
        assert command[0] == "sbatch"
        commands.append(command)
        path = Path(command[-1])
        name = path.name.split("_")[0]
        submitted[name] = (path, path.read_text())
        assert submitted[name][1] in checked
        if name == "B":
            assert command[command.index("--dependency") + 1] == "afterok:101"
        return subprocess.CompletedProcess(command, 0, f"Submitted batch job {100 + len(commands)}", "")
    monkeypatch.setattr("subprocess.run", scheduler)
    preview = preview_bundle(selected)
    receipt = submit_jobs("study", bundle_path=selected)
    snapshot = json.loads(Path(receipt["bundle_path"]).read_text())
    for name, (path, text) in submitted.items():
        assert text == preview["jobs"][name]["script"] == path.read_text()
        assert "#SBATCH --dependency" not in text
        assert snapshot[name]["_autoslurm_execution"] == {key: value for key, value in preview["jobs"][name].items() if key != "script"}
    assert selected.read_bytes() == before
    assert [command[0] for command in commands] == ["sbatch", "sbatch"]


@pytest.mark.parametrize("failure", ["initial-receipt", "script-staging"])
def test_record_or_staging_failure_carries_evidence_without_dispatch(failure, local_profile, monkeypatch):
    from autoslurm import SubmissionError
    from autoslurm import submission_operation
    selected = save_bundle({"sample": {"script": "echo science", "slurm": {}}}, "study")
    monkeypatch.setattr("autoslurm.bundle_preparation.validate_slurm_content", lambda content: None)
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: pytest.fail("Failed preparation dispatched work"))
    if failure == "initial-receipt":
        def storage_failure(*args, **kwargs):
            raise OSError("receipt disk full")
        monkeypatch.setattr(submission_operation, "write_receipt", storage_failure)
    else:
        real_write = Path.write_text
        def script_failure(path, *args, **kwargs):
            if path.parent == slurm_dir():
                raise OSError("script disk full")
            return real_write(path, *args, **kwargs)
        monkeypatch.setattr(Path, "write_text", script_failure)
    with pytest.raises(SubmissionError) as error:
        submit_jobs("study", bundle_path=selected)
    receipt = error.value.receipt
    assert receipt["state"] == "rejected" and receipt["execution_finished"]
    assert receipt["jobs"]["sample"]["state"] == "not_submitted"
    assert Path(receipt["bundle_path"]).exists()
    assert "disk full" in receipt["error"]
    if failure == "initial-receipt":
        assert "tracking_error" in receipt


@pytest.mark.parametrize("failure", ["transfer", "session-open", "lost-response", "session-close", "final-tracking", "final-tracking-interrupt"])
def test_remote_dispatch_phase_preserves_known_acceptance(failure, monkeypatch):
    from contextlib import contextmanager
    from autoslurm import SubmissionError, load_submission
    from autoslurm.execution import resolve_execution_context
    from autoslurm import submission_operation
    from tests.submission_helpers import accepted_receipt
    selected = save_bundle({"sample": {"script": "echo science", "slurm": {}}}, "study")
    context = resolve_execution_context("remote", {"hostname": "cluster", "path": "/remote/state", "venv_path": "/prepared"})
    monkeypatch.setattr("autoslurm.bundle_preparation.validate_slurm_content", lambda content: None)
    monkeypatch.setattr("autoslurm.job_runner.probe_submission_helper", lambda context: None)
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: pytest.fail("Unexpected unmocked dispatch adapter"))
    def transfer(*args, **kwargs):
        if failure == "transfer":
            raise OSError("transfer failed")
    @contextmanager
    def session(*args, **kwargs):
        if failure == "session-open":
            raise OSError("session failed")
        yield None
        if failure == "session-close":
            raise OSError("cleanup failed")
    dispatches = []
    def dispatch(payload, **kwargs):
        dispatches.append(payload)
        if failure == "lost-response":
            raise OSError("connection lost")
        return accepted_receipt(payload, {"sample": "101"})
    monkeypatch.setattr(submission_operation, "transfer_slurms_to_remote", transfer)
    monkeypatch.setattr(submission_operation, "ssh_submission_session", session)
    monkeypatch.setattr(submission_operation, "run_bulk_submit_driver_remotely", dispatch)
    if failure.startswith("final-tracking"):
        def no_projection(receipt):
            error = KeyboardInterrupt if failure.endswith("interrupt") else OSError
            raise error("tracking mirror failed")
        monkeypatch.setattr(submission_operation, "project_receipt", no_projection)
    with pytest.raises(SubmissionError) as error:
        submit_jobs("study", bundle_path=selected, context=context)
    receipt = error.value.receipt
    assert len(dispatches) == (0 if failure in {"transfer", "session-open"} else 1)
    if failure == "session-close" or failure.startswith("final-tracking"):
        assert receipt["state"] == "submitted" and receipt["execution_finished"]
        assert receipt["jobs"]["sample"]["id"] == "101"
        assert load_submission(receipt["receipt_path"])["jobs"]["sample"]["id"] == "101"
    elif failure == "lost-response":
        assert receipt["state"] == "uncertain"
        assert receipt["jobs"]["sample"]["state"] == "uncertain"
    else:
        assert receipt["state"] == "rejected"
        assert receipt["jobs"]["sample"]["state"] == "not_submitted"
