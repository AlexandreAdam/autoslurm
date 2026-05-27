from __future__ import annotations

from pathlib import Path
from datetime import datetime

from autoslurm.apps import cancel as cancel_app


def test_cancel_formats_completed_as_success(monkeypatch, capsys):
    jobs = [
        {"name": "job_done", "id": "123", "machine": None},
    ]
    monkeypatch.setattr(cancel_app, "load_bundle_from_path", lambda path: (jobs, {}, None))
    monkeypatch.setattr(cancel_app, "job_status_texts", lambda jobs: {"job_done": "COMPLETED"})

    seen = {"ids": None}
    monkeypatch.setattr(cancel_app, "_cancel_local", lambda ids: seen.__setitem__("ids", ids))

    cancel_app.main(
        ["--bundle-file", str(Path("/tmp/fake_bundle_20250101000000.json")), "--status-filter", "submitted", "--yes"]
    )
    capsys.readouterr()
    assert seen["ids"] == ["123"]


def test_cancel_all_filter_uses_cancellable_states(monkeypatch, capsys):
    jobs = [
        {"name": "job_done", "id": "123", "machine": None},
        {"name": "job_running", "id": "124", "machine": None},
    ]
    monkeypatch.setattr(cancel_app, "load_bundle_from_path", lambda path: (jobs, {}, None))
    monkeypatch.setattr(
        cancel_app,
        "job_status_texts",
        lambda jobs: {"job_done": "COMPLETED", "job_running": "RUNNING"},
    )

    seen = {"ids": None}
    monkeypatch.setattr(cancel_app, "_cancel_local", lambda ids: seen.__setitem__("ids", ids))

    cancel_app.main(["--bundle-file", str(Path("/tmp/fake_bundle_20250101000000.json")), "--yes"])
    capsys.readouterr()
    assert seen["ids"] == ["124"]


def test_cancel_bundle_target_prints_shared_status_context(monkeypatch, capsys):
    jobs = [
        {"name": "job_running", "id": "124", "machine": None},
    ]
    saved_date = datetime(2025, 1, 1, 0, 0, 0)
    monkeypatch.setattr(
        cancel_app,
        "bundle_snapshots",
        lambda desired_date=None: [{"bundle": "recovery", "date": saved_date}],
    )
    monkeypatch.setattr(cancel_app, "load_bundle", lambda name, date=None: (jobs, {}, saved_date))
    monkeypatch.setattr(cancel_app, "bundle_jobs_context", lambda *args, **kwargs: "SHARED_STATUS_VIEW")
    monkeypatch.setattr(
        cancel_app,
        "bundle_job_rows",
        lambda *args, **kwargs: (saved_date, [{"job_id_raw": "124", "machine_name": None}]),
    )
    monkeypatch.setattr(cancel_app, "job_status_texts", lambda jobs: {"job_running": "RUNNING"})

    cancel_app.main(["1"])
    out = capsys.readouterr().out
    assert "SHARED_STATUS_VIEW" in out
