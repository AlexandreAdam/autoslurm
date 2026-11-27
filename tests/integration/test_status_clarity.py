"""Status meaning, provenance and presentation use one offline evidence path."""

import copy
import json
import sys
from pathlib import Path

import pytest

from autoslurm import inspect_bundle, inspect_bundles, execute_acp
from autoslurm.apps import status as cli
from autoslurm.array_status import aggregate_states, status_for_job_id
from autoslurm.inspection_cache import InspectionCache
from autoslurm.status_explanations import explain_state
from autoslurm.status_table import table, cell_width
from autoslurm.status_views import rows_from_resolved, bundle_jobs_context_from_rows
from autoslurm.storage import storage_root
from tests.inspection_helpers import saved_run, mock_scheduler


@pytest.mark.parametrize("states,expected", [
    (["FAILED", "CANCELLED"], "FAILED"),
    (["TIMEOUT", "CANCELLED", "UNKNOWN"], "FAILED"),
    (["RUNNING", "CANCELLED"], "RUNNING"),
    (["PENDING", "CANCELLED"], "PENDING"),
    (["UNKNOWN", "CANCELLED"], "UNKNOWN"),
    (["COMPLETED", "CANCELLED"], "CANCELLED"),
])
def test_aggregate_does_not_hide_failed_active_or_missing_tasks(states, expected):
    assert aggregate_states(states) == expected
    assert aggregate_states(list(reversed(states))) == expected


def test_failed_array_task_wins_over_cancelled_parent():
    assert status_for_job_id("101", {"101": "CANCELLED", "101_0": "FAILED"}, 2) == "FAILED"


@pytest.mark.parametrize("reason,category", [
    ("(Dependency)", "dependency"), ("DependencyNeverSatisfied", "dependency_invalid"),
    ("Priority", "priority"), ("Resources", "resources"),
    ("JobArrayTaskLimit", "array_limit"), ("JobHeldUser", "hold"),
    ("JobHeldAdmin", "hold"), ("BeginTime", "begin_time"),
    ("QOSGrpCpuLimit", "policy_limit"), ("AssocMaxJobsLimit", "policy_limit"),
    ("InvalidAccount", "configuration"), ("AccountNotAllowed", "configuration"),
    ("PartitionDown", "configuration"), ("NewSiteReason", "unknown"),
    (None, "unknown"), ("None", "unknown"),
])
def test_classification_preserves_raw_reason(reason, category):
    result = explain_state("PENDING", reason, "0:0")
    assert result["category"] == category and result["raw_reason"] == reason
    assert "exit=" not in result["message"]
    assert not explain_state("COMPLETED", reason, "0:0")["message"]


def failed_run():
    return saved_run(name="kepler", jobs={
        "stars": {"id": "101", "slurm": {"array": "0-49"}},
        "merge": {"id": "102", "dependencies": ["stars"]},
    })


def failed_observation(monkeypatch):
    return mock_scheduler(monkeypatch, accounting="\n".join(
        [f"101_{i}|FAILED|1:0|NonZeroExitCode" for i in range(50)] + ["102|CANCELLED|0:0|None"]))


def test_reported_fifty_failures_one_cancellation_in_cli_api_and_agent(monkeypatch, capsys):
    path = failed_run()
    calls = failed_observation(monkeypatch)
    view = inspect_bundle(path)
    assert len(calls) == 2 and view["state"] == "failed"
    assert view["jobs"][0]["counts"]["failed"] == 50
    cli.main([])
    text = capsys.readouterr().out
    row = next(line for line in text.splitlines() if "kepler" in line)
    assert "FAILED" in row and "50 failed" in row and "1 cancelled" in row
    assert "observation" not in text.lower() and "Checked:" in text
    assert "saved" not in text.splitlines()[0] and "\x1b[" not in text
    result = execute_acp({"action": "inspect_run", "bundle_path": str(path)})["result"]
    assert result["state"] == "failed" and result["jobs"][0]["explanation"]["category"] == "failure"


def graph_run(*, custom=False):
    return saved_run(name="graph", jobs={
        "set": {"id": "100"},
        "shards": {"id": "101", "dependencies": ["set"], "slurm": {"array": "0-3"}},
        "merge": {"id": "102", "dependencies": ["shards"], "slurm": {"time": "15:00"}},
        "summary": {"id": "103", "dependencies": ["merge", "set"],
                    "slurm": {"dependency": "afterany:102"} if custom else {}},
    })


def graph_observation(monkeypatch):
    return mock_scheduler(monkeypatch,
        queue="101_2|RUNNING|10:00|None\n101_3|PENDING|15:00|Resources\n102|PENDING|15:00|(Dependency)\n103|PENDING|15:00|Dependency",
        accounting="100|COMPLETED|0:0|None\n101_0|COMPLETED|0:0|None\n101_1|COMPLETED|0:0|None")


@pytest.mark.parametrize("custom", [False, True])
def test_dependency_names_complete_parent_and_custom_condition(monkeypatch, custom):
    path = graph_run(custom=custom)
    calls = graph_observation(monkeypatch)
    view = inspect_bundle(path)
    jobs = {job["name"]: job for job in view["jobs"]}
    assert len(calls) == 2
    assert jobs["merge"]["explanation"]["message"] == "Waiting for shards"
    assert jobs["summary"]["explanation"]["message"] == ("Waiting for dependencies" if custom else "Waiting for merge")
    assert jobs["shards"]["explanation"]["pending_counts"] == {"resources": 1}
    assert jobs["shards"]["tasks"][3]["reason"] == "Resources"


def test_cached_status_reinterprets_old_aggregate_without_any_write_or_query(monkeypatch, capsys):
    path = failed_run()
    failed_observation(monkeypatch)
    inspect_bundle(path)
    cache = InspectionCache(storage_root()).observation_path(path)
    payload = json.loads(cache.read_text())
    assert all("explanation" not in job for job in payload["jobs"])
    payload["state"] = "cancelled"  # Sidecar written by an older release.
    payload["jobs"][0]["state"] = "CANCELLED"
    payload["jobs"][0]["scheduler_state"] = "CANCELLED"
    cache.write_text(json.dumps(payload))
    before = cache.read_bytes()
    monkeypatch.setattr("subprocess.run", lambda *a, **k: pytest.fail("Cached status started a process"))
    monkeypatch.setattr("autoslurm.record_files.atomic_json", lambda *a, **k: pytest.fail("Cached status wrote data"))
    view = inspect_bundle(path, refresh=False)
    assert view["state"] == "failed" and view["freshness"] == "stale"
    assert view["jobs"][0]["explanation"]["message"].startswith("Last observed:")
    cli.main(["--cached"])
    text = capsys.readouterr().out
    assert "cached" in text and "Last saved check:" in text and "(not refreshed)" in text
    assert cache.read_bytes() == before


def test_mixed_pending_reasons_and_pure_projection_do_not_touch_definitions(monkeypatch):
    from autoslurm.save_load_jobs import load_bundle_from_path
    from autoslurm.status_explanations import explain_jobs
    path = graph_run()
    definitions, _, _ = load_bundle_from_path(path)
    mock_scheduler(monkeypatch,
        queue="101_2|PENDING|15:00|Priority\n101_3|PENDING|15:00|Resources\n102|PENDING|15:00|Dependency",
        accounting="100|COMPLETED|0:0|None\n101_0|FAILED|1:0|NonZeroExitCode\n101_1|COMPLETED|0:0|None")
    jobs = inspect_bundle(path)["jobs"]
    original = copy.deepcopy(definitions)
    raw = [{"reason": job["reason"], "tasks": [task["reason"] for task in job["tasks"]]} for job in jobs]
    monkeypatch.setattr(Path, "open", lambda *a, **k: pytest.fail("Pure explanation read a file"))
    monkeypatch.setattr("subprocess.run", lambda *a, **k: pytest.fail("Pure explanation started a process"))
    explain_jobs(definitions, jobs, freshness="stale")
    shards = next(job for job in jobs if job["name"] == "shards")
    assert shards["explanation"]["pending_counts"] == {"priority": 1, "resources": 1}
    assert shards["explanation"]["attention"] and "1 failed" in shards["explanation"]["message"]
    assert shards["explanation"]["message"].startswith("Last observed:")
    assert definitions == original
    assert [{"reason": job["reason"], "tasks": [task["reason"] for task in job["tasks"]]} for job in jobs] == raw


def test_cached_dependency_names_are_qualified_and_raw_details_survive(monkeypatch, capsys):
    path = graph_run()
    graph_observation(monkeypatch)
    inspect_bundle(path)
    monkeypatch.setattr("subprocess.run", lambda *a, **k: pytest.fail("Unexpected process"))
    cli.main(["--bundle-file", str(path), "--cached", "--details", "--width", "180"])
    text = capsys.readouterr().out
    assert "Last observed: waiting for" in text and "(unverified)" in text
    assert "reason=(Dependency) exit=-" in text and "limit=15:00" in text
    cli.main(["--bundle-file", str(path), "--cached", "--json", "--color", "always"])
    result = json.loads(capsys.readouterr().out)[0]
    assert result["jobs"][2]["reason"] == "(Dependency)"
    assert result["jobs"][2]["explanation"]["freshness"] == "stale"


def test_default_job_rows_hide_historical_reasons_on_completed_jobs(monkeypatch, capsys):
    path = saved_run(jobs={"done": {"id": "101"}})
    mock_scheduler(monkeypatch, accounting="101|COMPLETED|0:0|Dependency")
    cli.main(["--bundle-file", str(path)])
    text = capsys.readouterr().out
    assert "Dependency" not in text and "exit=0:0" not in text
    cli.main(["--bundle-file", str(path), "--details"])
    assert "reason=Dependency exit=0:0" in capsys.readouterr().out


@pytest.mark.parametrize("width", [40, 60, 80, 120, 180])
@pytest.mark.parametrize("color", ["always", "never"])
def test_table_bounds_colors_and_literal_text(width, color):
    text = table(["idx", "job", "status", "reason"], [
        {"idx": "1", "job": "界" * 50, "status": "FAILED", "reason": "bad\n\x1b[31m" + "x" * 100}],
        width=width, color=color)
    assert all(cell_width(line) <= width for line in text.splitlines())
    assert ("\x1b[" in text) == (color == "always")
    assert "\x1b[31m" not in text and "--details" in text


def test_auto_colors_no_color_and_plain_json(monkeypatch, capsys):
    failed_run()
    failed_observation(monkeypatch)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.delenv("NO_COLOR", raising=False)
    cli.main([])
    assert "\x1b[38;2;220;0;0mFAILED\x1b[0m" in capsys.readouterr().out
    monkeypatch.setenv("NO_COLOR", "1")
    cli.main([])
    assert "\x1b[" not in capsys.readouterr().out
    cli.main(["--json", "--color", "always"])
    assert json.loads(capsys.readouterr().out)[0]["state"] == "failed"


def test_partial_and_never_checked_views_are_distinct(monkeypatch, capsys):
    path = failed_run()
    cli.main(["--cached"])
    text = capsys.readouterr().out
    assert "not checked" in text and "UNKNOWN" in text
    mock_scheduler(monkeypatch, accounting="101_0|FAILED|1:0|NonZeroExitCode", queue_code=1)
    cli.main([])
    text = capsys.readouterr().out
    assert "FAILED" in text and "partially checked" in text and "unknown" in text
    assert inspect_bundle(path)["freshness"] == "partial"


def test_multiple_runs_share_scheduler_queries_and_preserve_indices(monkeypatch, capsys):
    first = failed_run()
    second = saved_run(name="other", date="20250102000000", jobs={"one": {"id": "103"}})
    calls = failed_observation(monkeypatch)
    inspect_bundles([first, second])
    assert len(calls) == 2
    cli.main([])
    lines = capsys.readouterr().out.splitlines()
    assert lines[1].split()[:2] == ["1", "other"] and lines[2].split()[:2] == ["2", "kepler"]


def test_invalid_array_filter_fails_before_observing(monkeypatch):
    failed_run()
    monkeypatch.setattr("subprocess.run", lambda *a, **k: pytest.fail("Invalid selector queried scheduler"))
    with pytest.raises(SystemExit):
        cli.main(["1", "--array", "bad"])


@pytest.mark.parametrize("options,count", [(["--head"], 10), (["--head", "3"], 3)])
def test_head_limits_latest_run_selection_before_queries(monkeypatch, capsys, options, count):
    for number in range(12):
        saved_run(name=f"run-{number:02}", date=f"202501{number+1:02}000000",
                  jobs={"one": {"id": str(100 + number)}})
    calls = mock_scheduler(monkeypatch, queue="\n".join(f"{100+n}|RUNNING|10:00|None" for n in range(12)))
    cli.main([*options, "--json"])
    views = json.loads(capsys.readouterr().out)
    assert len(views) == count and "run-11" in views[0]["bundle_path"]
    assert "run-00" not in str(views)
    assert len(calls) == 2
    assert set(calls[0][calls[0].index("-j") + 1].split(",")) == {str(100 + n) for n in range(12-count, 12)}
    cli.main([*options, "--cached"])
    assert len(calls) == 2 and "run-11" in capsys.readouterr().out


@pytest.mark.parametrize("options", [["--head", "0"], ["--head", "-1"], ["1", "--head"]])
def test_invalid_head_does_not_observe(monkeypatch, options):
    monkeypatch.setattr("subprocess.run", lambda *a, **k: pytest.fail("Invalid head queried scheduler"))
    with pytest.raises(SystemExit):
        cli.main(options)
