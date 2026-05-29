from __future__ import annotations

from autoslurm.apps import logs as logs_app


def test_logs_without_args_shows_status_summary(monkeypatch):
    calls: list[list[str] | None] = []

    def fake_status(argv=None):
        calls.append(argv)

    monkeypatch.setattr(logs_app.status, "main", fake_status)
    logs_app.main([])
    assert calls == [[]]


def test_logs_with_args_delegates_to_inspect(monkeypatch):
    calls: list[list[str] | None] = []

    def fake_inspect(argv=None):
        calls.append(argv)

    monkeypatch.setattr(logs_app.inspect, "main", fake_inspect)
    logs_app.main(["my-bundle", "--job", "1", "--logs"])
    assert calls == [["my-bundle", "--job", "1", "--logs"]]
