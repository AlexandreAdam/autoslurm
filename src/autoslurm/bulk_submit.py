from __future__ import annotations

from dataclasses import dataclass
from collections import defaultdict
from typing import Callable


@dataclass(frozen=True)
class SubmissionRequest:
    """A single job submission request."""

    job_name: str
    slurm_name: str
    dependency_ids: tuple[str, ...]


@dataclass(frozen=True)
class LevelSubmitResult:
    """Result of level-based DAG submission orchestration."""

    job_ids: dict[str, str]
    levels: list[list[str]]
    round_trips: int


def topological_levels(children_by_job: dict[str, list[str]]) -> list[list[str]]:
    """
    Compute DAG levels from a graph represented as parent->children adjacency.

    Level 0 contains roots (jobs with no prerequisites). Each next level contains
    jobs whose prerequisites are fully satisfied by earlier levels.
    """
    parents_by_job: dict[str, set[str]] = defaultdict(set)
    indegree: dict[str, int] = {}

    for parent, children in children_by_job.items():
        indegree.setdefault(parent, 0)
        for child in children:
            parents_by_job[child].add(parent)
            indegree[child] = indegree.get(child, 0) + 1

    remaining = dict(indegree)
    current_level = sorted([name for name, degree in remaining.items() if degree == 0])
    levels: list[list[str]] = []
    visited_count = 0

    while current_level:
        levels.append(current_level)
        visited_count += len(current_level)
        next_candidates: list[str] = []
        for parent in current_level:
            for child in children_by_job.get(parent, []):
                remaining[child] -= 1
                if remaining[child] == 0:
                    next_candidates.append(child)
        current_level = sorted(next_candidates)

    if visited_count != len(remaining):
        raise ValueError("Dependency graph contains a cycle or disconnected invalid edges.")
    return levels


def submit_dag_by_levels(
    *,
    children_by_job: dict[str, list[str]],
    slurm_names: dict[str, str],
    submit_level: Callable[[list[SubmissionRequest]], dict[str, str]],
) -> LevelSubmitResult:
    """
    Submit a DAG level by level.

    The `submit_level` callback is where transport happens (for example one SSH
    round-trip that submits all jobs in the level remotely). It receives jobs in
    one level with pre-resolved dependency IDs and must return `{job_name: job_id}`.
    """
    levels = topological_levels(children_by_job)

    parents_by_job: dict[str, set[str]] = defaultdict(set)
    all_jobs = set(children_by_job.keys())
    for parent, children in children_by_job.items():
        for child in children:
            parents_by_job[child].add(parent)
            all_jobs.add(child)

    missing_slurm = sorted([job for job in all_jobs if job not in slurm_names])
    if missing_slurm:
        raise KeyError(f"Missing slurm script names for jobs: {', '.join(missing_slurm)}")

    job_ids: dict[str, str] = {}
    round_trips = 0

    for level in levels:
        requests: list[SubmissionRequest] = []
        for job_name in level:
            parent_names = sorted(parents_by_job.get(job_name, set()))
            dependency_ids = tuple(job_ids[parent] for parent in parent_names)
            requests.append(
                SubmissionRequest(
                    job_name=job_name,
                    slurm_name=slurm_names[job_name],
                    dependency_ids=dependency_ids,
                )
            )

        response = submit_level(requests)
        round_trips += 1

        for request in requests:
            if request.job_name not in response:
                raise KeyError(
                    f"submit_level did not return a job id for '{request.job_name}'."
                )
            job_ids[request.job_name] = response[request.job_name]

    return LevelSubmitResult(job_ids=job_ids, levels=levels, round_trips=round_trips)

