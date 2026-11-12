import copy
import json
from pathlib import Path
import subprocess

from autoslurm.storage import jobs_dir


def saved_run(name="study", date="20250101000000", jobs=None):
    jobs = copy.deepcopy(jobs or {"sample": {"id": "101", "script": "echo science", "slurm": {}}})
    for key, job in jobs.items():
        job.setdefault("name", key)
        job.setdefault("script", "echo science")
        job.setdefault("slurm", {})
        job.setdefault("_autoslurm_snapshot_kind", "submission" if job.get("id") else "draft")
    path = jobs_dir() / f"{name}_{date}.json"
    path.write_text(json.dumps(jobs))
    return path


def remote_observation(queue="", accounting="", queue_code=0, accounting_code=0):
    return f"__AUTOSLURM_QUERY_0__\n{queue}\n__AUTOSLURM_EXIT__{queue_code}\n__AUTOSLURM_QUERY_1__\n{accounting}\n__AUTOSLURM_EXIT__{accounting_code}\n"


def mock_scheduler(monkeypatch, *, queue="", accounting="", queue_code=0, accounting_code=0):
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        if command[0] == "squeue":
            return subprocess.CompletedProcess(command, queue_code, queue, "queue unavailable" if queue_code else "")
        if command[0] == "sacct":
            return subprocess.CompletedProcess(command, accounting_code, accounting, "accounting unavailable" if accounting_code else "")
        if command[0] == "ssh":
            return subprocess.CompletedProcess(command, 0, remote_observation(queue, accounting, queue_code, accounting_code), "")
        raise AssertionError(f"Unexpected command: {command}")
    monkeypatch.setattr("subprocess.run", run)
    return calls
