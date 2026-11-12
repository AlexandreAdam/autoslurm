import json
import os
from datetime import datetime
from pathlib import Path
import re
import subprocess
import sys

import pytest

from autoslurm import list_saved_bundles, load_bundle_from_path, save_bundle, submit_jobs
from autoslurm.storage import jobs_dir, out_dir, storage_root
from autoslurm.utils import save_config


EXAMPLE = Path(__file__).resolve().parents[2] / "examples/reference_client"


@pytest.fixture
def science_client(tmp_path, monkeypatch):
    # Same launcher as the example package's installed console entry point.
    commands = tmp_path / "bin"
    commands.mkdir()
    launcher = commands / "science-demo"
    launcher.write_text(
        f"#!{sys.executable}\nimport sys\nsys.path.insert(0, {str(EXAMPLE)!r})\n"
        "from science_demo import main\nmain()\n"
    )
    launcher.chmod(0o755)
    monkeypatch.setenv("PATH", str(commands) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    monkeypatch.chdir(EXAMPLE)
    save_config({"machines": {"mock": {"slurm_account": "mock", "env_command": "true", "project_root": str(EXAMPLE)}}, "default_machine": "mock"})


@pytest.mark.local_processes
@pytest.mark.parametrize("fixture", ["single", "array"])
def test_documented_client_workflow(fixture, science_client, monkeypatch):
    bundle_name = f"reference-{fixture}"
    definitions = json.loads((EXAMPLE / f"bundles/{fixture}.json").read_text())
    planned_path = save_bundle(definitions, bundle_name)
    historical_path = jobs_dir() / f"{bundle_name}_20200101000000.json"
    planned_path.rename(historical_path)
    planned_path = historical_path
    planned_bytes = planned_path.read_bytes()
    planned_jobs, _, _ = load_bundle_from_path(planned_path)
    assert all("id" not in job for job in planned_jobs)

    # A newer, different draft must not change the explicitly selected input.
    other_name = "unselected"
    other_path = jobs_dir() / f"{bundle_name}_{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
    other_path.write_text(json.dumps({other_name: {"name": other_name, "script": "must-not-run", "slurm": {}}}))
    calls = []
    real_run = subprocess.run

    def fake_sbatch(command, *args, **kwargs):
        if command[0] == "bash":
            return real_run(command, *args, **kwargs)
        assert command[0] == "sbatch", command
        script = Path(command[-1])
        text = script.read_text()
        job_name = re.search(r"^#SBATCH --job-name=(.+)$", text, re.M).group(1)
        assert job_name != other_name
        job_id = str(100 + len(calls))
        if job_name == "reduce":
            assert command[command.index("--dependency") + 1] == "afterok:100"
        array = re.search(r"^#SBATCH --array=(\d+)-(\d+)$", text, re.M)
        indices = range(int(array[1]), int(array[2]) + 1) if array else [None]
        for index in indices:
            env = dict(os.environ)
            if index is not None:
                env["SLURM_ARRAY_TASK_ID"] = str(index)
            result = real_run(["bash", str(script)], env=env, capture_output=True, text=True)
            log_name = f"{job_name}-{job_id}" + (f"_{index}" if index is not None else "") + ".out"
            (out_dir() / log_name).write_text(result.stdout + result.stderr)
            assert result.returncode == 0, result.stderr
        calls.append((job_name, job_id))
        return subprocess.CompletedProcess(command, 0, f"Submitted batch job {job_id}\n", "")

    monkeypatch.setattr("subprocess.run", fake_sbatch)
    submit_jobs(bundle_name, machine="mock", bundle_path=planned_path)
    # The input file is retained separately from the new submission snapshot.
    assert planned_path.read_bytes() == planned_bytes
    records = []
    for entry in list_saved_bundles(bundle_name=bundle_name):
        jobs, _, _ = load_bundle_from_path(entry["path"])
        if any("id" in job for job in jobs):
            records.append((entry, jobs))
    assert len(records) == 1
    record, submitted = records[0]
    assert {job["name"]: job["id"] for job in submitted} == dict(calls)
    assert all(job["machine"] == "mock" for job in submitted)
    assert record["path"] != planned_path
    summary_path = storage_root() / "results" / ("reference-single/summary.json" if fixture == "single" else "reference-array/summary/summary.json")
    summary = json.loads(summary_path.read_text())
    assert summary["sum_squares"] == 30
    assert summary["count"] == 4
    if fixture == "array":
        assert [name for name, _ in calls] == ["shards", "reduce"]
        assert len(list((storage_root() / "results/reference-array/parts").glob("part-*.json"))) == 4


@pytest.mark.local_processes
def test_reference_client_reports_missing_input_and_incomplete_reduction(tmp_path):
    command = [sys.executable, str(EXAMPLE / "science_demo.py")]
    missing = subprocess.run(command + ["--mode", "single", "--input-file", "missing.json", "--output-dir", str(tmp_path / "single")], cwd=tmp_path, capture_output=True, text=True)
    assert missing.returncode == 1
    assert "science-demo:" in missing.stderr
    assert not (tmp_path / "single/summary.json").exists()
    incomplete = subprocess.run(command + ["--mode", "reduce", "--input-file", str(EXAMPLE / "data/measurements.json"), "--parts-dir", str(tmp_path / "missing-parts"), "--output-dir", str(tmp_path / "reduce")], capture_output=True, text=True)
    assert incomplete.returncode == 1
    assert "part-0.json" in incomplete.stderr
    assert not (tmp_path / "reduce/summary.json").exists()
    parts = tmp_path / "mixed-parts"
    parts.mkdir()
    (parts / "part-0.json").write_text(json.dumps({"index": 0, "square": 1, "input_sha256": "different-input"}))
    mixed = subprocess.run(command + ["--mode", "reduce", "--input-file", str(EXAMPLE / "data/measurements.json"), "--parts-dir", str(parts), "--output-dir", str(tmp_path / "mixed")], capture_output=True, text=True)
    assert mixed.returncode == 1
    assert "does not match the current input" in mixed.stderr
    assert not (tmp_path / "mixed/summary.json").exists()
