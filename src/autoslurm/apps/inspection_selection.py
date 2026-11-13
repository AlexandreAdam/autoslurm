"""Resolve terminal row selectors once, before inspecting a saved run."""

from ..array_status import declared_array_indices
from ..save_load_jobs import load_bundle_from_path
from .status import _parse_array_task_filter


def resolve_job_selection(paths, job, array, task_index, parser):
    """Use the same one-based job/expanded-array rows as status and inspect."""
    array_tasks = _parse_array_task_filter(array, parser)
    if task_index is not None and array_tasks is not None and task_index not in array_tasks:
        parser.error("The selected task is excluded by --array.")
    if job is None:
        return None, task_index, array_tasks
    if len(paths) != 1:
        parser.error("A job selector requires one exact bundle.")
    jobs, _, _ = load_bundle_from_path(paths[0])
    if not job.isdigit():
        if job not in {item["name"] for item in jobs}:
            parser.error("Selected job is absent from this snapshot.")
        return job, task_index, array_tasks
    pairs = []
    for item in jobs:
        indices = declared_array_indices((item.get("slurm") or {}).get("array")) if array is not None else []
        pairs.extend((item["name"], index) for index in (indices or [None])
                     if array_tasks is None or index is None or index in array_tasks)
    if not 1 <= int(job) <= len(pairs):
        parser.error("Job index is out of range.")
    name, row_task = pairs[int(job) - 1]
    if row_task is not None:
        if task_index is not None and task_index != row_task:
            parser.error("The selected job row and --task refer to different array tasks.")
        task_index = row_task
    return name, task_index, array_tasks
