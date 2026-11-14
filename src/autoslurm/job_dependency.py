from typing import Union
from graphlib import TopologicalSorter, CycleError
from .storage import ensure_storage_dirs, slurm_dir
from .errors import InvalidRequestError, DiagnosticCause

__all__ = ["dependency_graph", "update_slurm_with_dependencies"]


def dependency_graph(jobs):
    """
    Build a dependency graph from a dictionary of jobs.

    Example:
        jobs = {
            "JobA": {},
            "JobB": {"dependencies": ["JobA"]},
            "JobC": {"dependencies": ["JobA", "JobB"]},
        }
        dependency_graph(jobs) = {
                "JobA": ["JobB", JobC"],
                "JobB": ["JobC"],
                "JobC": []
            }
    """
    if not isinstance(jobs, dict):
        raise InvalidRequestError('A dependency graph requires a dictionary of jobs.', field='bundle', stage='validate_graph')
    dependency_graph = {name: [] for name in jobs}
    for job_name, job in jobs.items():
        if not isinstance(job, dict):
            raise InvalidRequestError('Every job must be a dictionary.', field='job', stage='validate_graph',
                                      context={'job': job_name if isinstance(job_name, str) else None})
        if not isinstance(job_name, str) or not job_name.strip() or job.get("name", job_name) not in (None, job_name):
            raise InvalidRequestError('Job names must match their nonempty bundle keys.', field='name', stage='validate_graph',
                                      context={'job': job_name if isinstance(job_name, str) else None})
        if job.get('dependencies') is not None and not isinstance(job['dependencies'], (list, tuple)):
            raise InvalidRequestError(f'Dependencies for {job_name!r} must be a list.', field='dependencies',
                                      stage='validate_graph', context={'job': job_name})
        if job.get("dependencies") is not None:  # avoid case where dependencies is None
            for dep in job.get("dependencies", []):
                if not isinstance(dep, str):
                    raise InvalidRequestError('Dependencies must be existing job names.', field='dependencies',
                                              stage='validate_graph', context={'job': job_name})
                if dep not in jobs:
                    raise InvalidRequestError(f'Unknown dependency {dep!r} for {job_name!r}.', field='dependencies',
                                              stage='validate_graph', context={'job': job_name})
                if job_name not in dependency_graph[dep]:
                    dependency_graph[dep].append(job_name)
    try:
        tuple(TopologicalSorter(dependency_graph).static_order())
    except CycleError as error:
        cycle = error.args[1]
        raise InvalidRequestError('Job dependencies contain a cycle: ' + ' -> '.join(cycle),
            field='dependencies', stage='validate_graph', context={'job': cycle[0]},
            cause=DiagnosticCause.from_exception(error)) from error
    return dependency_graph


def update_slurm_with_dependencies(
    slurm_name, dependency_job_ids: Union[list, tuple, int]
):  # , dependency_type: Union[list, str]='afterok'):
    if not isinstance(dependency_job_ids, (list, tuple)):
        dependency_job_ids = [dependency_job_ids]
    # if not isinstance(dependency_type, list):
    # dependency_type = [dependency_type] * len(dependency_job_ids)
    ensure_storage_dirs()
    file_path = slurm_dir() / slurm_name

    with open(file_path, "r") as file:
        lines = file.readlines()

    dependency_line_index = None
    for i, line in enumerate(lines):
        if line.startswith("#SBATCH --dependency"):
            dependency_line_index = i
            existing_deps = line.strip().split("afterok:")[-1]
            new_deps = ":".join(dependency_job_ids)
            if existing_deps:
                new_deps = existing_deps + ":" + new_deps
            lines[i] = f"#SBATCH --dependency=afterok:{new_deps}\n"
            break

    if dependency_line_index is None:
        # Insert the dependency directive after the shebang line
        dependency_directive = (
            f"#SBATCH --dependency=afterok:{':'.join(dependency_job_ids)}\n"
        )
        for i, line in enumerate(lines):
            if line.startswith("#!/bin/bash"):
                lines.insert(i + 1, dependency_directive)
                break

    with open(file_path, "w") as file:
        file.writelines(lines)
