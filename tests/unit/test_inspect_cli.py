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

    assert "bundle_a 2025-01-01T00:00:00" in output
    assert "Use --job <number|name>" not in output
    assert "idx id name status" in output


def test_inspect_job_prints_latest_job_log(monkeypatch, capsys):
    monkeypatch.setattr(inspect_app, "latest_log_context", lambda bundle, date=None, job_name=None: f"log:{bundle}:{job_name}")

    inspect_app.main(["bundle_a", "--job", "2"])
    output = capsys.readouterr().out.strip()

    assert output == "log:bundle_a:2"


def test_inspect_latest_defaults_to_latest_bundle_status(monkeypatch, capsys):
    monkeypatch.setattr(
        inspect_app,
        "latest_bundle_summaries",
        lambda desired_date=None: [{"bundle": "latest_bundle", "date": datetime(2025, 1, 1, 0, 0, 0)}],
    )
    monkeypatch.setattr(inspect_app, "bundle_jobs_context", lambda bundle, date=None: f"{bundle}\nidx id name status")

    inspect_app.main(["--latest"])
    output = capsys.readouterr().out.strip()

    assert output.startswith("latest_bundle")


def test_inspect_bundle_index_uses_latest_first(monkeypatch, capsys):
    monkeypatch.setattr(
        inspect_app,
        "latest_bundle_summaries",
        lambda desired_date=None: [
            {"bundle": "older", "date": datetime(2025, 1, 1, 0, 0, 0)},
            {"bundle": "newer", "date": datetime(2025, 1, 2, 0, 0, 0)},
        ],
    )
    monkeypatch.setattr(inspect_app, "bundle_jobs_context", lambda bundle, date=None: f"{bundle}\nidx id name status")

    inspect_app.main(["1"])
    output = capsys.readouterr().out.strip()

    assert output.startswith("newer")


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


def test_inspect_requires_bundle_or_latest(capsys):
    inspect_app.main([])
    assert "usage:" in capsys.readouterr().out
