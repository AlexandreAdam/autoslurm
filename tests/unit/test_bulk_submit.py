from autoslurm.bulk_submit import (
    SubmissionRequest,
    submit_dag_by_levels,
    topological_levels,
)


def test_topological_levels_wide_graph():
    graph = {
        "A": ["D"],
        "B": ["D"],
        "C": ["D"],
        "D": [],
    }
    assert topological_levels(graph) == [["A", "B", "C"], ["D"]]


def test_submit_dag_by_levels_wide_graph_batches_per_level():
    graph = {
        "A": ["D"],
        "B": ["D"],
        "C": ["D"],
        "D": [],
    }
    slurm_names = {name: f"{name}.sh" for name in graph}
    calls: list[list[SubmissionRequest]] = []

    def submit_level(requests: list[SubmissionRequest]) -> dict[str, str]:
        calls.append(requests)
        return {request.job_name: f"id-{request.job_name}" for request in requests}

    result = submit_dag_by_levels(
        children_by_job=graph, slurm_names=slurm_names, submit_level=submit_level
    )

    assert result.round_trips == 2
    assert result.levels == [["A", "B", "C"], ["D"]]
    assert result.job_ids["D"] == "id-D"
    assert len(calls) == 2
    assert tuple(calls[1][0].dependency_ids) == ("id-A", "id-B", "id-C")


def test_submit_dag_by_levels_tall_graph():
    graph = {
        "A": ["B"],
        "B": ["C"],
        "C": ["D"],
        "D": [],
    }
    slurm_names = {name: f"{name}.sh" for name in graph}

    def submit_level(requests: list[SubmissionRequest]) -> dict[str, str]:
        return {request.job_name: f"id-{request.job_name}" for request in requests}

    result = submit_dag_by_levels(
        children_by_job=graph, slurm_names=slurm_names, submit_level=submit_level
    )

    assert result.levels == [["A"], ["B"], ["C"], ["D"]]
    assert result.round_trips == 4


def test_submit_dag_by_levels_cycle_detection():
    graph = {"A": ["B"], "B": ["A"]}
    slurm_names = {"A": "A.sh", "B": "B.sh"}

    def submit_level(_requests: list[SubmissionRequest]) -> dict[str, str]:
        return {}

    try:
        submit_dag_by_levels(
            children_by_job=graph, slurm_names=slurm_names, submit_level=submit_level
        )
    except ValueError as exc:
        assert "cycle" in str(exc).lower()
    else:
        raise AssertionError("Expected ValueError for cyclic DAG")

