"""Local bundle persistence plus explicit aliases for historical import paths."""

from datetime import datetime, timedelta
from graphlib import TopologicalSorter
from pathlib import Path
from typing import Optional
import json
import warnings

from .record_files import atomic_json
from .definitions import DATE_FORMAT
from .storage import ensure_storage_dirs, jobs_dir
from .job_dependency import dependency_graph
from .bundle_selection import (
    SNAPSHOT_KIND_KEY, _snapshot_date, get_bundle_filter_mode, set_bundle_filter_mode,
    all_bundle_snapshots, bundle_snapshot_state, bundle_snapshots,
    inactive_bundle_snapshots, stale_bundle_snapshots, list_saved_bundles,
    latest_bundle_summaries, nearest_bundle_filename, select_bundle_snapshot,
)
from .file_transfer import transfer_slurm_to_remote, transfer_slurms_to_remote, transfer_bundle_to_remote

__all__ = ["schedule_job", "save_bundle", "load_bundle", "load_bundle_from_path",
           "list_saved_bundles", "latest_bundle_summaries", "bundle_snapshots",
           "get_bundle_filter_mode", "set_bundle_filter_mode", "stale_bundle_snapshots",
           "inactive_bundle_snapshots", "all_bundle_snapshots", "bundle_snapshot_state",
           "transfer_slurm_to_remote", "transfer_slurms_to_remote", "transfer_bundle_to_remote",
           "nearest_bundle_filename", "select_bundle_snapshot"]


def _ensure_snapshot_kind(payload: dict, *, kind: str) -> dict:
    if kind not in {"draft", "submission"}:
        raise ValueError("kind must be 'draft' or 'submission'")
    if not isinstance(payload, dict):
        return payload
    for job in payload.values():
        if isinstance(job, dict):
            value = str(job.get(SNAPSHOT_KIND_KEY, "")).strip().lower()
            if value not in {"draft", "submission"}:
                job[SNAPSHOT_KIND_KEY] = kind
    return payload


def _new_snapshot(bundle, name, *, warn_on_collision=False):
    """Create a complete snapshot at a free timestamp without replacing evidence."""
    date = datetime.now()
    try:
        _, nearest_date = nearest_bundle_filename(name)
        if date - nearest_date < timedelta(seconds=1):
            if warn_on_collision:
                warnings.warn(
                    "Found a job saved at the same time. "
                    "If you wanted the job to be appended to a bundle instead, "
                    "use the flags --append and --bundle=name_of_bundle."
                )
            date += timedelta(seconds=1)
    except FileNotFoundError:
        pass
    ensure_storage_dirs()
    while True:
        path = jobs_dir() / f"{name}_{date.strftime(DATE_FORMAT)}.json"
        try:
            atomic_json(path, bundle, exclusive=True, indent=4)
            return path
        except FileExistsError:
            if not path.exists():
                raise
            date += timedelta(seconds=1)


def _normalize_scheduled_job(job):
    """Apply the historical command/name defaults before storing a scheduled job."""
    if "script" not in job:
        raise KeyError("Job configuration must minimally contain the 'script' entry to run an application")
    if "name" not in job:
        script_value = job["script"]
        candidate = script_value.split()[-1]
        if candidate.endswith(".py"):
            job["name"] = Path(candidate).stem
        elif Path(script_value).suffix:
            job["name"] = Path(script_value).stem
        else:
            job["name"] = script_value
    if len(job["script"].split()) == 1 and job["script"].endswith(".py"):
        job["script"] = f"python {job['script']}"
    _ensure_snapshot_kind({job["name"]: job}, kind="draft")
    return job


def _append_jobs(jobs, name):
    """Read once and publish the complete append once; never leave a partial batch."""
    try:
        filename, _ = nearest_bundle_filename(name)
    except FileNotFoundError:
        path, bundle = None, {}
    else:
        path = jobs_dir() / filename
        with open(path) as stream:
            bundle = json.load(stream)
    for job in jobs:
        base_name = job["name"]
        job_name, number = base_name, 0
        while job_name in bundle:
            number += 1
            job_name = f"{base_name}_{number:03d}"
        job["name"] = job_name
        bundle[job_name] = job
    if path is None:
        return _new_snapshot(bundle, name)
    atomic_json(path, bundle, indent=4)
    return path


def save_bundle(bundle: dict, name: str, append: bool = False) -> Path:
    """Save a job dictionary and return its exact snapshot path.

    New snapshots never replace an existing timestamp. Append updates the nearest
    saved snapshot once, giving repeated job names a numeric suffix. Neither
    operation submits jobs. Callers retain the historical job-name/kind defaults.
    """
    if not isinstance(bundle, dict):
        raise TypeError("bundle must be a dictionary")
    for job in bundle.values():
        if not isinstance(job, dict):
            raise TypeError("Each job in the bundle must be a dictionary. If you want to save a single job, use schedule_job() instead.")
        if "script" not in job:
            raise KeyError("Each job in the bundle must minimally contain the 'script' entry to run an application")
    for key, job in bundle.items():
        job["name"] = _effective_job_name(job, key)
    _ensure_snapshot_kind(bundle, kind="draft")
    if append:
        jobs = [_normalize_scheduled_job(job) for job in bundle.values()]
        path = _append_jobs(jobs, name)
    else:
        path = _new_snapshot(bundle, name, warn_on_collision=True)
    print(f"Saved bundle {name} to {path}")
    return path


def schedule_job(job: dict, bundle_name: Optional[str] = None,
                 append: bool = False) -> tuple[dict, Path]:
    """Save one job, returning its effective definition and exact snapshot path."""
    job = _normalize_scheduled_job(job)
    name = bundle_name if bundle_name is not None else job["name"]
    path = _append_jobs([job], name) if append else _new_snapshot({job["name"]: job}, name)
    print(f"Saved job {job['name']} to {path}")
    return job, path


def order_jobs(jobs, sorted_names):
    jobs_list = []
    for name in sorted_names:
        job = jobs[name]
        job["name"] = _effective_job_name(job, name)
        jobs_list.append(job)
    return jobs_list


def _effective_job_name(job, definition_key):
    name = job.get("name")
    if name is None:
        return definition_key
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Job names must be nonempty strings.")
    return name


def load_bundle(
    name: str, desired_date: Optional[datetime] = None
) -> tuple[list, dict, datetime]:
    """
    Read the job bundle JSON file and extract the dependency graph.

    Parameters:
    name (str): The name of the job bundle to load.
    topological_sort (bool): Flag indicating whether to perform a topological sort on the dependency graph.
                             Defaults to True.

    Returns:
    tuple: A tuple containing the loaded jobs and the dependency graph.

    Raises:
    FileNotFoundError: If the specified job file does not exist.
    JSONDecodeError: If the job file is not a valid JSON file.
    """

    job_file, _ = nearest_bundle_filename(name, desired_date)
    return load_bundle_from_path(jobs_dir() / job_file)


def load_bundle_from_path(
    bundle_path: str | Path,
) -> tuple[list, dict, datetime]:
    """
    Load a bundle from an explicit JSON file path.

    This is the path-based counterpart to :func:`load_bundle`, which looks up
    bundles by name under the AutoSlurm storage root.

    Saved snapshot dates come from the filename; unversioned external files
    use modification time as a fallback.
    """
    file_path = Path(bundle_path)
    if not file_path.is_file():
        raise FileNotFoundError(f"Bundle file not found: {file_path}")

    with open(file_path, "r") as file:
        try:
            jobs = json.load(file)
        except json.JSONDecodeError:
            raise OSError(
                f"Error decoding the job bundle file {file_path}. Make sure it is a valid JSON file."
            )

    dependencies = dependency_graph(jobs)
    sorted_job_names = tuple(TopologicalSorter(dependencies).static_order())[::-1]
    jobs = order_jobs(jobs, sorted_job_names)
    # AutoSlurm snapshot identity comes from its filename, not mutable mtime.
    saved_date = _snapshot_date(file_path, fallback_to_mtime=True)
    return jobs, dependencies, saved_date
