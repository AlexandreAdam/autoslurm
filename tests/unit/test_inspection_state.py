"""Projection and producing-path selection require data, not runtime access."""

import copy
from pathlib import Path

from autoslurm.execution import producing_machine
from autoslurm.inspection_state import resolve_jobs
from autoslurm.log_files import select_log_references


def test_projection_and_reference_selection_have_no_io_or_input_mutation(monkeypatch):
    jobs = [{"name": "array", "id": "101", "machine": "mock", "slurm": {"array": "0,2,4"}}]
    profiles = {"mock": {"env_command": "true"}}
    key, _ = producing_machine(jobs[0], profiles)
    observation = {"observed_at": "2026-11-12T00:00:00+00:00", "errors": [{"source": "queue", "message": "queue unavailable"}],
                   "records": {"101_0": {"state": "COMPLETED", "raw_id": "9000", "source": "accounting", "exit_code": "0:0"},
                               "101_2": {"state": "FAILED", "raw_id": "9002", "source": "accounting", "reason": "NonZeroExitCode", "exit_code": "1:0"}}}
    observations = {key: observation}
    original = copy.deepcopy((jobs, profiles, observations))
    def no_io(*args, **kwargs):
        raise AssertionError("Projection/selection performed I/O")
    monkeypatch.setattr(Path, "open", no_io)
    monkeypatch.setattr("subprocess.run", no_io)
    monkeypatch.setattr("autoslurm.inspection_collection.load_config", no_io)
    resolved = resolve_jobs(jobs, observations, profiles=profiles)
    assert [task["state"] for task in resolved[0]["tasks"]] == ["COMPLETED", "FAILED", "UNKNOWN"]
    assert resolved[0]["counts"]["unknown"] == 1
    refs = select_log_references(jobs, resolved, profiles=profiles, root=Path("/evidence"), task_index=2)
    assert refs[0]["paths"] == ["/evidence/out/array-9002.out", "/evidence/out/array-101_2.out", "/evidence/out/array-101.2.out"]
    assert (jobs, profiles, observations) == original
    resolved[0]["errors"][0]["message"] = "caller edit"
    assert observations[key]["errors"][0]["message"] == "queue unavailable"


def test_projection_with_empty_evidence_never_collects_it(monkeypatch):
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Unexpected query")))
    result = resolve_jobs([{"name": "sample", "id": "101", "slurm": {}}], {})
    assert result[0]["state"] == "UNKNOWN"
    assert result[0]["observed_at"] is None
