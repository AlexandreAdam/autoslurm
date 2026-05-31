from __future__ import annotations

from datetime import datetime

from autoslurm.apps import inspect as inspect_app


def test_inspect_bundle_defaults_to_status_view(monkeypatch, capsys):
    monkeypatch.setattr(
        inspect_app,
        "bundle_jobs_context",
        lambda bundle, date=None: (
            "bundle_a 2025-01-01T00:00:00\n"
            "Use --job <number|name> to inspect a job.\n"
            "idx id name status\n"
            "1   -  train RUNNING"
        ),
    )

    inspect_app.main(["bundle_a"])
    output = capsys.readouterr().out

    assert "Bundle: bundle_a" in output
    assert "bundle_a 2025-01-01T00:00:00" in output
    assert "Use --job <number|name>" not in output
    assert "idx id name status" in output


def test_inspect_job_prints_latest_job_log(monkeypatch, capsys):
    monkeypatch.setattr(
        inspect_app,
        "latest_log_context",
        lambda bundle, date=None, job_name=None, array_task=None: f"log:{bundle}:{job_name}:{array_task}",
    )

    inspect_app.main(["bundle_a", "--job", "2"])
    output = capsys.readouterr().out.strip()

    assert output == "log:bundle_a:2:None"


def test_inspect_latest_defaults_to_latest_bundle_status(monkeypatch, capsys):
    monkeypatch.setattr(
        inspect_app,
        "bundle_snapshots",
        lambda desired_date=None: [{"bundle": "latest_bundle", "date": datetime(2025, 1, 1, 0, 0, 0)}],
    )
    monkeypatch.setattr(inspect_app, "bundle_jobs_context", lambda bundle, date=None: f"{bundle}\nidx id name status")

    inspect_app.main(["--latest"])
    output = capsys.readouterr().out.strip()

    assert output.startswith("Bundle: latest_bundle")


def test_inspect_bundle_index_uses_latest_first(monkeypatch, capsys):
    monkeypatch.setattr(
        inspect_app,
        "bundle_snapshots",
        lambda desired_date=None: [
            {"bundle": "older", "date": datetime(2025, 1, 1, 0, 0, 0)},
            {"bundle": "newer", "date": datetime(2025, 1, 2, 0, 0, 0)},
        ],
    )
    monkeypatch.setattr(inspect_app, "bundle_jobs_context", lambda bundle, date=None: f"{bundle}\nidx id name status")

    inspect_app.main(["1"])
    output = capsys.readouterr().out.strip()

    assert output.startswith("Bundle: newer")


def test_inspect_supports_multiple_indices_and_range_for_status_view(monkeypatch, capsys):
    monkeypatch.setattr(
        inspect_app,
        "bundle_snapshots",
        lambda desired_date=None: [
            {"bundle": "older", "date": datetime(2025, 1, 1, 0, 0, 0)},
            {"bundle": "newer", "date": datetime(2025, 1, 2, 0, 0, 0)},
            {"bundle": "latest", "date": datetime(2025, 1, 3, 0, 0, 0)},
        ],
    )
    monkeypatch.setattr(inspect_app, "bundle_jobs_context", lambda bundle, date=None: f"{bundle}\nidx id name status")

    inspect_app.main(["2", "1-2"])
    output = capsys.readouterr().out

    assert "Bundle: newer" in output
    assert "Bundle: latest" in output
    assert output.find("Bundle: newer") < output.find("Bundle: latest")


def test_inspect_script_prints_job_script(monkeypatch, capsys):
    monkeypatch.setattr(
        inspect_app,
        "job_context",
        lambda bundle, job, date=None, include_script=False, include_logs=False, include_status=True: (
            f"script:{bundle}:{job}:{include_script}:{include_logs}:{include_status}"
        ),
    )

    inspect_app.main(["bundle_a", "--job", "1", "--script"])
    output = capsys.readouterr().out.strip()

    assert output == "script:bundle_a:1:True:False:False"


def test_inspect_status_prints_job_status(monkeypatch, capsys):
    monkeypatch.setattr(
        inspect_app,
        "job_context",
        lambda bundle, job, date=None, include_script=False, include_logs=False, include_status=True: (
            f"status:{bundle}:{job}:{include_script}:{include_logs}:{include_status}"
        ),
    )

    inspect_app.main(["bundle_a", "--job", "1", "--status"])
    output = capsys.readouterr().out.strip()

    assert output == "status:bundle_a:1:False:False:True"


def test_inspect_logs_flag_aliases_log(monkeypatch, capsys):
    monkeypatch.setattr(
        inspect_app,
        "latest_log_context",
        lambda bundle, date=None, job_name=None, array_task=None: f"log:{bundle}:{job_name}:{array_task}",
    )

    inspect_app.main(["bundle_a", "--job", "2", "--logs"])
    output = capsys.readouterr().out.strip()

    assert output == "log:bundle_a:2:None"


def test_inspect_array_task_passed_to_log_lookup(monkeypatch, capsys):
    monkeypatch.setattr(
        inspect_app,
        "latest_log_context",
        lambda bundle, date=None, job_name=None, array_task=None: f"log:{bundle}:{job_name}:{array_task}",
    )

    inspect_app.main(["bundle_a", "--job", "2", "--array-task", "3", "--log"])
    output = capsys.readouterr().out.strip()

    assert output == "log:bundle_a:2:3"


def test_inspect_array_alias_passed_to_log_lookup(monkeypatch, capsys):
    monkeypatch.setattr(
        inspect_app,
        "latest_log_context",
        lambda bundle, date=None, job_name=None, array_task=None: f"log:{bundle}:{job_name}:{array_task}",
    )

    inspect_app.main(["bundle_a", "--job", "2", "--array", "4", "--log"])
    output = capsys.readouterr().out.strip()

    assert output == "log:bundle_a:2:4"


def test_inspect_requires_bundle_or_latest(capsys):
    inspect_app.main([])
    assert "usage:" in capsys.readouterr().out
