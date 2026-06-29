from __future__ import annotations

import re
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
    monkeypatch.setattr(status, "load_bundle", lambda bundle_name, desired_date=None: ([], {}, desired_date))
    monkeypatch.setattr(
        status,
        "bundle_job_rows_from_jobs",
        lambda jobs, bundle_date, **kwargs: (bundle_date, []),
    )
    monkeypatch.setattr(
        status,
        "bundle_jobs_context_from_rows",
        lambda bundle_name, bundle_date, rows, **kwargs: f"detail:{bundle_name}",
    )

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
    monkeypatch.setattr(status, "load_bundle", lambda bundle_name, desired_date=None: ([], {}, desired_date))
    monkeypatch.setattr(
        status,
        "bundle_job_rows_from_jobs",
        lambda jobs, bundle_date, **kwargs: (bundle_date, []),
    )
    monkeypatch.setattr(
        status,
        "bundle_jobs_context_from_rows",
        lambda bundle_name, bundle_date, rows, **kwargs: f"detail:{bundle_name}",
    )

    status.main(["2", "1-2"])
    output = capsys.readouterr().out

    assert "Bundle: b2" in output
    assert "Bundle: b3" in output
    assert output.find("Bundle: b2") < output.find("Bundle: b3")


def test_status_array_filter_is_forwarded_to_bundle_detail(monkeypatch, capsys):
    monkeypatch.setattr(
        status,
        "bundle_snapshots",
        lambda desired_date=None: [
            {"bundle": "array_bundle", "date": datetime(2025, 1, 1, 0, 0, 0), "job_count": 1},
        ],
    )
    captured = {"kwargs": None}
    monkeypatch.setattr(status, "load_bundle", lambda bundle_name, desired_date=None: ([], {}, desired_date))
    monkeypatch.setattr(
        status,
        "bundle_job_rows_from_jobs",
        lambda jobs, bundle_date, **kwargs: (
            captured.__setitem__("kwargs", kwargs) or bundle_date,
            [],
        ),
    )
    monkeypatch.setattr(
        status,
        "bundle_jobs_context_from_rows",
        lambda bundle_name, bundle_date, rows, **kwargs: f"detail:{bundle_name}:{kwargs}",
    )

    status.main(["1", "--array", "2-3"])
    output = capsys.readouterr().out

    assert "Bundle: array_bundle" in output
    assert captured["kwargs"] is not None
    assert captured["kwargs"]["show_array_tasks"] is True
    assert captured["kwargs"]["array_tasks"] == {2, 3}


def test_status_array_detail_uses_declared_zero_based_indices(monkeypatch, capsys):
    monkeypatch.setattr(
        status,
        "bundle_snapshots",
        lambda desired_date=None: [
            {"bundle": "array_bundle", "date": datetime(2025, 1, 1, 0, 0, 0), "job_count": 1},
        ],
    )
    monkeypatch.setattr(
        status,
        "load_bundle",
        lambda bundle_name, desired_date=None: (
            [
                {
                    "name": "array_job",
                    "id": "123",
                    "machine": "remote",
                    "slurm": {"array": "0-2"},
                }
            ],
            {},
            desired_date,
        ),
    )
    monkeypatch.setattr(
        status,
        "_fetch_statuses_and_time_left_for_job_ids",
        lambda job_ids, machine_name: ({"123": "PENDING"}, {}),
    )

    status.main(["1", "--array"])
    output = re.sub(r"\x1b\[[0-9;]*m", "", capsys.readouterr().out)

    assert "123_0" in output
    assert "123_1" in output
    assert "123_2" in output
    assert "123_3" not in output


def test_status_array_detail_keeps_parent_row_when_failed_tasks_are_unknown(monkeypatch, capsys):
    monkeypatch.setattr(
        status,
        "bundle_snapshots",
        lambda desired_date=None: [
            {"bundle": "array_bundle", "date": datetime(2025, 1, 1, 0, 0, 0), "job_count": 1},
        ],
    )
    monkeypatch.setattr(
        status,
        "load_bundle",
        lambda bundle_name, desired_date=None: (
            [
                {
                    "name": "array_job",
                    "id": "123",
                    "machine": "remote",
                    "slurm": {"array": "0-2"},
                }
            ],
            {},
            desired_date,
        ),
    )
    monkeypatch.setattr(
        status,
        "_fetch_statuses_and_time_left_for_job_ids",
        lambda job_ids, machine_name: ({"123": "FAILED"}, {}),
    )

    status.main(["1", "--array"])
    output = re.sub(r"\x1b\[[0-9;]*m", "", capsys.readouterr().out)

    assert "123 " in output
    assert "123_0" not in output
    assert "123_1" not in output
    assert "123_2" not in output


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
    monkeypatch.setattr(
        status,
        "_fetch_statuses_and_time_left_for_job_ids",
        lambda job_ids, machine_name: ({"123": "COMPLETED"}, {"123": "00:10:00"}),
    )

    status.main([])
    output = capsys.readouterr().out
    assert "\x1b[38;2;220;0;0mbroken\x1b[0m" in output
    assert "\x1b[38;2;0;200;0mcompleted\x1b[0m" in output


def test_status_summary_marks_cancelled(monkeypatch, capsys):
    monkeypatch.setattr(
        status,
        "bundle_snapshots",
        lambda desired_date=None: [
            {"bundle": "cancelled_bundle", "date": datetime(2025, 1, 6, 0, 0, 0), "job_count": 1, "state": "active"},
        ],
    )
    monkeypatch.setattr(
        status,
        "load_bundle",
        lambda bundle_name, desired_date=None: ([{"name": "job_a", "id": "123"}], {}, desired_date),
    )
    monkeypatch.setattr(
        status,
        "_fetch_statuses_and_time_left_for_job_ids",
        lambda job_ids, machine_name: ({"123": "CANCELLED"}, {"123": "-"}),
    )

    status.main([])
    output = capsys.readouterr().out
    assert "cancelled" in output
    assert "\x1b[38;2;220;0;0mcancelled\x1b[0m" in output


def test_status_summary_marks_cancelled_from_slurm_state(monkeypatch, capsys):
    monkeypatch.setattr(
        status,
        "bundle_snapshots",
        lambda desired_date=None: [
            {"bundle": "cancelled_bundle", "date": datetime(2025, 1, 6, 0, 0, 0), "job_count": 1, "state": "active"},
        ],
    )
    monkeypatch.setattr(
        status,
        "load_bundle",
        lambda bundle_name, desired_date=None: ([{"name": "job_a", "id": "123"}], {}, desired_date),
    )
    monkeypatch.setattr(
        status,
        "_fetch_statuses_and_time_left_for_job_ids",
        lambda job_ids, machine_name: ({"123": "CANCELLED"}, {}),
    )

    status.main([])
    output = capsys.readouterr().out
    assert "cancelled" in output
    assert "\x1b[38;2;220;0;0mcancelled\x1b[0m" in output


def test_status_summary_counts_array_task_states(monkeypatch, capsys):
    monkeypatch.setattr(
        status,
        "bundle_snapshots",
        lambda desired_date=None: [
            {"bundle": "array_bundle", "date": datetime(2025, 1, 7, 0, 0, 0), "job_count": 1, "state": "active"},
        ],
    )
    monkeypatch.setattr(
        status,
        "load_bundle",
        lambda bundle_name, desired_date=None: (
            [
                {
                    "name": "array_job",
                    "id": "123",
                    "machine": "remote",
                    "slurm": {"array": "1-3"},
                }
            ],
            {},
            desired_date,
        ),
    )
    monkeypatch.setattr(
        status,
        "_fetch_statuses_and_time_left_for_job_ids",
        lambda job_ids, machine_name: (
            {
                "123_1": "COMPLETED",
                "123_2": "FAILED",
                "123_3": "RUNNING",
            },
            {},
        ),
    )

    status.main([])
    output = capsys.readouterr().out
    lines = [line for line in output.splitlines() if line.strip()]
    header = re.sub(r"\x1b\[[0-9;]*m", "", lines[0])
    row = re.sub(r"\x1b\[[0-9;]*m", "", next(line for line in lines if "array_bundle" in line))
    header_fields = re.split(r"\s{2,}", header.strip())
    row_fields = re.split(r"\s{2,}", row.strip())

    assert header_fields == [
        "idx",
        "bundle",
        "status",
        "saved",
        "jobs",
        "array",
        "pending",
        "running",
        "success",
        "failed",
        "cancelled",
    ]
    assert row_fields[1] == "array_bundle"
    assert row_fields[5] == "3"
    assert row_fields[6] == "0"
    assert row_fields[7] == "1"
    assert row_fields[8] == "1"
    assert row_fields[9] == "1"


def test_status_summary_does_not_count_parent_array_failure_as_every_task(monkeypatch, capsys):
    monkeypatch.setattr(
        status,
        "bundle_snapshots",
        lambda desired_date=None: [
            {"bundle": "array_bundle", "date": datetime(2025, 1, 7, 0, 0, 0), "job_count": 1, "state": "active"},
        ],
    )
    monkeypatch.setattr(
        status,
        "load_bundle",
        lambda bundle_name, desired_date=None: (
            [
                {
                    "name": "array_job",
                    "id": "123",
                    "machine": "remote",
                    "slurm": {"array": "0-19"},
                }
            ],
            {},
            desired_date,
        ),
    )
    monkeypatch.setattr(
        status,
        "_fetch_statuses_and_time_left_for_job_ids",
        lambda job_ids, machine_name: ({"123": "FAILED"}, {}),
    )

    status.main([])
    output = capsys.readouterr().out
    lines = [line for line in output.splitlines() if line.strip()]
    header = re.sub(r"\x1b\[[0-9;]*m", "", lines[0])
    row = re.sub(r"\x1b\[[0-9;]*m", "", next(line for line in lines if "array_bundle" in line))
    header_fields = re.split(r"\s{2,}", header.strip())
    row_fields = re.split(r"\s{2,}", row.strip())

    assert header_fields[5] == "array"
    assert header_fields[9] == "failed"
    assert row_fields[5] == "20"
    assert row_fields[9] == "1"


def test_status_summary_prefers_cancelled_over_running_for_mixed_array_states(monkeypatch, capsys):
    monkeypatch.setattr(
        status,
        "bundle_snapshots",
        lambda desired_date=None: [
            {"bundle": "mixed_bundle", "date": datetime(2025, 1, 8, 0, 0, 0), "job_count": 1, "state": "active"},
        ],
    )
    monkeypatch.setattr(
        status,
        "load_bundle",
        lambda bundle_name, desired_date=None: (
            [
                {
                    "name": "array_job",
                    "id": "123",
                    "machine": "remote",
                    "slurm": {"array": "1-3"},
                }
            ],
            {},
            desired_date,
        ),
    )
    monkeypatch.setattr(
        status,
        "_fetch_statuses_and_time_left_for_job_ids",
        lambda job_ids, machine_name: (
            {
                "123_1": "CANCELLED",
                "123_2": "COMPLETED",
                "123_3": "PENDING",
            },
            {},
        ),
    )

    status.main([])
    output = capsys.readouterr().out
    assert "mixed_bundle" in output
    assert "cancelled" in output
    assert "running" not in output.splitlines()[1]
    assert "\x1b[38;2;220;0;0mcancelled\x1b[0m" in output


def test_status_summary_batches_remote_queries_across_bundles(monkeypatch, capsys):
    monkeypatch.setattr(
        status,
        "bundle_snapshots",
        lambda desired_date=None: [
            {"bundle": "bundle_a", "date": datetime(2025, 1, 2, 0, 0, 0), "job_count": 1, "state": "active"},
            {"bundle": "bundle_b", "date": datetime(2025, 1, 1, 0, 0, 0), "job_count": 1, "state": "active"},
        ],
    )

    def fake_load_bundle(bundle_name, desired_date=None):
        if bundle_name == "bundle_a":
            return ([{"name": "job_a", "id": "111", "machine": "remote"}], {}, desired_date)
        if bundle_name == "bundle_b":
            return ([{"name": "job_b", "id": "222", "machine": "remote"}], {}, desired_date)
        raise AssertionError(bundle_name)

    monkeypatch.setattr(status, "load_bundle", fake_load_bundle)
    seen = {"fetch": 0}

    def fake_fetch(job_ids, machine_name):
        seen["fetch"] += 1
        assert machine_name == "remote"
        assert sorted(job_ids) == ["111", "222"]
        return {"111": "RUNNING", "222": "PENDING"}, {"111": "00:10:00", "222": "00:20:00"}

    monkeypatch.setattr(status, "_fetch_statuses_and_time_left_for_job_ids", fake_fetch)

    status.main([])
    output = capsys.readouterr().out

    assert seen["fetch"] == 1
    assert "bundle_a" in output
    assert "bundle_b" in output
    assert "running" in output or "completed" in output
