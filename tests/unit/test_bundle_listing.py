from __future__ import annotations

import json
from datetime import datetime

import pytest

from autoslurm.apps import experiment_context
from autoslurm.save_load_jobs import latest_bundle_summaries, list_saved_bundles
from autoslurm.storage import ensure_storage_dirs, jobs_dir, set_storage_root


def _write_bundle(filename: str, jobs: dict) -> None:
    path = jobs_dir() / filename
    path.write_text(json.dumps(jobs))


@pytest.fixture(autouse=True)
def mock_load_config(monkeypatch, tmp_path):
    config = {
        "machines": {
            "local": {
                "path": str(tmp_path / "storage"),
            }
        },
        "default_machine": "local",
    }
    monkeypatch.setattr("autoslurm.save_load_jobs.load_config", lambda: config)
    monkeypatch.setattr("autoslurm.utils.load_config", lambda: config)
    yield config


def test_list_saved_bundles_orders_by_date(tmp_path):
    set_storage_root(tmp_path / "storage")
    ensure_storage_dirs()

    _write_bundle("job_a_20250102000000.json", {"job_a": {"script": "run-a"}})
    _write_bundle("job_b_20250103000000.json", {"job_b": {"script": "run-b"}})
    _write_bundle("job_c_20250105000000.json", {"job_c": {"script": "run-c"}})

    entries = list_saved_bundles(
        desired_date=datetime(2025, 1, 3, 0, 0, 0),
    )

    assert [entry["bundle"] for entry in entries] == ["job_b", "job_a", "job_c"]


def test_latest_bundle_summaries_keep_only_most_recent_snapshot(tmp_path):
    set_storage_root(tmp_path / "storage")
    ensure_storage_dirs()

    _write_bundle("job_a_20250102000000.json", {"job_a": {"script": "run-a"}})
    _write_bundle("job_a_20250106000000.json", {"job_a": {"script": "run-a2"}})
    _write_bundle("job_b_20250103000000.json", {"job_b": {"script": "run-b"}})
    _write_bundle("job_c_20250105000000.json", {"job_c": {"script": "run-c"}})

    entries = latest_bundle_summaries(datetime(2025, 1, 3, 0, 0, 0))

    assert [entry["bundle"] for entry in entries] == ["job_b", "job_c", "job_a"]
    assert entries[-1]["date"] == datetime(2025, 1, 6, 0, 0, 0)


def test_context_list_mode_accepts_partial_date_components(tmp_path, capsys):
    set_storage_root(tmp_path / "storage")
    ensure_storage_dirs()

    _write_bundle("job_a_20250102000000.json", {"job_a": {"script": "run-a"}})
    _write_bundle("job_b_20250103000000.json", {"job_b": {"script": "run-b"}})
    _write_bundle("job_c_20250105000000.json", {"job_c": {"script": "run-c"}})

    experiment_context.main(["--year", "2025", "--month", "1"])
    output = capsys.readouterr().out

    lines = output.splitlines()
    assert lines[0].startswith("job_a ")
    assert all("path=" not in line for line in lines)


def test_context_with_no_args_defaults_to_compact_bundle_index(tmp_path, capsys):
    set_storage_root(tmp_path / "storage")
    ensure_storage_dirs()

    experiment_context.main([])
    output = capsys.readouterr().out

    assert "No saved bundles found." in output


def test_context_job_status_is_compact(tmp_path, monkeypatch, capsys):
    set_storage_root(tmp_path / "storage")
    ensure_storage_dirs()

    bundle = {
        "analysis": {
            "name": "analysis",
            "script": "run-analysis",
            "id": "12345",
            "machine": "local",
            "slurm": {"time": "00:05:00", "mem": "1G", "cpus_per_task": 1},
        }
    }
    _write_bundle("experiment_20250102000000.json", bundle)

    def fake_run(cmd, *args, **kwargs):
        class Result:
            returncode = 0
            stdout = "RUNNING\n"
            stderr = ""

        return Result()

    monkeypatch.setattr("subprocess.run", fake_run)

    experiment_context.main(["experiment", "--job", "analysis"])
    output = capsys.readouterr().out

    assert "analysis" in output
    assert "status=RUNNING" in output
    assert "path=" not in output


def test_context_job_script_view_is_compact(tmp_path, capsys):
    set_storage_root(tmp_path / "storage")
    ensure_storage_dirs()

    bundle = {
        "analysis": {
            "name": "analysis",
            "script": "run-analysis",
            "slurm": {"time": "00:05:00", "mem": "1G", "cpus_per_task": 1},
        }
    }
    _write_bundle("experiment_20250102000000.json", bundle)
    (tmp_path / "storage" / "slurm" / "analysis_20250102000000.sh").write_text(
        "#!/bin/bash\necho analysis"
    )

    experiment_context.main(["experiment", "--job", "analysis", "--script"])
    output = capsys.readouterr().out

    assert "analysis" in output
    assert "#!/bin/bash" in output
    assert "path=" not in output
