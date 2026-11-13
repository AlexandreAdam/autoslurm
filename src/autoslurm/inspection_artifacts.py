"""Explicit selectors and artifact attachment around scheduler observations."""

from dataclasses import dataclass
from pathlib import Path

from .log_files import read_job_logs, validate_log_bounds
from .utils import name_slurm_script


@dataclass(frozen=True)
class ArtifactRequest:
    include_logs: bool = False
    include_script: bool = False
    job_name: str | None = None
    task_index: int | None = None
    tail: int = 40
    max_log_bytes: int = 65536
    max_logs: int = 20
    refresh_logs: bool = False
    stream: str = "both"
    task_indices: set[int] | None = None

    def __post_init__(self):
        # Historical context helpers accept decimal task selectors as strings.
        if isinstance(self.task_index, str) and self.task_index.isdecimal():
            object.__setattr__(self, "task_index", int(self.task_index))

    def validate(self, run):
        if not isinstance(self.stream, str) or self.stream not in {"both", "stdout", "stderr"}:
            raise ValueError("Log stream must be both, stdout or stderr.")
        if self.include_logs:
            validate_log_bounds(self.tail, self.max_log_bytes, self.max_logs)
        if self.task_index is not None and (type(self.task_index) is not int or self.task_index < 0):
            raise ValueError("Task index must be a nonnegative integer.")
        if self.task_indices is not None:
            if not isinstance(self.task_indices, (set, frozenset)) or any(type(index) is not int or index < 0 for index in self.task_indices):
                raise ValueError("Task indices must be a set of nonnegative integers.")
            if self.task_index is not None:
                raise ValueError("Select one task or a set of tasks, not both.")
        if self.job_name is not None and self.job_name not in {job["name"] for job in run.jobs}:
            raise ValueError("Selected job is absent from this exact snapshot.")


def _read_scripts(jobs, date, job_name, root):
    scripts, errors = [], []
    for job in jobs:
        if job_name is not None and job["name"] != job_name:
            continue
        path = Path(root) / "slurm" / name_slurm_script(job, date)
        try:
            content = path.read_text()
        except OSError as error:
            content = None
            errors.append({"source": "script", "message": str(error), "path": str(path)})
        scripts.append({"job_name": job["name"], "path": str(path), "content": content})
    return scripts, errors


def attach_artifacts(view, run, request, *, profiles, root, cache):
    if request.task_index is not None and not any(
        task["task_index"] == request.task_index
        for job in view["jobs"] if request.job_name is None or job["name"] == request.job_name
        for task in job["tasks"]
    ):
        raise ValueError("Selected task is absent from the declared/observed indices.")
    if request.include_logs:
        resolved_jobs = view["jobs"]
        if request.task_indices is not None:
            resolved_jobs = [dict(job, tasks=[task for task in job["tasks"]
                             if not job["is_array"] or task["task_index"] in request.task_indices])
                             for job in resolved_jobs]
        view["logs"] = read_job_logs(
            run.jobs, resolved_jobs, job_name=request.job_name, task_index=request.task_index,
            tail=request.tail, max_bytes=request.max_log_bytes, max_logs=request.max_logs,
            refresh=request.refresh_logs, profiles=profiles, root=root, cache=cache,
            stream=request.stream,
        )
    if request.include_script:
        view["scripts"], errors = _read_scripts(run.jobs, run.date, request.job_name, root)
        view["errors"].extend(errors)
    for entry in view["logs"]:
        if entry["state"] == "error":
            view["errors"].append({"source": "log", "message": entry["error"], "path": entry.get("path")})
        if entry.get("cache_error"):
            view["errors"].append(entry["cache_error"])
    if view["errors"] and view["freshness"] == "fresh":
        view["freshness"] = "partial"
    return view
