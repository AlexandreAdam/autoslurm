"""Cleanup eligibility uses task evidence and preserves uncertain submissions."""
import json
import subprocess
from pathlib import Path

import pytest

from autoslurm import save_bundle, submit_jobs
from autoslurm.apps import clean
from autoslurm.storage import jobs_dir
from autoslurm.utils import save_config


def snapshot(name="run", identities=("101",), array=None):
    path = jobs_dir() / f"{name}_20260101000000.json"
    path.write_text(json.dumps({f"job{i}": {"name": f"job{i}", "script": "echo test", "id": identity,
        "slurm": {"array": array} if array else {}} for i, identity in enumerate(identities)}))
    return path


def scheduler(monkeypatch, states, errors=None):
    calls = []
    def query(ids, *args):
        calls.append(ids)
        return {"observed_at": "2026-11-23T12:00:00+00:00", "errors": errors or [],
                "records": {identity: {"state": state, "source": "accounting"}
                            for identity, state in states.items()}}
    monkeypatch.setattr("autoslurm.inspection_collection.query_scheduler", query)
    return calls


@pytest.mark.parametrize("scope,states,expected", [
    ("completed", {"101": "COMPLETED"}, True),
    ("completed", {"101": "FAILED"}, False),
    ("completed", {"101": "RUNNING"}, False),
    ("completed", {}, False),
    ("terminal", {"101": "COMPLETED", "102": "FAILED"}, True),
    ("terminal", {"101": "COMPLETED", "102": "CANCELLED"}, True),
    ("terminal", {"101": "FAILED", "102": "PENDING"}, False),
    ("all", {"101": "COMPLETED"}, True),
    ("all", {"101": "RUNNING"}, False),
])
def test_scopes_use_live_task_evidence(monkeypatch, capsys, scope, states, expected):
    identities = ("101", "102") if "102" in states else ("101",)
    path = snapshot(identities=identities)
    scheduler(monkeypatch, states)
    clean.main(["--scope", scope])
    preview = capsys.readouterr().out
    assert path.exists()
    assert (str(path) in preview) == expected
    clean.main(["--scope", scope, "--yes"])
    assert path.exists() != expected


@pytest.mark.parametrize("scope", ["failed", "cancelled", "terminal", "all", "completed"])
@pytest.mark.parametrize("second", ["RUNNING", "UNKNOWN", None])
def test_array_failure_never_hides_live_or_missing_tasks(monkeypatch, scope, second):
    path = snapshot(array="0-1")
    states = {"101": "FAILED", "101_0": "FAILED"}
    if second:
        states["101_1"] = second
    scheduler(monkeypatch, states)
    clean.main(["--scope", scope, "--yes"])
    assert path.exists()


def test_complete_array_and_unsubmitted_job_policies(monkeypatch):
    array = snapshot("array", array="0-1")
    partial = snapshot("legacy-partial", identities=("101", None))
    scheduler(monkeypatch, {"101": "COMPLETED", "101_0": "COMPLETED", "101_1": "COMPLETED"})
    clean.main(["--scope", "completed", "--yes"])
    assert not array.exists()
    assert partial.exists()  # Success means every declared job completed.
    clean.main(["--scope", "terminal", "--yes"])
    assert not partial.exists()  # Legacy terminal scope concerns submitted work.


def test_failed_observation_cannot_authorize_deletion(monkeypatch):
    path = snapshot()
    scheduler(monkeypatch, {"101": "COMPLETED"}, [{"source": "queue", "message": "SSH failed"}])
    clean.main(["--scope", "completed", "--yes"])
    assert path.exists()


def tracked(monkeypatch):
    save_config({"machines": {"mock": {"env_command": "true"}}, "default_machine": "mock"})
    monkeypatch.setattr("autoslurm.bundle_preparation.validate_slurm_content", lambda content: None)
    draft = save_bundle({"job": {"name": "job", "script": "echo test", "slurm": {}}}, "tracked")
    monkeypatch.setattr("subprocess.run", lambda command, **kwargs:
                        subprocess.CompletedProcess(command, 0, "Submitted batch job 101\n", ""))
    receipt = submit_jobs("tracked", bundle_path=draft)
    return Path(receipt["bundle_path"]), Path(receipt["receipt_path"])


@pytest.mark.parametrize("scope", ["completed", "terminal", "failed", "cancelled", "all"])
def test_settled_tracked_jobs_can_be_cleaned_without_deleting_receipts(monkeypatch, scope):
    path, receipt = tracked(monkeypatch)
    evidence = receipt.read_bytes()
    state = {"failed": "FAILED", "cancelled": "CANCELLED"}.get(scope, "COMPLETED")
    scheduler(monkeypatch, {"101": state})
    clean.main(["--scope", scope, "--yes"])
    assert not path.exists()
    assert receipt.read_bytes() == evidence


@pytest.mark.parametrize("receipt_state", ["uncertain", "submitting", "partial"])
def test_unsettled_dispatch_retained_even_if_known_ids_finished(monkeypatch, receipt_state):
    path, receipt = tracked(monkeypatch)
    data = json.loads(receipt.read_text())
    data["state"] = receipt_state
    data["execution_finished"] = False
    receipt.write_text(json.dumps(data))
    calls = scheduler(monkeypatch, {"101": "COMPLETED"})
    clean.main(["--scope", "all", "--yes"])
    assert path.exists()
    assert calls == []


def test_receipt_failure_retains_tracking(monkeypatch):
    path, receipt = tracked(monkeypatch)
    receipt.write_text("broken")
    scheduler(monkeypatch, {"101": "COMPLETED"})
    clean.main(["--scope", "terminal", "--yes"])
    assert path.exists()


def test_changed_snapshot_retained(monkeypatch, capsys):
    path = snapshot()
    scheduler(monkeypatch, {"101": "COMPLETED"})
    original = clean._render_table
    def changed(rows):
        path.write_text(path.read_text() + "\n")
        return original(rows)
    monkeypatch.setattr(clean, "_render_table", changed)
    clean.main(["--scope", "completed", "--yes"])
    assert path.exists()
    assert "Retained changed evidence" in capsys.readouterr().out


def test_draft_cleanup_never_queries_scheduler(monkeypatch):
    snapshot(identities=(None,))
    def forbidden(*args):
        pytest.fail("Draft cleanup must not query the scheduler")
    monkeypatch.setattr(clean, "observe_job_statuses", forbidden)
    clean.main(["--scope", "unsubmitted"])


@pytest.mark.parametrize("state,removed", [("COMPLETED", True), ("RUNNING", False)])
def test_scope_constrains_explicit_index(monkeypatch, state, removed):
    path, _ = tracked(monkeypatch)
    scheduler(monkeypatch, {"101": state})
    clean.main(["1", "--scope", "completed", "--yes"])
    assert path.exists() != removed


def test_cancelled_parent_is_not_a_successful_array(monkeypatch):
    path = snapshot(array="0-1")
    scheduler(monkeypatch, {"101": "CANCELLED", "101_0": "COMPLETED", "101_1": "COMPLETED"})
    clean.main(["--scope", "completed", "--yes"])
    assert path.exists()


def test_all_scope_includes_explicit_draft(monkeypatch):
    path = snapshot(identities=(None,))
    clean.main(["1", "--scope", "all", "--yes"])
    assert not path.exists()
