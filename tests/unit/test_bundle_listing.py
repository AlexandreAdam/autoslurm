from __future__ import annotations

import json
from datetime import datetime

from autoslurm.apps import experiment_context
from autoslurm.save_load_jobs import list_saved_bundles
from autoslurm.storage import ensure_storage_dirs, jobs_dir, set_storage_root


def _write_bundle(filename: str, jobs: dict) -> None:
    path = jobs_dir() / filename
    path.write_text(json.dumps(jobs))


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


def test_context_list_mode_prints_bundle_summary(tmp_path, capsys):
    set_storage_root(tmp_path / "storage")
    ensure_storage_dirs()

    _write_bundle("job_a_20250102000000.json", {"job_a": {"script": "run-a"}})
    _write_bundle("job_b_20250103000000.json", {"job_b": {"script": "run-b"}})
    _write_bundle("job_c_20250105000000.json", {"job_c": {"script": "run-c"}})

    experiment_context.main(["--list", "--date", "2025-01-03T00:00:00"])
    output = capsys.readouterr().out

    first = output.splitlines()[0]
    assert "job_b" in first
    assert "jobs=job_b" in output
    assert "job_a" in output
    assert "job_c" in output


def test_context_list_mode_accepts_partial_date_components(tmp_path, capsys):
    set_storage_root(tmp_path / "storage")
    ensure_storage_dirs()

    _write_bundle("job_a_20250102000000.json", {"job_a": {"script": "run-a"}})
    _write_bundle("job_b_20250103000000.json", {"job_b": {"script": "run-b"}})
    _write_bundle("job_c_20250105000000.json", {"job_c": {"script": "run-c"}})

    experiment_context.main(["--list", "--year", "2025", "--month", "1"])
    output = capsys.readouterr().out

    assert "job_a" in output
    assert "job_b" in output
    assert "job_c" in output
