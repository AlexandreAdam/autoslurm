"""Evidence isolation across collection, cache and artifact boundaries."""

import base64
import copy
import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from autoslurm import inspect_bundle, inspect_bundles
from autoslurm.execution import EXECUTION_METADATA_KEY, resolve_execution_context
from autoslurm.storage import out_dir, storage_root
from autoslurm.utils import save_config
from tests.inspection_helpers import saved_run, mock_scheduler, remote_observation


def test_invalid_id_does_not_poison_a_healthy_run_on_the_same_machine(monkeypatch):
    broken = saved_run(name="broken", jobs={"bad": {"id": "bad-id"}})
    healthy = saved_run(name="healthy")
    calls = mock_scheduler(monkeypatch, accounting="101|COMPLETED|0:0|None|101")
    views = inspect_bundles([broken, healthy])
    assert views[1]["state"] == "completed"
    assert views[0]["state"] == "unknown" and views[0]["errors"]
    assert len(calls) == 2
    assert calls[0][calls[0].index("-j") + 1] == "101"


def test_valid_json_with_missing_cache_fields_is_unavailable_evidence(monkeypatch):
    path = saved_run()
    mock_scheduler(monkeypatch, accounting="101|COMPLETED|0:0|None|101")
    inspect_bundle(path)
    cache = next((storage_root() / "observations").glob("*.json"))
    cache.write_text(json.dumps({"definition_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}))
    view = inspect_bundle(path, refresh=False)
    assert view["jobs"][0]["state"] == "UNKNOWN"
    assert view["freshness"] == "never"
    assert any(error["source"] == "cache" for error in view["errors"])


def test_missing_script_error_does_not_contaminate_cached_scheduler_status(monkeypatch):
    path = saved_run()
    mock_scheduler(monkeypatch, accounting="101|COMPLETED|0:0|None|101")
    first = inspect_bundle(path, include_script=True)
    assert any(error["source"] == "script" for error in first["errors"])
    second = inspect_bundle(path, refresh=False)
    assert second["state"] == "completed"
    assert second["errors"] == []
    assert "scripts" not in second


def test_malformed_recorded_remote_transport_never_queries_local_slurm(monkeypatch):
    path = saved_run(jobs={"sample": {"id": "101", EXECUTION_METADATA_KEY: {"is_remote": True, "transport": {}}}})
    calls = mock_scheduler(monkeypatch, accounting="101|COMPLETED|0:0|None|101")
    result = inspect_bundle(path)
    assert calls == []
    assert result["state"] == "unknown" and result["errors"]


def remote_run(tmp_path, *, identity="101", name="remote"):
    context = resolve_execution_context("remote", {"hostname": "cluster"}, root_resolver=lambda *args: str(tmp_path / "remote"))
    job = {"name": "sample", "id": identity, "script": "echo science", "slurm": {"output": "/logs/shared.out"}}
    job[EXECUTION_METADATA_KEY] = context.resolve_job(job)
    return saved_run(name=name, jobs={"sample": job})


def remote_logs(monkeypatch, response=None):
    calls = []
    response = "0|ok|12|" + base64.b64encode(b"live detail\n").decode() if response is None else response
    def transport(command, **kwargs):
        assert command[0] == "ssh"
        calls.append(command)
        stdout = response if command[-1] == "python3 -B -" else remote_observation(accounting="101|FAILED|1:0|NonZeroExitCode|101")
        return subprocess.CompletedProcess(command, 0, stdout, "")
    monkeypatch.setattr("subprocess.run", transport)
    return calls


def test_remote_missing_log_keeps_its_observation_time(tmp_path, monkeypatch):
    path = remote_run(tmp_path)
    remote_logs(monkeypatch, "0|missing||")
    entry = inspect_bundle(path, include_logs=True)["logs"][0]
    assert entry["state"] == "missing"
    assert entry["freshness"] == "fresh" and entry["observed_at"]
    assert entry["path"] == "/logs/shared.out"


@pytest.mark.parametrize("bad_cache", [[], None, {"jobs": []}])
def test_invalid_cache_shapes_do_not_crash_cached_inspection(monkeypatch, bad_cache):
    path = saved_run()
    mock_scheduler(monkeypatch, accounting="101|COMPLETED|0:0|None|101")
    inspect_bundle(path)
    next((storage_root() / "observations").glob("*.json")).write_text(json.dumps(bad_cache))
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: pytest.fail("Cached read queried scheduler"))
    result = inspect_bundle(path, refresh=False)
    assert result["freshness"] == "never" and result["errors"][0]["source"] == "cache"


def test_observation_cache_write_failure_keeps_live_scheduler_evidence(monkeypatch):
    path = saved_run()
    mock_scheduler(monkeypatch, accounting="101|COMPLETED|0:0|None|101")
    def disk_failure(*args):
        raise OSError("cache disk full")
    monkeypatch.setattr("autoslurm.inspection_cache.atomic_json", disk_failure)
    result = inspect_bundle(path)
    assert result["state"] == "completed" and result["freshness"] == "partial"
    assert result["jobs"][0]["tasks"][0]["source"] == "accounting"
    assert result["errors"][0]["source"] == "cache"


def test_log_cache_write_failure_keeps_the_fetched_log(tmp_path, monkeypatch):
    from autoslurm import inspection_cache
    path = remote_run(tmp_path)
    calls = remote_logs(monkeypatch)
    real_write = inspection_cache.atomic_json
    def disk_failure(path, value):
        if path.parent.name == "logs":
            raise OSError("log cache full")
        real_write(path, value)
    monkeypatch.setattr(inspection_cache, "atomic_json", disk_failure)
    result = inspect_bundle(path, include_logs=True)
    assert len(calls) == 2
    assert result["logs"][0]["state"] == "available"
    assert result["logs"][0]["text"] == "live detail"
    assert result["freshness"] == "partial"
    assert any(error["source"] == "cache" for error in result["errors"])
    # Request-specific cache/log errors must not poison later status-only reads.
    assert inspect_bundle(path, refresh=False)["errors"] == []


@pytest.mark.parametrize("response", ["", "0|ok|1|***", "0|ok|20|" + base64.b64encode(b"too much data").decode()])
def test_invalid_or_oversized_remote_log_response_is_bounded_error(tmp_path, monkeypatch, response):
    path = remote_run(tmp_path)
    remote_logs(monkeypatch, response)
    result = inspect_bundle(path, include_logs=True, max_log_bytes=4)
    assert result["logs"][0]["state"] == "error"
    assert result["state"] == "failed" and result["freshness"] == "partial"
    assert not list((storage_root() / "observations/logs").glob("*.json"))


def test_corrupt_log_cache_is_explicit_and_does_not_contact_remote_host(tmp_path, monkeypatch):
    path = remote_run(tmp_path)
    remote_logs(monkeypatch)
    inspect_bundle(path, include_logs=True)
    next((storage_root() / "observations/logs").glob("*.json")).write_text("[]")
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: pytest.fail("Cached log read contacted host"))
    result = inspect_bundle(path, refresh=False, include_logs=True)
    assert result["freshness"] == "stale" and result["logs"][0]["state"] == "error"
    assert result["errors"]


def test_cached_excerpt_is_not_relabelled_for_another_job_using_the_same_path(tmp_path, monkeypatch):
    first = remote_run(tmp_path)
    remote_logs(monkeypatch)
    inspect_bundle(first, include_logs=True)
    second = remote_run(tmp_path, identity="102", name="second")
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: pytest.fail("Cached inspection queried host"))
    result = inspect_bundle(second, refresh=False, include_logs=True)
    assert result["logs"][0]["state"] == "not_cached"
    assert result["jobs"][0]["id"] == "102"


def test_legacy_local_profile_can_read_logs_without_saved_remote_metadata(monkeypatch):
    save_config({"machines": {"local": {"env_command": "true", "slurm_account": "mock"}}, "default_machine": "local"})
    path = saved_run(jobs={"sample": {"id": "101", "machine": "local"}})
    (out_dir() / "sample-101.out").write_text("local evidence")
    mock_scheduler(monkeypatch)
    result = inspect_bundle(path, include_logs=True)
    assert result["logs"][0]["text"] == "local evidence"


@pytest.mark.parametrize("execution", [None, {"is_remote": True, "transport": []}, {"is_remote": False, "transport": {"hostname": "cluster"}}])
def test_malformed_machine_metadata_is_reported_per_run(monkeypatch, execution):
    broken = saved_run(name="bad", jobs={"sample": {"id": "101", EXECUTION_METADATA_KEY: execution}})
    healthy = saved_run(name="good", jobs={"sample": {"id": "102"}})
    calls = mock_scheduler(monkeypatch, accounting="102|COMPLETED|0:0|None|102")
    results = inspect_bundles([broken, healthy])
    assert len(calls) == 2 and results[1]["state"] == "completed"
    assert results[0]["state"] == "unknown" and results[0]["errors"]


@pytest.mark.parametrize("options", [{"tail": -1}, {"tail": 1.5}, {"max_log_bytes": "100"}, {"max_logs": True}, {"job_name": "absent"}])
def test_invalid_artifact_request_stops_before_querying_or_caching(monkeypatch, options):
    path = saved_run()
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: pytest.fail("Invalid artifact request queried host"))
    with pytest.raises(ValueError):
        inspect_bundle(path, include_logs=True, **options)
    assert not list((storage_root() / "observations").glob("*.json"))


def test_partial_parent_evidence_is_preserved_when_children_are_absent(monkeypatch):
    path = saved_run(jobs={"array": {"id": "101", "slurm": {"array": "0-2"}}})
    mock_scheduler(monkeypatch, queue_code=1, accounting="101|FAILED|1:0|NonZeroExitCode|101")
    result = inspect_bundle(path)
    assert result["state"] == "failed" and result["freshness"] == "partial"
    assert result["jobs"][0]["counts"]["unknown"] == 3


def test_definition_change_during_loading_is_reported_without_querying_it(monkeypatch):
    from autoslurm import inspection_collection
    path = saved_run()
    real_load = inspection_collection.load_bundle_from_path
    def concurrent_change(selected):
        result = real_load(selected)
        data = json.loads(Path(selected).read_text())
        data["sample"]["id"] = "999"
        Path(selected).write_text(json.dumps(data))
        return result
    monkeypatch.setattr(inspection_collection, "load_bundle_from_path", concurrent_change)
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: pytest.fail("Changed definition was queried"))
    result = inspect_bundle(path)
    assert result["state"] == "broken" and "changed" in result["errors"][0]["message"]


def test_changed_local_receipt_identity_invalidates_old_scheduler_cache(monkeypatch):
    from autoslurm import submit_jobs
    from autoslurm.submission import atomic_json
    selected = saved_run(jobs={"sample": {}})
    save_config({"machines": {"mock": {"env_command": "true", "slurm_account": "mock"}}, "default_machine": "mock"})
    monkeypatch.setattr("autoslurm.bundle_preparation.validate_slurm_content", lambda content: None)
    monkeypatch.setattr("subprocess.run", lambda command, **kwargs: subprocess.CompletedProcess(command, 0, "Submitted batch job 101", ""))
    receipt = submit_jobs("study", bundle_path=selected)
    path = Path(receipt["bundle_path"])
    definition = json.loads(path.read_text())
    definition["sample"].pop("id")
    atomic_json(path, definition)
    uncertain = copy.deepcopy(receipt)
    uncertain.update(state="uncertain", execution_finished=False)
    uncertain["jobs"]["sample"] = {"state": "uncertain", "dependencies": []}
    atomic_json(Path(receipt["receipt_path"]), uncertain)
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: pytest.fail("Receipt-only/cached read queried scheduler"))
    assert inspect_bundle(path)["state"] == "uncertain"
    atomic_json(Path(receipt["receipt_path"]), receipt)
    cached = inspect_bundle(path, refresh=False)
    assert cached["freshness"] == "never"
    assert cached["jobs"][0]["id"] == "101" and cached["jobs"][0]["state"] == "UNKNOWN"


def test_existing_cache_with_attached_artifacts_remains_readable_without_artifact_errors(monkeypatch):
    path = saved_run()
    mock_scheduler(monkeypatch, accounting="101|COMPLETED|0:0|None|101")
    result = inspect_bundle(path)
    result["scripts"] = [{"content": None}]
    result["errors"].append({"source": "script", "message": "old missing script"})
    next((storage_root() / "observations").glob("*.json")).write_text(json.dumps(result))
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: pytest.fail("Legacy cache read queried scheduler"))
    cached = inspect_bundle(path, refresh=False)
    assert cached["state"] == "completed" and cached["freshness"] == "stale"
    assert not cached["errors"] and "scripts" not in cached


@pytest.mark.parametrize("field,value", [("id", []), ("counts", []), ("tasks", [None])])
def test_malformed_cached_job_fields_are_rejected(monkeypatch, field, value):
    path = saved_run()
    mock_scheduler(monkeypatch)
    result = inspect_bundle(path)
    result["jobs"][0][field] = value
    next((storage_root() / "observations").glob("*.json")).write_text(json.dumps(result))
    result = inspect_bundle(path, refresh=False)
    assert result["freshness"] == "never" and any(error["source"] == "cache" for error in result["errors"])


def test_unreadable_profiles_do_not_hide_jobs_with_complete_producing_evidence(monkeypatch):
    from autoslurm.storage import config_file_path
    legacy = saved_run(name="legacy", jobs={"sample": {"id": "101", "machine": "remote"}})
    local = saved_run(name="local", jobs={"sample": {"id": "102"}})
    config_file_path().write_text("invalid JSON")
    calls = mock_scheduler(monkeypatch, accounting="102|COMPLETED|0:0|None|102")
    results = inspect_bundles([legacy, local])
    assert len(calls) == 2 and results[1]["state"] == "completed"
    assert results[0]["errors"][0]["source"] == "configuration"
