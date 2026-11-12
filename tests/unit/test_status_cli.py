"""CLI behavior checked against saved snapshots and the real shared view."""
import json
import pytest
from autoslurm.apps import status
from autoslurm.utils import save_config
from tests.inspection_helpers import saved_run, mock_scheduler


@pytest.fixture
def runs(monkeypatch):
    save_config({"machines": {"local": {}}, "default_machine": "local", "bundle_filter_mode": "all"})
    old = saved_run("study", "20250101000000")
    new = saved_run("study", "20250102000000", {"sample": {"id": "102"}})
    calls = mock_scheduler(monkeypatch, queue="102|RUNNING|00:10:00|None", accounting="101|COMPLETED|0:0|None|101")
    return old, new, calls


def test_summary_keeps_two_snapshots_and_batches_queries(runs, capsys):
    status.main([])
    text = capsys.readouterr().out
    assert text.count("study") == 2
    assert "unknown" in text.splitlines()[0]
    assert "running" in text and "completed" in text
    assert len(runs[2]) == 2


@pytest.mark.parametrize("selector", [["1"], ["study"], ["--bundle-file", "PATH"]])
def test_detail_resolves_to_the_exact_latest_snapshot(runs, selector, capsys):
    status.main([str(runs[1]) if value == "PATH" else value for value in selector])
    text = capsys.readouterr().out
    assert "102" in text and "RUNNING" in text and "2025-01-02" in text
    assert "101 " not in text


def test_multiple_indices_and_ranges_keep_requested_order(runs, capsys):
    status.main(["2", "1-2"])
    text = capsys.readouterr().out
    assert text.index("2025-01-01") < text.index("2025-01-02")
    assert text.count("Observation:") == 2
    assert len(runs[2]) == 2


def test_partial_date_components_select_historical_snapshot(runs, capsys):
    status.main(["study", "--year", "2025", "--month", "1", "--day", "1", "--json"])
    view = json.loads(capsys.readouterr().out)[0]
    assert view["bundle_path"] == str(runs[0])
    assert view["state"] == "completed"


def test_exact_missing_file_never_selects_a_neighbor(runs, capsys):
    status.main(["--bundle-file", str(runs[0]) + ".missing", "--json"])
    view = json.loads(capsys.readouterr().out)[0]
    assert view["state"] == "broken" and view["errors"]


@pytest.mark.parametrize("array_filter", [[], ["0"], ["1-2"]])
def test_array_indices_and_filters_keep_unknown_tasks(monkeypatch, capsys, array_filter):
    path = saved_run(jobs={"array": {"id": "101", "slurm": {"array": "0-2"}}})
    mock_scheduler(monkeypatch, accounting="101_0|COMPLETED|0:0|None|500\n101_1|FAILED|1:0|None|501")
    status.main(["--bundle-file", str(path), "--array", *array_filter])
    text = capsys.readouterr().out
    for index in ({0, 1, 2} if not array_filter else {0} if array_filter == ["0"] else {1, 2}):
        assert f"101_{index}" in text
    assert "101_3" not in text
    if not array_filter or array_filter == ["1-2"]:
        assert "UNKNOWN" in text


@pytest.mark.parametrize("state", ["COMPLETED", "CANCELLED", "FAILED", "PENDING", "UNKNOWN"])
def test_summary_state_is_shared_with_json(monkeypatch, capsys, state):
    path = saved_run()
    mock_scheduler(monkeypatch, accounting=f"101|{state}|0:0|None|101")
    status.main(["--bundle-file", str(path), "--json"])
    view = json.loads(capsys.readouterr().out)[0]
    assert view["state"] == state.lower()


def test_draft_never_queries_scheduler(monkeypatch, capsys):
    path = saved_run(jobs={"draft": {"script": "echo draft"}})
    calls = mock_scheduler(monkeypatch)
    status.main(["--bundle-file", str(path), "--json"])
    view = json.loads(capsys.readouterr().out)[0]
    assert view["state"] == "ready_to_go"
    assert calls == []


def test_broken_entry_does_not_hide_healthy_entries(runs, capsys):
    broken = runs[1].parent / "broken_20250103000000.json"
    broken.write_text('{"bad": {"dependencies": ["absent"]}}')
    status.main(["--json"])
    views = json.loads(capsys.readouterr().out)
    assert len(views) == 3
    assert any(view["state"] == "broken" for view in views)
    assert any(view["state"] == "completed" for view in views)
