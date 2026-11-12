"""Path boundaries that do not require a scheduler or transport."""

from datetime import datetime
from io import StringIO
import json
import shlex
import subprocess

import pytest

from autoslurm import recorded_execution, resolve_results_path, path_exists
from autoslurm.execution import EXECUTION_METADATA_KEY, resolve_execution_context
from autoslurm.job_to_slurm import write_slurm_content
from autoslurm.save_load_jobs import select_bundle_snapshot, load_bundle
from autoslurm.storage import jobs_dir, storage_root


@pytest.mark.parametrize("log_name", [None, "log %j.out"])
def test_nested_working_directory_keeps_input_and_results_bases(tmp_path, log_name):
    project = tmp_path / "science project"
    (project / "analysis").mkdir(parents=True)
    (project / "data").mkdir()
    (project / "data/input.json").write_text("[1]")
    config = {"software_root": str(tmp_path / "software"), "results_root": str(project), "path": "/obsolete-storage"}
    job = {"name": "sample", "script": "science-demo", "slurm": {"output": log_name, "chdir": None}, "working_directory": "analysis", "input_args": ["input_file"], "path_args": ["parts_dir"], "script_args": {"input_file": "data/input.json", "parts_dir": "future/parts", "output_dir": "future/summary"}}
    context = resolve_execution_context("local", config)
    context.validate_jobs([job])  # Future results need not exist yet.
    evidence = context.resolve_job(job)
    assert evidence["storage_root"] == str(storage_root())
    assert evidence["working_directory"] == str(project / "analysis")
    assert evidence["resolved_paths"]["input_file"] == str(project / "data/input.json")
    assert evidence["resolved_paths"]["parts_dir"] == str(project / "future/parts")
    output = StringIO()
    write_slurm_content(output, job, config, context=context)
    directives = [line for line in output.getvalue().splitlines() if line.startswith("#SBATCH --output=")]
    assert len(directives) == 1
    expected_log = project / "analysis" / log_name if log_name else storage_root() / "out/%x-%j.out"
    assert shlex.split(directives[0][len("#SBATCH "):]) == ["--output=" + str(expected_log)]


@pytest.mark.parametrize("field,value", [("output_dir", "/outside"), ("output_dir", "../outside"), ("working_directory", "/outside"), ("working_directory", "../outside"), ("output", "/outside"), ("output", "../outside")])
def test_project_aware_paths_cannot_escape_declared_bases(field, value, tmp_path):
    job = {"name": "sample", "script": "science-demo", "slurm": {}, "script_args": {}}
    if field == "working_directory":
        job[field] = value
    elif field == "output":
        job["slurm"][field] = value
    else:
        job["script_args"][field] = value
    context = resolve_execution_context("local", {"project_root": str(tmp_path)})
    with pytest.raises(ValueError, match="relative|traverse"):
        context.validate_jobs([job])


def test_one_argument_cannot_use_two_path_bases(tmp_path):
    context = resolve_execution_context("local", {"project_root": str(tmp_path)})
    with pytest.raises(ValueError, match="both a required input and a result"):
        context.resolve_job({"input_args": ["parts"], "path_args": ["parts"], "script_args": {"parts": "study"}})


@pytest.mark.parametrize("key", ["project_root", "results_root"])
def test_invalid_machine_root_fails_before_remote_discovery(key):
    def no_discovery(*args):
        pytest.fail("Invalid machine roots reached remote discovery")
    with pytest.raises(ValueError, match=key):
        resolve_execution_context("remote", {"hostname": "fake", key: "relative/root"}, root_resolver=no_discovery)


def test_saved_remote_artifact_uses_producing_transport_without_profile(tmp_path, monkeypatch):
    context = resolve_execution_context("old-name", {"hosturl": "old-host", "username": "scientist", "results_root": "/old/results"}, root_resolver=lambda *args: "/old/state")
    evidence = context.resolve_job({"script_args": {"output_dir": "study"}})
    evidence["project_root"] = "/old/project"  # A saved pre-merge producing record.
    saved = tmp_path / "historical_20260101000000.json"
    saved.write_text(json.dumps({"sample": {"name": "sample", "script": "science-demo", "slurm": {}, EXECUTION_METADATA_KEY: evidence}}))
    calls = []
    def fake_run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")
    monkeypatch.setattr("subprocess.run", fake_run)
    assert recorded_execution(saved)["machine"] == "old-name"
    assert resolve_results_path("study/summary.json", bundle_path=saved) == "/old/results/study/summary.json"
    assert path_exists("study/summary.json", bundle_path=saved)
    assert calls == [["ssh", "scientist@old-host", "test -e /old/results/study/summary.json"]]
    with pytest.raises(ValueError, match="either a saved execution"):
        resolve_results_path("study", bundle_path=saved, machine_name="new-name")


def test_legacy_record_without_execution_evidence_is_explicit(tmp_path):
    saved = tmp_path / "legacy.json"
    saved.write_text(json.dumps({"sample": {"name": "sample", "script": "science-demo", "slurm": {}}}))
    with pytest.raises(ValueError, match="no recorded execution paths"):
        resolve_results_path("study", bundle_path=saved)


def test_dated_selection_and_named_loading_share_exact_snapshot(tmp_path):
    older = jobs_dir() / "study_20260101000000.json"
    newer = jobs_dir() / "study_20260201000000.json"
    older.write_text(json.dumps({"sample": {"script": "old", "slurm": {}}}))
    newer.write_text(json.dumps({"sample": {"script": "new", "slurm": {}}}))
    selected = select_bundle_snapshot("study", desired_date=datetime(2026, 1, 2))
    jobs, _, saved_date = load_bundle("study", datetime(2026, 1, 2))
    assert selected["path"] == older
    assert selected["date"] == saved_date == datetime(2026, 1, 1)
    assert jobs[0]["name"] == "sample"
    assert jobs[0]["script"] == "old"
