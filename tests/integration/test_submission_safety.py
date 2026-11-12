"""Submission failures exercised through the public client and real local driver."""

import copy
import json
from pathlib import Path
import shlex
import subprocess

import pytest

from autoslurm import (save_bundle, submit_jobs, SubmissionError, load_submission,
                      list_submissions, refresh_submission, execute_acp)
from autoslurm.bulk_submit_driver import BulkSubmitPayload, submit_payload
from autoslurm.storage import storage_root, slurm_dir
from autoslurm.utils import save_config
from autoslurm.submission import write_receipt


@pytest.fixture(autouse=True)
def mocked_shell_syntax(monkeypatch):
    # Shell syntax is exercised with real bash in test_job_environment.py.
    monkeypatch.setattr("autoslurm.job_runner.validate_slurm_content", lambda content: None)


def prepare(remote=None):
    config = {"env_command": "true", "slurm_account": "mock"}
    if remote:
        config.update(hostname="producing-host", storage_root=str(remote), venv_path="/prepared/env")
    save_config({"machines": {"mock": config}, "default_machine": "mock"})
    # Reverse definition order must not change prerequisites.
    definitions = {name: {"name": name, "script": "echo science", "slurm": {}, "dependencies": deps}
                   for name, deps in [("C", ["B"]), ("B", ["A"]), ("A", []), ("Z", ["C"])]}
    return save_bundle(definitions, "study")


@pytest.mark.parametrize("failure,expected", [("reject", "partial"), ("malformed", "uncertain"), ("interrupt", "uncertain")])
def test_local_partial_failure_keeps_first_id_and_blocks_descendants(monkeypatch, failure, expected):
    selected = prepare()
    original = selected.read_bytes()
    calls = []
    def fake_run(command, **kwargs):
        assert command[0] == "sbatch"
        name = Path(command[-1]).name.split("_")[0]
        calls.append(name)
        if name == "A":
            return subprocess.CompletedProcess(command, 0, "Submitted batch job 101\n", "")
        assert name == "B"
        receipt = list_submissions("study")[0]
        assert receipt["jobs"]["A"]["id"] == "101"  # Durable before B starts.
        assert "--dependency=afterok:101" in Path(command[-1]).read_text()
        if failure == "interrupt":
            raise KeyboardInterrupt()
        return subprocess.CompletedProcess(command, 1 if failure == "reject" else 0, "garbled", "account denied")
    monkeypatch.setattr("subprocess.run", fake_run)
    with pytest.raises(SubmissionError) as error:
        submit_jobs("study", bundle_path=selected)
    receipt = error.value.receipt
    assert receipt["state"] == expected
    assert calls == ["A", "B"]
    assert receipt["jobs"]["A"]["id"] == "101"
    assert receipt["jobs"]["B"]["state"] == ("rejected" if failure == "reject" else "uncertain")
    assert receipt["jobs"]["C"]["state"] == receipt["jobs"]["Z"]["state"] == "blocked"
    assert selected.read_bytes() == original
    assert load_submission(receipt["receipt_path"])["jobs"]["A"]["id"] == "101"
    snapshot = json.loads(Path(receipt["bundle_path"]).read_text())
    assert snapshot["A"]["id"] == "101"
    assert snapshot["B"]["_autoslurm_submission"]["error"]
    from datetime import datetime
    from autoslurm.experiment_context import job_context
    selected_date = datetime.strptime(Path(receipt["bundle_path"]).stem.rsplit("_", 1)[-1], "%Y%m%d%H%M%S")
    script_context = job_context("study", "A", selected_date, include_script=True, include_status=False)
    assert "echo science" in script_context
    assert "script missing" not in script_context
    with pytest.raises(ValueError, match="resubmit"):
        submit_jobs("study", bundle_path=receipt["bundle_path"])
    assert len(calls) == 2


@pytest.mark.parametrize("failure", ["partial", "lost-final", "lost-active"])
def test_remote_receipts_survive_response_loss_and_refresh_without_resubmission(tmp_path, monkeypatch, failure):
    remote = tmp_path / "remote state"
    (remote / "slurm").mkdir(parents=True)
    selected = prepare(remote)
    scheduler_calls = []
    dispatches = []
    commands = []
    def scheduler(command, **kwargs):
        name = Path(command[-1]).name.split("_")[0]
        scheduler_calls.append(name)
        if name == "B":
            assert command[command.index("--dependency") + 1] == "afterok:101"
            disk = json.loads(next((remote / "submissions").glob("*.json")).read_text())
            assert disk["jobs"]["A"]["id"] == "101"
            if failure == "partial":
                return subprocess.CompletedProcess(command, 1, "", "account denied")
            if failure == "lost-active":
                raise SystemExit()  # Helper disappears with B's outcome unrecorded.
        return subprocess.CompletedProcess(command, 0, str(101 + "ABCZ".index(name)), "")
    def transport(command, **kwargs):
        commands.append(command)
        if command[0] == "scp":
            for source in command[1:-1]:
                (remote / "slurm" / Path(source).name).write_bytes(Path(source).read_bytes())
        elif command[-1].startswith("bash -lc "):
            return subprocess.CompletedProcess(command, 0, str(remote) + "\n", "")
        elif "--capabilities" in command[-1]:
            return subprocess.CompletedProcess(command, 0, '{"submission_protocol": 1}', "")
        elif command[-1].startswith("cat -- "):
            assert "producing-host" in command
            return subprocess.CompletedProcess(command, 0, Path(shlex.split(command[-1])[-1]).read_text(), "")
        elif "autoslurm.apps.bulk_submit_driver" in command[-1]:
            payload = json.loads(kwargs["input"])
            dispatches.append(payload)
            try:
                result = submit_payload(BulkSubmitPayload(**payload), run_command=scheduler)
                response = {"ok": True, "receipt": result.receipt}
                code = 0
            except SubmissionError as exc:
                response = {"ok": False, "receipt": exc.receipt, "error": str(exc)}
                code = 1
            except SystemExit:
                return subprocess.CompletedProcess(command, 255, "", "connection lost")
            if failure == "lost-final":
                return subprocess.CompletedProcess(command, 255, "", "connection lost")
            return subprocess.CompletedProcess(command, code, json.dumps(response), "")
        return subprocess.CompletedProcess(command, 0, "", "")
    monkeypatch.setattr("subprocess.run", transport)
    with pytest.raises(SubmissionError) as error:
        submit_jobs("study", bundle_path=selected)
    receipt = error.value.receipt
    assert receipt["state"] == ("partial" if failure == "partial" else "uncertain")
    if failure != "partial":
        assert all(job["state"] == "uncertain" for job in receipt["jobs"].values())
    assert len(dispatches) == 1
    # Remove the producing profile: exact refresh must still use saved transport.
    save_config({"machines": {"elsewhere": {"env_command": "true", "slurm_account": "mock"}}, "default_machine": "elsewhere"})
    before = list(scheduler_calls)
    refreshed = refresh_submission(receipt["receipt_path"])
    assert scheduler_calls == before
    assert len(dispatches) == 1
    assert refreshed["jobs"]["A"]["id"] == "101"
    if failure == "lost-active":
        assert refreshed["state"] == "uncertain"
        assert refreshed["jobs"]["B"]["state"] == refreshed["jobs"]["C"]["state"] == "uncertain"
        assert not refreshed["execution_finished"]
    else:
        assert refreshed["state"] == ("partial" if failure == "partial" else "submitted")
    # The execution identity cannot be invoked a second time.
    with pytest.raises(FileExistsError):
        submit_payload(BulkSubmitPayload(**dispatches[0]), run_command=scheduler)
    assert scheduler_calls == before
    # Agent and terminal callers read the very same evidence.
    assert execute_acp({"action": "inspect_submission", "receipt_path": receipt["receipt_path"]})["result"] == refreshed


@pytest.mark.parametrize("problem", ["missing-dependency", "cycle", "missing-command", "invalid-environment"])
def test_invalid_later_job_stops_before_any_scheduler_effect(problem, monkeypatch):
    selected = prepare()
    data = json.loads(selected.read_text())
    if problem == "missing-dependency":
        data["Z"]["dependencies"] = ["absent"]
    elif problem == "cycle":
        data["A"]["dependencies"] = ["Z"]
    elif problem == "missing-command":
        data["Z"]["script"] = ""
    else:
        data["Z"]["runtime_environment"] = {"OMP_NUM_THREADS": "$(run something)"}
    selected.write_text(json.dumps(data))
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: pytest.fail("Invalid graph reached an external command"))
    with pytest.raises((ValueError, KeyError)):
        submit_jobs("study", bundle_path=selected)
    assert not list_submissions()
    assert not list(slurm_dir().glob("*.sh"))


def test_receipt_write_failure_after_acceptance_preserves_in_memory_id_and_stops(monkeypatch):
    from autoslurm import bulk_submit_driver as driver
    selected = prepare()
    real_write = driver.write_receipt
    accepted = []
    def failing_write(path, receipt):
        if receipt["jobs"]["A"].get("id"):
            raise OSError("disk full")
        real_write(path, receipt)
    def scheduler(command, **kwargs):
        accepted.append(command)
        return subprocess.CompletedProcess(command, 0, "Submitted batch job 101", "")
    monkeypatch.setattr(driver, "write_receipt", failing_write)
    monkeypatch.setattr("subprocess.run", scheduler)
    with pytest.raises(SubmissionError) as error:
        submit_jobs("study", bundle_path=selected)
    assert len(accepted) == 1
    assert error.value.receipt["jobs"]["A"]["id"] == "101"
    assert load_submission(error.value.receipt["receipt_path"])["jobs"]["A"]["id"] == "101"


def test_receipt_inspection_and_cleanup_preserve_uncertain_records(monkeypatch, capsys):
    from autoslurm.apps import submission, clean
    selected = prepare()
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: (_ for _ in ()).throw(TimeoutError("no response")))
    with pytest.raises(SubmissionError) as error:
        submit_jobs("study", bundle_path=selected)
    receipt = error.value.receipt
    submission.main([receipt["receipt_path"], "--json"])
    capsys.readouterr()
    # No accepted ID exists, but this is not a fresh draft to delete or submit.
    clean.main(["--scope", "unsubmitted", "--yes"])
    assert Path(receipt["bundle_path"]).exists()
    assert load_submission(receipt["receipt_path"])["state"] == "uncertain"


@pytest.mark.parametrize("reject_first", [False, True])
def test_same_level_partial_ids_and_unrelated_not_submitted(monkeypatch, reject_first):
    selected = prepare()
    data = json.loads(selected.read_text())
    data["B"]["dependencies"] = []
    data["C"]["dependencies"] = ["A", "B"]
    data["Z"]["dependencies"] = []
    selected.write_text(json.dumps(data))
    calls = []
    def scheduler(command, **kwargs):
        name = Path(command[-1]).name.split("_")[0]
        calls.append(name)
        rejected = name == ("A" if reject_first else "B")
        return subprocess.CompletedProcess(command, 1 if rejected else 0, "Submitted batch job 101" if not rejected else "", "quota")
    monkeypatch.setattr("subprocess.run", scheduler)
    with pytest.raises(SubmissionError) as error:
        submit_jobs("study", bundle_path=selected)
    receipt = error.value.receipt
    assert receipt["state"] == ("rejected" if reject_first else "partial")
    assert calls == (["A"] if reject_first else ["A", "B"])
    assert receipt["jobs"]["C"]["state"] == "blocked"
    assert receipt["jobs"]["Z"]["state"] == "not_submitted"


@pytest.mark.parametrize("problem", ["old-helper", "missing-venv"])
def test_incompatible_helper_stops_before_dispatch(problem, monkeypatch):
    selected = prepare()
    config = {"hostname": "producing-host", "path": "/remote/state", "env_command": "true", "slurm_account": "mock"}
    if problem != "missing-venv":
        config["venv_path"] = "/prepared/env"
    save_config({"machines": {"mock": config}, "default_machine": "mock"})
    calls = []
    def only_capability(command, **kwargs):
        calls.append(command)
        assert "--capabilities" in command[-1]
        return subprocess.CompletedProcess(command, 0, '{"submission_protocol": 0}', "")
    monkeypatch.setattr("subprocess.run", only_capability)
    with pytest.raises(RuntimeError, match="helper|venv_path"):
        submit_jobs("study", bundle_path=selected)
    assert len(calls) == (0 if problem == "missing-venv" else 1)
    assert not list_submissions()
    assert not list(slurm_dir().glob("*.sh"))


@pytest.mark.parametrize("fault", ["missing", "changed-id", "different-submission", "changed-path"])
def test_refresh_error_preserves_known_ids_and_returns_evidence_to_agent(tmp_path, monkeypatch, fault):
    selected = prepare()
    monkeypatch.setattr("subprocess.run", lambda command, **kwargs: subprocess.CompletedProcess(command, 0, "Submitted batch job 101", ""))
    receipt = submit_jobs("study", bundle_path=selected)
    receipt["execution"]["is_remote"] = True
    receipt["execution"]["transport"] = {"hostname": "producing-host"}
    write_receipt(receipt["receipt_path"], receipt)
    observed = copy.deepcopy(receipt)
    if fault == "changed-id":
        observed["jobs"]["A"]["id"] = "999"
    elif fault == "different-submission":
        observed["submission_id"] = "0" * 32
    elif fault == "changed-path":
        observed["bundle_path"] = str(tmp_path / "wrong-snapshot.json")
    monkeypatch.setattr("subprocess.run", lambda command, **kwargs: subprocess.CompletedProcess(command, 255 if fault == "missing" else 0, json.dumps(observed), "connection refused"))
    outcome = execute_acp({"action": "inspect_submission", "receipt_path": receipt["receipt_path"], "refresh": True})
    assert outcome["status"] == "error"
    assert outcome["result"]["state"] == "submitted"
    assert outcome["result"]["jobs"]["A"]["id"] == "101"
    assert outcome["result"]["observation_error"]
    assert load_submission(receipt["receipt_path"])["jobs"]["A"]["id"] == "101"
