"""Preparation can be checked as data transformation without a filesystem/Slurm."""

import copy
from pathlib import Path

import pytest

from autoslurm.bundle_preparation import prepare_bundle
from autoslurm.execution import resolve_execution_context


def test_preparation_has_no_external_effects_and_copies_caller_data(monkeypatch):
    context = resolve_execution_context("mock", {"software_root": "/science", "results_root": "/results"})
    jobs = [{"name": "sample", "script": "science-demo", "slurm": {},
             "input_args": ["input_file"],
             "script_args": {"input_file": "data/input.json", "output_dir": "study", "values": [1, 2]}}]
    graph = {"sample": []}
    original = copy.deepcopy(jobs)
    def no_effects(*args, **kwargs):
        pytest.fail("In-memory preparation performed an external operation")
    monkeypatch.setattr("subprocess.run", no_effects)
    monkeypatch.setattr(Path, "open", no_effects)
    prepared = prepare_bundle(jobs, graph, context)
    assert jobs == original
    assert prepared.jobs[0].execution["resolved_paths"] == {"input_file": "/results/data/input.json", "output_dir": "/results/study"}
    assert "--input-file=/results/data/input.json" in prepared.jobs[0].script
    jobs[0]["script_args"]["values"].append(3)
    jobs[0]["script_args"]["output_dir"] = "other"
    graph["sample"].append("new")
    assert prepared.jobs[0].definition == original[0]
    assert prepared.children_by_job == {"sample": []}


@pytest.mark.parametrize("field,value", [("slurm", []), ("script_args", []), ("environment", ""), ("runtime_environment", [])])
def test_preparation_rejects_malformed_mapping_fields(field, value):
    job = {"name": "sample", "script": "echo science", "slurm": {}, field: value}
    context = resolve_execution_context("mock", {})
    with pytest.raises(ValueError, match="mapping"):
        prepare_bundle([job], {"sample": []}, context)
