from __future__ import annotations

from autoslurm.apps import root


def test_root_dispatches_action_arguments(monkeypatch):
    calls = []

    def fake_schedule(argv=None):
        calls.append(argv)

    monkeypatch.setitem(root.ACTION_HANDLERS, "schedule", fake_schedule)

    root.main(["schedule", "--time", "00:05:00", "--mem", "1G"])

    assert calls == [["--time", "00:05:00", "--mem", "1G"]]


def test_root_accepts_action_aliases(monkeypatch):
    calls = []

    def fake_context(argv=None):
        calls.append(("context", argv))

    def fake_agent(argv=None):
        calls.append(("agent", argv))

    monkeypatch.setitem(root.ACTION_HANDLERS, "context", fake_context)
    monkeypatch.setitem(root.ACTION_HANDLERS, "agent", fake_agent)

    root.main(["experiment-context", "--date", "20250101"])
    root.main(["agent-context", "--sections", "10_task_schedule.md"])

    assert calls == [
        ("context", ["--date", "20250101"]),
        ("agent", ["--sections", "10_task_schedule.md"]),
    ]


def test_root_help_lists_actions(capsys):
    root.main(["--help"])
    captured = capsys.readouterr()

    assert "autoslurm" in captured.out
    assert "schedule" in captured.out
    assert "submit" in captured.out
    assert "configuration" in captured.out
    assert "context" in captured.out
    assert "agent" in captured.out
