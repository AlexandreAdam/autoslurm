from __future__ import annotations

from datetime import datetime

from autoslurm.apps import status


def test_status_prints_numbered_summary_rows(monkeypatch, capsys):
    monkeypatch.setattr(
        status,
        "bundle_snapshots",
        lambda desired_date=None: [
            {"bundle": "older", "date": datetime(2025, 1, 1, 0, 0, 0), "job_count": 1},
            {"bundle": "newer", "date": datetime(2025, 1, 2, 0, 0, 0), "job_count": 2},
        ],
    )
    monkeypatch.setattr(status, "load_bundle", lambda bundle_name, desired_date=None: ([], {}, desired_date))
    monkeypatch.setattr(status, "_job_status_texts", lambda jobs: {})

    status.main([])
    output = capsys.readouterr().out.splitlines()

    assert "idx" in output[0]
    assert output[1].startswith("1")
    assert "newer" in output[1]
    assert output[2].startswith("2")
    assert "older" in output[2]


def test_status_index_selects_bundle_detail(monkeypatch, capsys):
    monkeypatch.setattr(
        status,
        "bundle_snapshots",
        lambda desired_date=None: [
            {"bundle": "older", "date": datetime(2025, 1, 1, 0, 0, 0), "job_count": 1},
            {"bundle": "newer", "date": datetime(2025, 1, 2, 0, 0, 0), "job_count": 2},
        ],
    )
    monkeypatch.setattr(status, "bundle_jobs_context", lambda bundle_name, desired_date=None: f"detail:{bundle_name}")

    status.main(["1"])
    output = capsys.readouterr().out.strip()

    assert output == "Bundle: newer\n\ndetail:newer"


def test_status_forwards_reference_date(monkeypatch, capsys):
    seen = {"value": None}
    monkeypatch.setattr(status, "load_bundle", lambda bundle_name, desired_date=None: ([], {}, desired_date))
    monkeypatch.setattr(status, "_job_status_texts", lambda jobs: {})

    def fake_bundle_snapshots(desired_date=None):
        seen["value"] = desired_date
        return [{"bundle": "experiment", "date": datetime(2025, 1, 1, 0, 0, 0), "job_count": 1}]

    monkeypatch.setattr(status, "bundle_snapshots", fake_bundle_snapshots)
    status.main(["--year", "2025", "--month", "1"])
    capsys.readouterr()

    assert seen["value"] is not None
    assert seen["value"].year == 2025
    assert seen["value"].month == 1


def test_status_keeps_multiple_snapshots_with_same_name(monkeypatch, capsys):
    monkeypatch.setattr(
        status,
        "bundle_snapshots",
        lambda desired_date=None: [
            {"bundle": "recovery", "date": datetime(2025, 1, 3, 0, 0, 0), "job_count": 2},
            {"bundle": "recovery", "date": datetime(2025, 1, 2, 0, 0, 0), "job_count": 3},
            {"bundle": "other", "date": datetime(2025, 1, 1, 0, 0, 0), "job_count": 1},
        ],
    )
    monkeypatch.setattr(status, "load_bundle", lambda bundle_name, desired_date=None: ([], {}, desired_date))
    monkeypatch.setattr(status, "_job_status_texts", lambda jobs: {})

    status.main([])
    lines = capsys.readouterr().out.splitlines()
    recovery_rows = [line for line in lines if "recovery" in line]
    assert len(recovery_rows) == 2


def test_status_supports_multiple_indices_and_range_in_order(monkeypatch, capsys):
    monkeypatch.setattr(
        status,
        "bundle_snapshots",
        lambda desired_date=None: [
            {"bundle": "b3", "date": datetime(2025, 1, 3, 0, 0, 0), "job_count": 1},
            {"bundle": "b2", "date": datetime(2025, 1, 2, 0, 0, 0), "job_count": 1},
            {"bundle": "b1", "date": datetime(2025, 1, 1, 0, 0, 0), "job_count": 1},
        ],
    )
    monkeypatch.setattr(status, "bundle_jobs_context", lambda bundle_name, desired_date=None: f"detail:{bundle_name}")

    status.main(["2", "1-2"])
    output = capsys.readouterr().out

    assert "Bundle: b2" in output
    assert "Bundle: b3" in output
    assert output.find("Bundle: b2") < output.find("Bundle: b3")


def test_status_summary_includes_bundle_status(monkeypatch, capsys):
    monkeypatch.setattr(
        status,
        "bundle_snapshots",
        lambda desired_date=None: [
            {"bundle": "broken_bundle", "date": datetime(2025, 1, 4, 0, 0, 0), "job_count": 1, "state": "broken"},
        ],
    )
    monkeypatch.setattr(status, "load_bundle", lambda bundle_name, desired_date=None: ([], {}, desired_date))
    monkeypatch.setattr(status, "_job_status_texts", lambda jobs: {})

    status.main([])
    output = capsys.readouterr().out
    assert "status" in output.splitlines()[0]
    assert "broken" in output


def test_status_summary_marks_ready_to_go_for_unsubmitted_valid_bundle(monkeypatch, capsys):
    monkeypatch.setattr(
        status,
        "bundle_snapshots",
        lambda desired_date=None: [
            {"bundle": "draft_bundle", "date": datetime(2025, 1, 5, 0, 0, 0), "job_count": 1, "state": "ready_to_go"},
        ],
    )
    monkeypatch.setattr(
        status,
        "load_bundle",
        lambda bundle_name, desired_date=None: (
            [{"name": "job_a", "id": None}],
            {},
            desired_date,
        ),
    )
    monkeypatch.setattr(status, "_job_status_texts", lambda jobs: {"job_a": "not_submitted"})

    status.main([])
    output = capsys.readouterr().out
    assert "ready_to_go" in output


def test_status_summary_colors_completed_and_broken(monkeypatch, capsys):
    monkeypatch.setattr(
        status,
        "bundle_snapshots",
        lambda desired_date=None: [
            {"bundle": "broken_bundle", "date": datetime(2025, 1, 4, 0, 0, 0), "job_count": 1, "state": "broken"},
            {"bundle": "done_bundle", "date": datetime(2025, 1, 5, 0, 0, 0), "job_count": 1, "state": "active"},
        ],
    )

    def fake_load_bundle(bundle_name, desired_date=None):
        if bundle_name == "done_bundle":
            return ([{"name": "job_a", "id": "123"}], {}, desired_date)
        raise RuntimeError("broken")

    monkeypatch.setattr(status, "load_bundle", fake_load_bundle)
    monkeypatch.setattr(status, "_job_status_texts", lambda jobs: {"job_a": "COMPLETED"})

    status.main([])
    output = capsys.readouterr().out
    assert "\x1b[38;2;220;0;0mbroken\x1b[0m" in output
    assert "\x1b[38;2;0;200;0mcompleted\x1b[0m" in output
