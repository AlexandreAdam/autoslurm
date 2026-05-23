from __future__ import annotations

import json

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

    submit.main(["--latest"])

    assert captured["name"] == "bundle_new"
    assert captured["machine"] == "local"
    assert captured["bundle_path"] is None


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
