from __future__ import annotations

import json
from datetime import datetime

import pytest

from autoslurm.apps import submit
from autoslurm.storage import ensure_storage_dirs, jobs_dir, set_storage_root


def _write_bundle(filename: str, bundle: dict) -> None:
    (jobs_dir() / filename).write_text(json.dumps(bundle))


def test_submit_latest_uses_most_recent_saved_bundle(tmp_path, monkeypatch):
    storage_root = tmp_path / "storage"
    set_storage_root(storage_root)
    ensure_storage_dirs()

    _write_bundle("bundle_old_20250101000000.json", {"job_old": {"name": "job_old", "script": "run-old", "slurm": {}}})
    _write_bundle("bundle_new_20250102000000.json", {"job_new": {"name": "job_new", "script": "run-new", "slurm": {}}})

    captured = {}

    def fake_machine_config(args=None, machine=None, overrides=None):
        return "local", {"env_command": "source env", "slurm_account": "acc"}

    def fake_submit_jobs(name, machine=None, machine_overrides=None, bundle_path=None):
        captured["name"] = name
        captured["machine"] = machine
        captured["machine_overrides"] = machine_overrides
        captured["bundle_path"] = bundle_path

    monkeypatch.setattr(submit, "machine_config", fake_machine_config)
    monkeypatch.setattr(submit, "submit_jobs", fake_submit_jobs)
    monkeypatch.setattr(
        submit,
        "latest_bundle_summaries",
        lambda desired_date=None: [
            {"bundle": "bundle_old", "date": datetime(2025, 1, 1, 0, 0, 0)},
            {"bundle": "bundle_new", "date": datetime(2025, 1, 2, 0, 0, 0)},
        ],
    )

    submit.main(["--latest"])

    assert captured["name"] == "bundle_new"
    assert captured["machine"] == "local"
    assert captured["bundle_path"] is not None


def test_submit_latest_prefers_most_recent_ready_to_go_snapshot(tmp_path, monkeypatch):
    storage_root = tmp_path / "storage"
    set_storage_root(storage_root)
    ensure_storage_dirs()

    submitted_path = jobs_dir() / "bundle_new_20250102000000.json"
    draft_path = jobs_dir() / "bundle_new_20250103000000.json"
    _write_bundle(
        submitted_path.name,
        {"job_new": {"name": "job_new", "script": "run-new", "id": "123", "_autoslurm_snapshot_kind": "submission"}},
    )
    _write_bundle(
        draft_path.name,
        {"job_new": {"name": "job_new", "script": "run-new", "id": None, "_autoslurm_snapshot_kind": "draft"}},
    )

    captured = {}

    def fake_machine_config(args=None, machine=None, overrides=None):
        return "local", {"env_command": "source env", "slurm_account": "acc"}

    def fake_submit_jobs(name, machine=None, machine_overrides=None, bundle_path=None):
        captured["name"] = name
        captured["bundle_path"] = bundle_path

    monkeypatch.setattr(submit, "machine_config", fake_machine_config)
    monkeypatch.setattr(submit, "submit_jobs", fake_submit_jobs)

    submit.main(["--latest"])

    assert captured["name"] == "bundle_new"
    assert captured["bundle_path"] == draft_path


def test_submit_named_bundle_prefers_most_recent_ready_to_go_snapshot(tmp_path, monkeypatch):
    storage_root = tmp_path / "storage"
    set_storage_root(storage_root)
    ensure_storage_dirs()

    submitted_path = jobs_dir() / "bundle_new_20250102000000.json"
    draft_path = jobs_dir() / "bundle_new_20250103000000.json"
    _write_bundle(
        submitted_path.name,
        {"job_new": {"name": "job_new", "script": "run-new", "id": "123", "_autoslurm_snapshot_kind": "submission"}},
    )
    _write_bundle(
        draft_path.name,
        {"job_new": {"name": "job_new", "script": "run-new", "id": None, "_autoslurm_snapshot_kind": "draft"}},
    )

    captured = {}

    def fake_machine_config(args=None, machine=None, overrides=None):
        return "local", {"env_command": "source env", "slurm_account": "acc"}

    def fake_submit_jobs(name, machine=None, machine_overrides=None, bundle_path=None):
        captured["name"] = name
        captured["bundle_path"] = bundle_path

    monkeypatch.setattr(submit, "machine_config", fake_machine_config)
    monkeypatch.setattr(submit, "submit_jobs", fake_submit_jobs)

    submit.main(["bundle_new"])

    assert captured["name"] == "bundle_new"
    assert captured["bundle_path"] == draft_path


def test_submit_latest_rejects_bundle_name(tmp_path, monkeypatch):
    storage_root = tmp_path / "storage"
    set_storage_root(storage_root)
    ensure_storage_dirs()

    _write_bundle("bundle_new_20250102000000.json", {"job_new": {"name": "job_new", "script": "run-new", "slurm": {}}})

    def fake_machine_config(args=None, machine=None, overrides=None):
        return "local", {"env_command": "source env", "slurm_account": "acc"}

    monkeypatch.setattr(submit, "machine_config", fake_machine_config)

    with pytest.raises(SystemExit, match="does not take a bundle name"):
        submit.main(["bundle_new", "--latest"])


def test_submit_index_uses_snapshot_path_even_with_duplicate_bundle_name(tmp_path, monkeypatch):
    storage_root = tmp_path / "storage"
    set_storage_root(storage_root)
    ensure_storage_dirs()

    old_path = jobs_dir() / "recovery_20250101000000.json"
    new_path = jobs_dir() / "recovery_20250102000000.json"
    _write_bundle(old_path.name, {"job_old": {"name": "job_old", "script": "run-old", "slurm": {}}})
    _write_bundle(new_path.name, {"job_new": {"name": "job_new", "script": "run-new", "slurm": {}}})

    captured = {}

    def fake_machine_config(args=None, machine=None, overrides=None):
        return "local", {"env_command": "source env", "slurm_account": "acc"}

    def fake_submit_jobs(name, machine=None, machine_overrides=None, bundle_path=None):
        captured["name"] = name
        captured["machine"] = machine
        captured["bundle_path"] = bundle_path

    monkeypatch.setattr(submit, "machine_config", fake_machine_config)
    monkeypatch.setattr(submit, "submit_jobs", fake_submit_jobs)
    monkeypatch.setattr(
        submit,
        "bundle_snapshots",
        lambda desired_date=None: [
            {"bundle": "recovery", "date": datetime(2025, 1, 2, 0, 0, 0), "path": new_path},
            {"bundle": "recovery", "date": datetime(2025, 1, 1, 0, 0, 0), "path": old_path},
        ],
    )

    submit.main(["--index", "2"])

    assert captured["name"] == "recovery"
    assert captured["machine"] == "local"
    assert captured["bundle_path"] == old_path


def test_submit_refuses_broken_bundle_from_index(tmp_path, monkeypatch):
    storage_root = tmp_path / "storage"
    set_storage_root(storage_root)
    ensure_storage_dirs()

    broken_path = jobs_dir() / "recovery_20250103000000.json"
    _write_bundle(
        broken_path.name,
        {"job_a": {"name": "job_a", "script": "run-a", "dependencies": ["missing_job"], "id": None}},
    )

    monkeypatch.setattr(
        submit,
        "bundle_snapshots",
        lambda desired_date=None: [
            {"bundle": "recovery", "date": datetime(2025, 1, 3, 0, 0, 0), "path": broken_path},
        ],
    )

    called = {"submit": False}

    def fake_machine_config(args=None, machine=None, overrides=None):
        return "local", {"env_command": "source env", "slurm_account": "acc"}

    def fake_submit_jobs(name, machine=None, machine_overrides=None, bundle_path=None):
        called["submit"] = True

    monkeypatch.setattr(submit, "machine_config", fake_machine_config)
    monkeypatch.setattr(submit, "submit_jobs", fake_submit_jobs)

    with pytest.raises(SystemExit, match="Refusing to submit broken bundle"):
        submit.main(["--index", "1"])
    assert called["submit"] is False


def test_submit_refuses_broken_bundle_from_name(tmp_path, monkeypatch):
    storage_root = tmp_path / "storage"
    set_storage_root(storage_root)
    ensure_storage_dirs()

    _write_bundle(
        "recovery_20250103000000.json",
        {"job_a": {"name": "job_a", "script": "run-a", "dependencies": ["missing_job"], "id": None}},
    )

    called = {"submit": False}

    def fake_machine_config(args=None, machine=None, overrides=None):
        return "local", {"env_command": "source env", "slurm_account": "acc"}

    def fake_submit_jobs(name, machine=None, machine_overrides=None, bundle_path=None):
        called["submit"] = True

    monkeypatch.setattr(submit, "machine_config", fake_machine_config)
    monkeypatch.setattr(submit, "submit_jobs", fake_submit_jobs)

    with pytest.raises(SystemExit, match="Refusing to submit broken bundle"):
        submit.main(["recovery"])
    assert called["submit"] is False
