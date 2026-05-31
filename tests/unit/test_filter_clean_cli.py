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
            "job_a": {"name": "job_a", "script": "run-a", "id": None, "_autoslurm_snapshot_kind": "submission"},
            "job_b": {"name": "job_b", "script": "run-b", "id": "12345", "_autoslurm_snapshot_kind": "submission"},
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


def test_clean_removes_only_stale_snapshots(tmp_path, capsys, monkeypatch):
    root = tmp_path / "storage"
    set_storage_root(root)
    ensure_storage_dirs()
    _write_config(root)

    stale = jobs_dir() / "recovery_20250101000000.json"
    latest_ready = jobs_dir() / "recovery_20250102000000.json"
    active = jobs_dir() / "recovery_20250103000000.json"
    _write_bundle(
        stale.name,
        {
            "job_a": {"name": "job_a", "script": "run-a", "id": None},
            "job_b": {"name": "job_b", "script": "run-b", "id": None},
        },
    )
    _write_bundle(
        latest_ready.name,
        {
            "job_a": {"name": "job_a", "script": "run-a", "id": None},
            "job_b": {"name": "job_b", "script": "run-b", "id": None},
        },
    )
    _write_bundle(
        active.name,
        {
            "job_a": {"name": "job_a", "script": "run-a", "id": None, "_autoslurm_snapshot_kind": "submission"},
            "job_b": {"name": "job_b", "script": "run-b", "id": "999", "_autoslurm_snapshot_kind": "submission"},
        },
    )

    monkeypatch.setattr(clean_app, "job_status_texts", lambda jobs: {"job_b": "COMPLETED"})

    clean_app.main([])
    preview = capsys.readouterr().out
    assert "Preview only" in preview
    assert str(stale) in preview
    assert stale.exists()
    assert latest_ready.exists()
    assert active.exists()

    clean_app.main(["--yes"])
    final = capsys.readouterr().out
    assert "Removed 2 bundle file(s)." in final
    assert not stale.exists()
    assert not latest_ready.exists()
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
    assert "No matching bundle snapshots found." in final
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


def test_active_prefers_ready_draft_over_ready_submission_artifact(tmp_path, capsys):
    root = tmp_path / "storage"
    set_storage_root(root)
    ensure_storage_dirs()
    _write_config(root)

    _write_bundle(
        "recovery_20250101000000.json",
        {"job_a": {"name": "job_a", "script": "run-a", "id": None, "_autoslurm_snapshot_kind": "submission"}},
    )
    _write_bundle(
        "recovery_20250102000000.json",
        {"job_a": {"name": "job_a", "script": "run-a", "id": None, "_autoslurm_snapshot_kind": "draft"}},
    )

    rows = bundle_snapshots()
    assert len(rows) == 1
    assert rows[0]["state"] == "ready_to_go"
    assert rows[0]["date"].strftime("%Y%m%d%H%M%S") == "20250102000000"


def test_cancelled_snapshots_are_visible_and_cleanable(tmp_path, capsys, monkeypatch):
    root = tmp_path / "storage"
    set_storage_root(root)
    ensure_storage_dirs()
    _write_config(root)

    cancelled = jobs_dir() / "recovery_20250103000000.json"
    _write_bundle(
        cancelled.name,
        {
            "job_a": {
                "name": "job_a",
                "script": "run-a",
                "id": "123",
                "_autoslurm_snapshot_kind": "submission",
            },
        },
    )

    monkeypatch.setattr(
        clean_app,
        "job_status_texts",
        lambda jobs: {"job_a": "CANCELLED"},
    )

    rows = bundle_snapshots()
    assert len(rows) == 1
    assert rows[0]["state"] == "active"

    clean_app.main(["--scope", "cancelled"])
    out = capsys.readouterr().out
    assert "cancelled" in out
    assert str(cancelled) in out


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


def test_clean_scope_failed_targets_fully_failed_submissions(tmp_path, capsys, monkeypatch):
    root = tmp_path / "storage"
    set_storage_root(root)
    ensure_storage_dirs()
    _write_config(root)

    failed_path = jobs_dir() / "failed_bundle_20250101000000.json"
    ok_path = jobs_dir() / "ok_bundle_20250102000000.json"
    _write_bundle(failed_path.name, {"job": {"name": "job", "script": "run", "id": "11"}})
    _write_bundle(ok_path.name, {"job": {"name": "job", "script": "run", "id": "12"}})

    monkeypatch.setattr(
        clean_app,
        "job_status_texts",
        lambda jobs: {"job": "FAILED"} if jobs[0]["id"] == "11" else {"job": "COMPLETED"},
    )

    clean_app.main(["--scope", "failed", "--yes"])
    out = capsys.readouterr().out
    assert "Removed 1 bundle file(s)." in out
    assert not failed_path.exists()
    assert ok_path.exists()


def test_clean_scope_unsubmitted_targets_zero_submission_snapshots(tmp_path, capsys, monkeypatch):
    root = tmp_path / "storage"
    set_storage_root(root)
    ensure_storage_dirs()
    _write_config(root)

    old_draft = jobs_dir() / "draft_bundle_20250101000000.json"
    latest_draft = jobs_dir() / "draft_bundle_20250102000000.json"
    submitted = jobs_dir() / "submitted_bundle_20250103000000.json"
    _write_bundle(old_draft.name, {"job": {"name": "job", "script": "run", "id": None}})
    _write_bundle(latest_draft.name, {"job": {"name": "job", "script": "run", "id": None}})
    _write_bundle(
        submitted.name,
        {"job": {"name": "job", "script": "run", "id": "42", "_autoslurm_snapshot_kind": "submission"}},
    )

    monkeypatch.setattr(clean_app, "job_status_texts", lambda jobs: {"job": "COMPLETED"})

    clean_app.main(["--scope", "unsubmitted", "--yes"])
    out = capsys.readouterr().out
    assert "Removed 2 bundle file(s)." in out
    assert not old_draft.exists()
    assert not latest_draft.exists()
    assert submitted.exists()


def test_clean_target_index_removes_selected_snapshot(tmp_path, capsys):
    root = tmp_path / "storage"
    set_storage_root(root)
    ensure_storage_dirs()
    _write_config(root)

    first = jobs_dir() / "bundle_20250101000000.json"
    second = jobs_dir() / "bundle_20250102000000.json"
    _write_bundle(first.name, {"job": {"name": "job", "script": "run", "id": None}})
    _write_bundle(
        second.name,
        {"job": {"name": "job", "script": "run", "id": "42", "_autoslurm_snapshot_kind": "submission"}},
    )

    # active mode order: second (active) only.
    clean_app.main(["1"])
    preview = capsys.readouterr().out
    assert "Preview only" in preview
    assert str(second) in preview
    assert second.exists()

    clean_app.main(["1", "--yes"])
    final = capsys.readouterr().out
    assert "Removed 1 bundle file(s)." in final
    assert first.exists()
    assert not second.exists()


def test_clean_target_range_removes_multiple_snapshots(tmp_path, capsys):
    root = tmp_path / "storage"
    set_storage_root(root)
    ensure_storage_dirs()
    _write_config(root)

    a = jobs_dir() / "bundle_20250101000000.json"
    b = jobs_dir() / "bundle_20250102000000.json"
    c = jobs_dir() / "bundle_20250103000000.json"
    _write_bundle(a.name, {"job": {"name": "job", "script": "run", "id": None}})
    _write_bundle(b.name, {"job": {"name": "job", "script": "run", "id": None}})
    _write_bundle(
        c.name,
        {"job": {"name": "job", "script": "run", "id": "42", "_autoslurm_snapshot_kind": "submission"}},
    )

    clean_app.main(["1", "--yes"])
    final = capsys.readouterr().out
    assert "Removed 1 bundle file(s)." in final
    assert not c.exists()
    assert b.exists()
    assert a.exists()
