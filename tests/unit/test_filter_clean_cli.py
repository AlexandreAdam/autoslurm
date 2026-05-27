from __future__ import annotations

import json

from autoslurm.apps import clean as clean_app
from autoslurm.apps import filter as filter_app
from autoslurm.save_load_jobs import bundle_snapshots
from autoslurm.storage import config_file_path, ensure_storage_dirs, jobs_dir, set_storage_root


def _write_bundle(filename: str, bundle: dict) -> None:
    (jobs_dir() / filename).write_text(json.dumps(bundle))


def _write_config(root) -> None:
    path = config_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "machines": {"local": {"path": str(root)}},
        "default_machine": "local",
        "bundle_filter_mode": "active",
    }
    path.write_text(json.dumps(data))


def test_filter_switch_controls_snapshot_visibility(tmp_path, capsys):
    root = tmp_path / "storage"
    set_storage_root(root)
    ensure_storage_dirs()
    _write_config(root)

    _write_bundle(
        "trial_20250101000000.json",
        {
            "job_a": {"name": "job_a", "script": "run-a", "id": None},
            "job_b": {"name": "job_b", "script": "run-b", "id": None},
        },
    )
    _write_bundle(
        "trial_20250102000000.json",
        {
            "job_a": {"name": "job_a", "script": "run-a", "id": None},
            "job_b": {"name": "job_b", "script": "run-b", "id": "12345"},
        },
    )

    active_rows = bundle_snapshots()
    assert len(active_rows) == 1
    assert active_rows[0]["date"].strftime("%Y%m%d%H%M%S") == "20250102000000"
    assert active_rows[0]["state"] == "active"

    filter_app.main(["all"])
    capsys.readouterr()
    all_rows = bundle_snapshots()
    assert len(all_rows) == 2

    filter_app.main(["active"])
    capsys.readouterr()
    active_rows_again = bundle_snapshots()
    assert len(active_rows_again) == 1


def test_clean_removes_only_stale_snapshots(tmp_path, capsys):
    root = tmp_path / "storage"
    set_storage_root(root)
    ensure_storage_dirs()
    _write_config(root)

    stale = jobs_dir() / "recovery_20250101000000.json"
    active = jobs_dir() / "recovery_20250102000000.json"
    _write_bundle(
        stale.name,
        {
            "job_a": {"name": "job_a", "script": "run-a", "id": None},
            "job_b": {"name": "job_b", "script": "run-b", "id": None},
        },
    )
    _write_bundle(
        active.name,
        {
            "job_a": {"name": "job_a", "script": "run-a", "id": None},
            "job_b": {"name": "job_b", "script": "run-b", "id": "999"},
        },
    )

    clean_app.main([])
    preview = capsys.readouterr().out
    assert "Preview only" in preview
    assert "ready_to_go" in preview
    assert str(stale) in preview
    assert stale.exists()
    assert active.exists()

    clean_app.main(["--yes"])
    final = capsys.readouterr().out
    assert "Removed 1 inactive bundle file(s)." in final
    assert not stale.exists()
    assert active.exists()


def test_broken_dependency_snapshot_visible_in_active_when_no_newer_ready(tmp_path, capsys):
    root = tmp_path / "storage"
    set_storage_root(root)
    ensure_storage_dirs()
    _write_config(root)

    broken = jobs_dir() / "recovery_20250103000000.json"
    _write_bundle(
        broken.name,
        {
            "job_a": {"name": "job_a", "script": "run-a", "dependencies": ["missing_job"], "id": None},
        },
    )

    # Default active mode should include latest broken snapshot when no ready/submitted exists.
    active_rows = bundle_snapshots()
    assert len(active_rows) == 1
    assert active_rows[0]["state"] == "broken"

    # all mode should expose them with explicit state marker.
    filter_app.main(["all"])
    capsys.readouterr()
    all_rows = bundle_snapshots()
    assert len(all_rows) == 1
    assert all_rows[0]["state"] == "broken"

    clean_app.main(["--yes"])
    final = capsys.readouterr().out
    assert "No inactive bundle snapshots found." in final
    assert broken.exists()


def test_active_prefers_latest_ready_to_go_over_broken_for_same_bundle(tmp_path, capsys):
    root = tmp_path / "storage"
    set_storage_root(root)
    ensure_storage_dirs()
    _write_config(root)

    _write_bundle(
        "recovery_20250101000000.json",
        {"job_a": {"name": "job_a", "script": "run-a", "dependencies": ["missing_job"], "id": None}},
    )
    _write_bundle(
        "recovery_20250102000000.json",
        {"job_a": {"name": "job_a", "script": "run-a", "id": None}},
    )

    rows = bundle_snapshots()
    assert len(rows) == 1
    assert rows[0]["state"] == "ready_to_go"
    assert rows[0]["date"].strftime("%Y%m%d%H%M%S") == "20250102000000"

    clean_app.main(["--yes"])
    capsys.readouterr()
    remaining = sorted(path.name for path in jobs_dir().glob("*.json"))
    assert remaining == ["recovery_20250102000000.json"]


def test_filter_prints_current_mode_and_available_modes(tmp_path, capsys):
    root = tmp_path / "storage"
    set_storage_root(root)
    ensure_storage_dirs()
    _write_config(root)

    filter_app.main([])
    out = capsys.readouterr().out
    assert "Current bundle filter:" in out
    assert "- active:" in out
    assert "- all:" in out
