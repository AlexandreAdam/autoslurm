import json
import os
from pathlib import Path
import shlex
import subprocess

import pytest

from autoslurm import inspect_bundle, inspect_bundles, list_runs, execute_acp, save_bundle, submit_jobs
from autoslurm.execution import resolve_execution_context, EXECUTION_METADATA_KEY
from autoslurm.storage import out_dir, storage_root
from autoslurm.utils import save_config
from tests.inspection_helpers import saved_run, mock_scheduler, remote_observation
from tests.integration.test_reference_client import science_client, EXAMPLE


@pytest.mark.local_processes
def test_scientific_array_shared_evidence_and_failed_refresh(science_client, monkeypatch, capsys):
    definitions = json.loads((EXAMPLE / "bundles/array.json").read_text())
    planned = save_bundle(definitions, "science-study")
    original = planned.read_bytes()
    real_run = subprocess.run
    def submit(command, **kwargs):
        if command[0] == "bash":
            return real_run(command, **kwargs)
        assert command[0] == "sbatch"
        script = Path(command[-1])
        if script.name.startswith("shards_"):
            for index in (0, 1):
                env = dict(os.environ, SLURM_ARRAY_TASK_ID=str(index if index == 0 else 99))
                result = real_run(["bash", str(script)], env=env, capture_output=True, text=True)
                assert (result.returncode == 0) == (index == 0)
                (out_dir() / f"shards-{9000 + index}.out").write_text(result.stdout + result.stderr)
            return subprocess.CompletedProcess(command, 0, "Submitted batch job 101", "")
        return subprocess.CompletedProcess(command, 0, "Submitted batch job 102", "")
    monkeypatch.setattr("subprocess.run", submit)
    receipt = submit_jobs("science-study", bundle_path=planned)
    capsys.readouterr()
    selected = Path(receipt["bundle_path"])
    selected_bytes = selected.read_bytes()
    queue = "101_3|RUNNING|00:01:00|None\n102|PENDING|00:01:00|DependencyNeverSatisfied"
    accounting = "101|FAILED|1:0|None|101\n101_0|COMPLETED|0:0|None|9000\n101_1|FAILED|2:0|NonZeroExitCode|9001\n101_1.batch|FAILED|2:0|ignored|9001.batch"
    calls = mock_scheduler(monkeypatch, queue=queue, accounting=accounting)
    view = inspect_bundle(receipt_path=receipt["receipt_path"], include_logs=True, job_name="shards", task_index=1)
    assert len(calls) == 2
    shards = next(job for job in view["jobs"] if job["name"] == "shards")
    assert [task["state"] for task in shards["tasks"]] == ["COMPLETED", "FAILED", "UNKNOWN", "RUNNING"]
    assert shards["counts"] == {"completed": 1, "failed": 1, "cancelled": 0, "running": 1, "pending": 0, "unknown": 1, "not_submitted": 0}
    assert shards["tasks"][1]["exit_code"] == "2:0"
    assert shards["tasks"][1]["reason"] == "NonZeroExitCode"
    assert view["state"] == "failed"
    assert view["submissions"][0]["state"] == "submitted"
    assert view["logs"][0]["path"].endswith("shards-9001.out")
    assert view["logs"][0]["text"]
    # A fresh agent needs only local discovery and an exact reference.
    found = execute_acp({"action": "list_runs", "bundle": "science-study"})["result"]
    assert any(row["bundle_path"] == str(selected) for row in found)
    agent = execute_acp({"action": "inspect_run", "bundle_path": str(selected)})["result"]
    def evidence(result):
        return [(job["id"], job["state"], [(task["job_id"], task["state"], task["reason"], task["exit_code"]) for task in job["tasks"]]) for job in result["jobs"]]
    assert evidence(agent) == evidence(view)
    from autoslurm.apps import inspect as inspect_cli, status as status_cli
    inspect_cli.main(["--bundle-file", str(selected), "--array", "--json"])
    terminal = json.loads(capsys.readouterr().out)
    assert [task["job_id"] for task in terminal["jobs"][0]["tasks"]] == [task["job_id"] for task in agent["jobs"][0]["tasks"]]
    status_cli.main(["--bundle-file", str(selected), "--array"])
    human = capsys.readouterr().out
    assert "101_1" in human and "FAILED" in human and "101_2" in human and "UNKNOWN" in human
    assert "NonZeroExitCode" in human and "exit=2:0" in human
    with (out_dir() / "shards-9001.out").open("a") as stream:
        stream.write("\nmore failure detail\n")
    assert "more failure detail" in inspect_bundle(selected, include_logs=True, job_name="shards", task_index=1)["logs"][0]["text"]
    mock_scheduler(monkeypatch, queue_code=1, accounting_code=1)
    failed = inspect_bundle(selected)
    assert failed["state"] == "unknown"
    assert failed["freshness"] == "failed"
    assert failed["last_observed"]["state"] == "failed"
    assert len(failed["errors"]) >= 2
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: pytest.fail("Cached inspection made an external call"))
    assert inspect_bundle(selected, refresh=False)["freshness"] == "stale"
    assert selected.read_bytes() == selected_bytes
    assert planned.read_bytes() == original


@pytest.mark.local_processes
def test_remote_logs_use_recorded_roots_and_refresh_custom_task_files(tmp_path, monkeypatch):
    project = tmp_path / "producing project"
    (project / "logs").mkdir(parents=True)
    config = {"hostname": "producing-host", "project_root": str(project)}
    context = resolve_execution_context("old-profile", config, root_resolver=lambda *args: str(tmp_path / "state"))
    job = {"name": "array", "id": "700", "machine": "old-profile", "script": "echo science", "slurm": {"array": "0,2-6:2%3", "output": "logs/%A_%a.out", "error": "logs/%A_%a.err"}}
    job[EXECUTION_METADATA_KEY] = context.resolve_job(job)
    selected = saved_run(jobs={"array": job})
    save_config({"machines": {"new-profile": {"hostname": "wrong-host"}}, "default_machine": "new-profile"})
    stdout = project / "logs/700_2.out"
    stderr = project / "logs/700_2.err"
    stdout.write_text("old result\n")
    stderr.write_text("old failure\n")
    real_run = subprocess.run
    calls = []
    def transport(command, **kwargs):
        assert command[0] == "ssh" and "producing-host" in command
        calls.append(command)
        shell = shlex.split(command[-1])[-1]
        if "tail -c" in shell:
            return real_run(["bash", "-c", shell], capture_output=True, text=True)
        return subprocess.CompletedProcess(command, 0, remote_observation("700_4|RUNNING|10:00|None", "700.2|FAILED|1:0|OutOfMemory|12345\n700_2.extern|COMPLETED|0:0|ignored|9"), "")
    monkeypatch.setattr("subprocess.run", transport)
    first = inspect_bundle(selected, include_logs=True, job_name="array", task_index=2, tail=1)
    assert len(calls) == 2  # One scheduler SSH, one log SSH; no raw-ID lookup.
    assert first["jobs"][0]["tasks"][1]["raw_id"] == "12345"
    assert first["jobs"][0]["tasks"][1]["job_id"] == "700_2"
    assert {entry["text"] for entry in first["logs"]} == {"old result", "old failure"}
    stdout.write_text("new result\n")  # Same length and a replacement must refresh too.
    stderr.write_text("longer failure\nextra detail\n")
    second = inspect_bundle(selected, include_logs=True, job_name="array", task_index=2, tail=1)
    assert {entry["text"] for entry in second["logs"]} == {"new result", "extra detail"}
    assert any(entry["truncated"] for entry in second["logs"])
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: pytest.fail("Cached remote logs contacted a host"))
    cached = inspect_bundle(selected, refresh=False, include_logs=True, job_name="array", task_index=2, tail=0)
    assert all(entry["text"] == "" and entry["freshness"] == "stale" for entry in cached["logs"])


@pytest.mark.parametrize("queue_code,accounting_code", [(0, 0), (1, 0), (0, 1), (1, 1)])
def test_empty_or_failed_queries_never_imply_completion(monkeypatch, queue_code, accounting_code):
    path = saved_run(jobs={"array": {"id": "101", "slurm": {"array": "0-2"}}})
    calls = mock_scheduler(monkeypatch, queue_code=queue_code, accounting_code=accounting_code)
    view = inspect_bundle(path)
    assert len(calls) == 2
    assert view["state"] == "unknown"
    assert all(task["state"] == "UNKNOWN" for task in view["jobs"][0]["tasks"])
    assert len(view["errors"]) == queue_code + accounting_code


def test_machine_batches_across_runs_and_ignores_accounting_steps(monkeypatch):
    paths = [saved_run(name="first"), saved_run(name="second", jobs={"sample": {"id": "102"}})]
    calls = mock_scheduler(monkeypatch, accounting="101|COMPLETED|0:0|None|101\n101.batch|FAILED|1:0|ignored|101.batch\n102|PENDING||Resources|102")
    views = inspect_bundles(paths)
    assert len(calls) == 2
    assert calls[0][calls[0].index("-j") + 1] == "101,102"
    assert [view["state"] for view in views] == ["completed", "pending"]


def test_parent_failure_does_not_attribute_failure_to_missing_tasks(monkeypatch):
    path = saved_run(jobs={"array": {"id": "101", "slurm": {"array": "0-3"}}})
    mock_scheduler(monkeypatch, accounting="101|FAILED|1:0|UnknownCause|101")
    view = inspect_bundle(path)
    assert view["state"] == "failed"
    assert view["jobs"][0]["counts"]["failed"] == 0
    assert view["jobs"][0]["counts"]["unknown"] == 4
    assert all(task["reason"] is None for task in view["jobs"][0]["tasks"])


def test_changed_cached_definition_is_not_reinterpreted_as_old_evidence(monkeypatch):
    path = saved_run()
    mock_scheduler(monkeypatch, accounting="101|COMPLETED|0:0|None|101")
    assert inspect_bundle(path)["state"] == "completed"
    content = json.loads(path.read_text())
    content["sample"]["id"] = "999"
    path.write_text(json.dumps(content))
    assert inspect_bundle(path, refresh=False)["state"] == "unknown"


def test_partial_query_failure_retains_live_state_and_marks_incomplete(monkeypatch):
    path = saved_run()
    mock_scheduler(monkeypatch, queue="101|RUNNING|02:00|Resources", accounting_code=1)
    view = inspect_bundle(path)
    assert view["state"] == "running" and view["freshness"] == "partial"
    assert view["errors"][0]["source"] == "accounting"
    assert view["jobs"][0]["tasks"][0]["source"] == "queue"
    mock_scheduler(monkeypatch, queue="101|RUNNING|02:00|None", accounting="101|COMPLETED|0:0|None|101")
    assert inspect_bundle(path)["state"] == "running"


@pytest.mark.parametrize("stdout,code,stderr", [("incomplete reply", 0, ""), ("", 255, "connection lost")])
def test_remote_query_failure_is_evidence_not_local_fallback(monkeypatch, stdout, code, stderr):
    save_config({"machines": {"remote": {"hostname": "cluster"}}, "default_machine": "remote"})
    path = saved_run(jobs={"sample": {"id": "101", "machine": "remote"}})
    calls = []
    def remote(command, **kwargs):
        calls.append(command)
        assert command[0] == "ssh"
        return subprocess.CompletedProcess(command, code, stdout, stderr)
    monkeypatch.setattr("subprocess.run", remote)
    view = inspect_bundle(path)
    assert len(calls) == 1
    assert view["state"] == "unknown" and view["freshness"] == "failed"
    assert view["errors"][0]["source"] == "transport"


def test_missing_profile_and_invalid_identity_do_not_query_local_scheduler(monkeypatch):
    paths = [saved_run(name="remote", jobs={"sample": {"id": "101", "machine": "missing"}}),
             saved_run(name="invalid", jobs={"sample": {"id": "not-an-id"}})]
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: pytest.fail("Invalid producer/ID issued a command"))
    views = inspect_bundles(paths)
    assert all(view["state"] == "unknown" and view["errors"] for view in views)
    assert "no local fallback" in views[0]["errors"][0]["message"]


def test_log_bounds_patterns_and_missing_snapshot_cache(monkeypatch, tmp_path):
    path = saved_run(jobs={"array": {"id": "101", "slurm": {"array": "0-2"}}})
    mock_scheduler(monkeypatch, accounting="101_0|COMPLETED|0:0|None|9000")
    log = out_dir() / "array-9000.out"
    log.write_text("first line\n" + "a" * 80 + "\nlast line\n")
    result = inspect_bundle(path, include_logs=True, max_logs=1, max_log_bytes=20, tail=1)
    assert result["logs"][0]["text"] == "last line"
    assert result["logs"][0]["truncated"]
    assert result["logs"][1] == {"state": "omitted", "count": 2, "reason": "Requested log-file bound reached."}
    # A removed definition must not continue to advertise its cached completion.
    path.unlink()
    assert inspect_bundle(path, refresh=False)["state"] == "broken"
    unsupported = saved_run(jobs={"sample": {"id": "101", "slurm": {"output": str(tmp_path / "%N.out")}}})
    result = inspect_bundle(unsupported, include_logs=True)
    assert result["logs"][0]["state"] == "error"
    assert "placeholder %N" in result["logs"][0]["error"]
    assert result["freshness"] == "partial"


def test_receipt_overlay_preserves_partial_submission_outcome(monkeypatch):
    from autoslurm.submission import atomic_json
    # Use the real receipt writer and an exact tracking file, then simulate evidence
    # persisted before a tracking mirror could be updated.
    draft = saved_run(jobs={"sample": {}})
    save_config({"machines": {"mock": {"env_command": "true", "slurm_account": "mock"}}, "default_machine": "mock"})
    monkeypatch.setattr("autoslurm.bundle_preparation.validate_slurm_content", lambda content: None)
    monkeypatch.setattr("subprocess.run", lambda command, **kwargs: subprocess.CompletedProcess(command, 0, "Submitted batch job 101", ""))
    receipt = submit_jobs("study", bundle_path=draft)
    receipt["state"] = "uncertain"
    receipt["jobs"]["sample"].update(state="accepted", id="101")
    atomic_json(Path(receipt["receipt_path"]), receipt)
    selected = Path(receipt["bundle_path"])
    snapshot = json.loads(selected.read_text())
    snapshot["sample"].pop("id")
    atomic_json(selected, snapshot)
    before = selected.read_bytes()
    receipt_before = Path(receipt["receipt_path"]).read_bytes()
    mock_scheduler(monkeypatch, accounting="101|FAILED|1:0|NonZeroExitCode|101")
    result = inspect_bundle(receipt_path=receipt["receipt_path"])
    assert result["submissions"][0]["state"] == "uncertain"
    assert result["jobs"][0]["submission_state"] == "accepted"
    assert result["jobs"][0]["id"] == "101" and result["state"] == "failed"
    assert selected.read_bytes() == before
    assert Path(receipt["receipt_path"]).read_bytes() == receipt_before


def test_sync_refreshes_appended_replaced_and_truncated_logs_without_rewriting_definitions(tmp_path, monkeypatch):
    import shutil
    from autoslurm.sync import sync_machine
    remote_root = tmp_path / "remote"
    for directory in ("jobs", "slurm", "out"):
        (remote_root / directory).mkdir(parents=True)
    (remote_root / "jobs/run.json").write_text("remote definition")
    (remote_root / "out/task.out").write_text("first")
    save_config({"machines": {"remote": {"hostname": "cluster", "storage_root": str(remote_root), "slurm_account": "mock", "env_command": "true"}}, "default_machine": "remote"})
    def transport(command, **kwargs):
        if command[0] == "ssh":
            return subprocess.CompletedProcess(command, 0, str(remote_root), "")
        assert command[0] == "rsync"
        source = Path(command[-2].split(":", 1)[1])
        target = Path(command[-1])
        for file in source.iterdir():
            destination = target / file.name
            if not destination.exists() or "--ignore-existing" not in command:
                shutil.copyfile(file, destination)
        return subprocess.CompletedProcess(command, 0, "", "")
    monkeypatch.setattr("subprocess.run", transport)
    sync_machine("remote")
    local_definition = storage_root() / "jobs/run.json"
    assert local_definition.read_text() == "remote definition"
    for text in ("first plus appended detail", "same sized replacement!!!!", "short"):
        (remote_root / "out/task.out").write_text(text)
        (remote_root / "jobs/run.json").write_text("must not overwrite")
        sync_machine("remote")
        assert (out_dir() / "task.out").read_text() == text
        assert local_definition.read_text() == "remote definition"


def test_cached_refresh_never_fetches_remote_logs_even_with_override(tmp_path, monkeypatch):
    context = resolve_execution_context("remote", {"hostname": "cluster"}, root_resolver=lambda *args: str(tmp_path / "remote"))
    job = {"name": "sample", "id": "101", "script": "echo science", "slurm": {}}
    job[EXECUTION_METADATA_KEY] = context.resolve_job(job)
    path = saved_run(jobs={"sample": job})
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: pytest.fail("Cached mode made a command"))
    view = inspect_bundle(path, refresh=False, refresh_logs=True, include_logs=True)
    assert view["freshness"] == "never" and view["logs"][0]["state"] == "not_cached"
