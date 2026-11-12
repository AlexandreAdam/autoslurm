"""Local bundle persistence plus explicit aliases for historical import paths."""

from datetime import datetime, timedelta
from graphlib import TopologicalSorter
from pathlib import Path
from typing import Optional
import json
import warnings

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


def save_bundle(
    bundle: dict,
    name: str,
    append: bool = False,
) -> Path:
    """
    Save job bundle configuration to a JSON file.

    Args:
        name (str): The name of the job bundle to save.
        bundle (dict): A dict of jobs (dict).
        append (bool): Flag indicating whether to append the job configurations to an existing file. Defaults to False.

    Behavior:
        - If append=False, a new job file is created.
        - If append=True, the jobs are saved to the last modified bundle with pattern 'name_*'. If no bundle file exists, a new one is created.
        - If job does not have key 'name', one is provided based on the key in the bundle.

    Returns:
        Path: The exact saved snapshot, suitable for explicit loading/submission.
    """
    if not isinstance(bundle, dict):
        raise TypeError("bundle must be a dictionary")
    for _, job in bundle.items():
        if not isinstance(job, dict):
            raise TypeError(
                "Each job in the bundle must be a dictionary. If you want to save a single job, use schedule_job() instead."
            )
        if "script" not in job:
            raise KeyError(
                "Each job in the bundle must minimally contain the 'script' entry to run an application"
            )

    if append:
        bundle = _ensure_snapshot_kind(bundle, kind="draft")
        for job_name, job in bundle.items():
            job["name"] = _effective_job_name(job, job_name)
            _, file_path = schedule_job(job, name, append=True)
    else:
        # Make sure a file with the same date does not exists, otherwise add 1 second to timestamp
        try:
            date = datetime.now()
            _, nearest_date = nearest_bundle_filename(name)
            if date - nearest_date < timedelta(seconds=1):
                warnings.warn(
                    "Found a job saved at the same time. "
                    "If you wanted the job to be appended to a bundle instead, "
                    "use the flags --append and --bundle=name_of_bundle."
                )
                date += timedelta(seconds=1)
        except FileNotFoundError:
            pass
        ensure_storage_dirs()
        # Make sure every job has a name
        for job_name, job in bundle.items():
            job["name"] = _effective_job_name(job, job_name)
        bundle = _ensure_snapshot_kind(bundle, kind="draft")
        while True:
            file_path = jobs_dir() / f"{name}_{date.strftime(DATE_FORMAT)}.json"
            try:
                with open(file_path, "x") as file:
                    json.dump(bundle, file, indent=4)
                break
            except FileExistsError:
                date += timedelta(seconds=1)
    print(f"Saved bundle {name} to {file_path}")
    return file_path


def schedule_job(
    job: dict,
    bundle_name: Optional[str] = None,
    append: bool = False,
) -> None:
    """
    Save job configurations to a JSON file.

    Args:
        job (dict): A dict of job configurations.
        bundle_name (Optional[str]): The name of the job bundle file to save to a JSON file. If None, the job name is used. Defaults to None.
        append (bool): Flag indicating whether to append the job configuration to an existing bundle. Defaults to False.

    Behavior:
        - If append=False and bundle_name=None, a new job file is created.
        - If append=False and bundle_name is specified, a new job file is created.
        - If append=True and bundle_name=None, the job is saved to the last modified bundle with pattern 'job['name']_*'.
            If no bundle file exists, a new one is created.
        - If append=True and bundle_name is specified, the job is saved to the latest bundle with the specified name.
            If no bundle file exists, a new one is created.
        - If job does not have key 'name', one is provided based on the script name. Note that name must be unique in the bundle,
            so the scheduler reserves the right to modify it.
    Returns:
        dict: The saved job configuration
    """
    ensure_storage_dirs()
    job_dir = jobs_dir()
    if "script" not in job:
        raise KeyError(
            "Job configuration must minimally contain the 'script' entry to run an application"
        )

    if "name" not in job:  # If job does not have a name, use the script name
        script_value = job["script"]
        tokens = script_value.split()
        candidate = tokens[-1]
        if candidate.endswith(".py"):
            job["name"] = Path(candidate).stem
        elif Path(script_value).suffix:
            job["name"] = Path(script_value).stem
        else:
            job["name"] = script_value
    # Normalize python script paths without invocation
    if len(job["script"].split()) == 1 and job["script"].endswith(".py"):
        job["script"] = f"python {job['script']}"
    job_name = job["name"]

    if bundle_name is None:
        bundle_name = job_name

    if append:
        try:  # Save the job in existing bundle file
            # Load the job file
            filename, date = nearest_bundle_filename(bundle_name)
            file_path = job_dir / filename
            with open(file_path, "r") as file:
                bundle = json.load(file)
            # Create a unique name in case of name conflict
            if job_name in bundle:
                i = 1
                job_name = f"{job_name}_{i:03d}"
                while job_name in bundle:
                    i += 1
                    job_name = f"{job_name[:-4]}_{i:03d}"
            job["name"] = job_name  # Update name of the job
            value = str(job.get(SNAPSHOT_KIND_KEY, "")).strip().lower()
            if value not in {"draft", "submission"}:
                job[SNAPSHOT_KIND_KEY] = "draft"
            bundle[job_name] = job  # Save it in bundle
        except (
            FileNotFoundError
        ):  # Create a new empty bundle file and save the job inside it
            date = datetime.now().strftime(DATE_FORMAT)
            print(
                f"Did not find a file with the pattern '{bundle_name}_*' in the directory {job_dir}. "
                f"Creating a new bundle file '{bundle_name}_{date}.json'"
            )
            file_path = job_dir / f"{bundle_name}_{date}.json"
            bundle = {job_name: job}
    else:  # Create a new job file
        date = datetime.now()
        try:
            # Make sure a file with the same date does not exists, otherwise add 1 second to timestamp
            _, nearest_date = nearest_bundle_filename(bundle_name)
            if date - nearest_date < timedelta(seconds=1):
                date += timedelta(seconds=1)
        except FileNotFoundError:
            pass
        date = date.strftime(DATE_FORMAT)
        file_path = job_dir / f"{bundle_name}_{date}.json"
        value = str(job.get(SNAPSHOT_KIND_KEY, "")).strip().lower()
        if value not in {"draft", "submission"}:
            job[SNAPSHOT_KIND_KEY] = "draft"
        bundle = {job_name: job}

    with open(file_path, "w") as file:
        json.dump(bundle, file, indent=4)
    print(f"Saved job {job_name} to {file_path}")
    return job, file_path


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
