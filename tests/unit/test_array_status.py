from __future__ import annotations

from autoslurm.array_status import declared_array_size, status_for_job_id


def test_status_for_job_id_keeps_non_array_behavior():
    assert status_for_job_id("123", {"123": "RUNNING"}) == "RUNNING"
    assert status_for_job_id("123", {}) == "UNKNOWN"


def test_status_for_job_id_array_all_completed():
    raw = {
        "123": "RUNNING",
        "123_1": "COMPLETED",
        "123_2": "COMPLETED",
    }
    assert status_for_job_id("123", raw) == "COMPLETED"


def test_status_for_job_id_array_failure_wins():
    raw = {
        "123_1": "COMPLETED",
        "123_2": "FAILED",
        "123_3": "PENDING",
    }
    assert status_for_job_id("123", raw) == "FAILED"


def test_status_for_job_id_array_cancelled_wins_over_completion():
    raw = {
        "123_1": "COMPLETED",
        "123_2": "CANCELLED",
        "123_3": "PENDING",
    }
    assert status_for_job_id("123", raw) == "CANCELLED"


def test_status_for_job_id_array_running_when_active_tasks_exist():
    raw = {
        "123_1": "COMPLETED",
        "123_2": "RUNNING",
        "123_3": "PENDING",
    }
    assert status_for_job_id("123", raw) == "RUNNING"


def test_status_for_job_id_array_pending_when_only_pending():
    raw = {
        "123_1": "PENDING",
        "123_2": "PENDING",
    }
    assert status_for_job_id("123", raw) == "PENDING"


def test_status_for_job_id_array_partial_completion_uses_declared_total():
    raw = {
        "123": "RUNNING",
        "123_1": "COMPLETED",
        "123_2": "COMPLETED",
    }
    assert status_for_job_id("123", raw, declared_total=4) == "RUNNING"


def test_declared_array_size_parses_common_specs():
    assert declared_array_size("1-4") == 4
    assert declared_array_size("1-10%6") == 10
    assert declared_array_size("1-10:2") == 5
    assert declared_array_size("1,3,5-9") == 7


def test_declared_array_size_returns_none_for_invalid_specs():
    assert declared_array_size(None) is None
    assert declared_array_size("") is None
    assert declared_array_size("abc") is None
    assert declared_array_size("5-1") is None
