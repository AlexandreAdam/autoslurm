"""Historical renderers use exact saved identity and bounded shared observations."""
import pytest
from autoslurm.experiment_context import experiment_context, latest_log_context, job_context
from autoslurm.storage import out_dir, slurm_dir
from tests.inspection_helpers import saved_run, mock_scheduler


def test_human_context_includes_selected_script_and_bound_log(monkeypatch):
    saved_run(jobs={"analysis": {"id": "42"}})
    (slurm_dir() / "analysis_20250101000000.sh").write_text("#!/bin/bash\necho analysis")
    (out_dir() / "analysis-42.out").write_text("analysis completed")
    mock_scheduler(monkeypatch, accounting="42|COMPLETED|0:0|None|42")
    text = experiment_context("study")
    assert "Job or bundle 'study'" in text and "analysis completed" in text and "echo analysis" in text


def test_unsubmitted_draft_does_not_adopt_a_same_name_log():
    saved_run(jobs={"analysis": {"script": "echo analysis"}})
    (out_dir() / "analysis-42.out").write_text("unrelated evidence")
    text = experiment_context("study")
    assert "has not been submitted yet" in text
    assert "unrelated evidence" not in text


@pytest.mark.parametrize("task_suffix", ["123_1", "123.1"])
def test_task_log_uses_saved_parent_and_exact_task(monkeypatch, task_suffix):
    saved_run(jobs={"array": {"id": "123", "slurm": {"array": "0-2"}}})
    (out_dir() / f"array-{task_suffix}.out").write_text("selected task log")
    (out_dir() / "array-999_1.out").write_text("unrelated log")
    mock_scheduler(monkeypatch)
    assert latest_log_context("study", job_name="array", array_task="1") == "selected task log"


def test_scalar_log_does_not_take_newer_unrelated_id(monkeypatch):
    saved_run(jobs={"sample": {"id": "101"}})
    (out_dir() / "sample-101.out").write_text("selected")
    (out_dir() / "sample-999.out").write_text("newer but unrelated")
    mock_scheduler(monkeypatch)
    assert latest_log_context("study", job_name="1") == "selected"


def test_missing_log_is_absent_not_success(monkeypatch):
    saved_run()
    mock_scheduler(monkeypatch)
    assert "No logs found" in latest_log_context("study", job_name="sample")


def test_context_requires_an_exact_run_for_logs():
    with pytest.raises(ValueError, match="exact run"):
        latest_log_context()


def test_script_only_view_never_queries_scheduler():
    saved_run(jobs={"sample": {"script": "echo sample"}})
    (slurm_dir() / "sample_20250101000000.sh").write_text("#!/bin/bash\necho sample")
    text = job_context("study", "1", include_script=True, include_status=False)
    assert "echo sample" in text and "status=" not in text


def test_job_selector_absent_from_snapshot_fails():
    saved_run()
    with pytest.raises(KeyError):
        job_context("study", "absent")


def test_legacy_cli_entry_point_uses_shared_inspection(monkeypatch, capsys):
    from autoslurm.apps import experiment_context as cli
    saved_run()
    mock_scheduler(monkeypatch, queue="101|RUNNING|01:00|None")
    cli.main(["study", "--status"])
    assert "RUNNING" in capsys.readouterr().out
