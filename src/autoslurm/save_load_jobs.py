"""Local bundle persistence plus explicit aliases for historical import paths."""

from datetime import datetime, timedelta
from graphlib import TopologicalSorter
from pathlib import Path
from typing import Optional
import warnings

from .record_files import atomic_json
from .definitions import DATE_FORMAT
from .storage import jobs_dir
from .job_dependency import dependency_graph
from .errors import InvalidRequestError, SelectionError, RecordCollisionError, RecordWriteError
from .bundle_selection import (
    SNAPSHOT_KIND_KEY, _snapshot_date, get_bundle_filter_mode, set_bundle_filter_mode,
    all_bundle_snapshots, bundle_snapshot_state, bundle_snapshots,
    inactive_bundle_snapshots, stale_bundle_snapshots, list_saved_bundles,
    latest_bundle_summaries, nearest_bundle_filename, select_bundle_snapshot,
    _read_snapshot, _selected_path, _bundle_name,
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


def _publish_bundle(path, bundle, *, name, source, job=None, exclusive=False):
    """Enrich the shared writer without changing its cause or publication facts."""
    try:
        atomic_json(path, bundle, exclusive=exclusive, indent=4)
    except RecordWriteError as error:
        facts = {"bundle": name, "bundle_path": str(path), "source": source}
        if job is not None:
            facts["job"] = job
        error.diagnostic = error.diagnostic.with_context(**facts)
        raise


def _validate_saved_graph(bundle, path):
    try:
        return dependency_graph(bundle)
    except InvalidRequestError as error:
        error.diagnostic = error.diagnostic.with_context(bundle_path=str(path))
        raise


def _read_existing_bundle(path, *, name, source, job=None):
    """Read/validate before mutation and retain the affected record identity."""
    try:
        bundle = _read_snapshot(path)
        _validate_saved_graph(bundle, path)
        return bundle
    except (SelectionError, InvalidRequestError) as error:
        facts = {"bundle": name, "source": source}
        if job is not None and "job" not in error.diagnostic.context:
            facts["job"] = job
        error.diagnostic = error.diagnostic.with_context(**facts)
        raise


def _new_snapshot(bundle, name, *, warn_on_collision=False, source="save_bundle", job=None, directory=None):
    """Create a complete snapshot at a free timestamp without replacing evidence."""
    date = datetime.now()
    if directory is None:
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
        except SelectionError as error:
            if error.diagnostic.code != 'resource_missing':
                raise
    while True:
        path = (jobs_dir() if directory is None else Path(directory)) / f"{name}_{date.strftime(DATE_FORMAT)}.json"
        try:
            _publish_bundle(path, bundle, name=name, source=source, job=job, exclusive=True)
            return path
        except RecordCollisionError as error:
            if getattr(error, "record_cleanup_errors", ()):
                raise
            date += timedelta(seconds=1)


def _normalize_scheduled_job(job):
    """Apply the historical command/name defaults before storing a scheduled job."""
    if not isinstance(job, dict):
        raise InvalidRequestError('Job configuration must be a dictionary.', field='job', stage='schedule_job',
                                  effects={'bundle_write': 'not_started'})
    if not isinstance(job.get('script'), str) or not job['script'].strip():
        raise InvalidRequestError("Job configuration must contain a nonempty 'script' entry to run an application",
            field='script', stage='schedule_job', effects={'bundle_write': 'not_started'})
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
    _effective_job_name(job, None)
    _ensure_snapshot_kind({job["name"]: job}, kind="draft")
    return job


def _append_jobs(jobs, name, *, source="save_bundle", job_name=None):
    """Read once and publish the complete append once; never leave a partial batch."""
    try:
        filename, _ = nearest_bundle_filename(name)
    except SelectionError as error:
        if error.diagnostic.code != 'resource_missing':
            raise
        path, bundle = None, {}
    else:
        path = jobs_dir() / filename
        bundle = _read_existing_bundle(path, name=name, source=source, job=job_name)
    for job in jobs:
        base_name = job["name"]
        effective_name, number = base_name, 0
        while effective_name in bundle:
            number += 1
            effective_name = f"{base_name}_{number:03d}"
        job["name"] = effective_name
        bundle[effective_name] = job
    if job_name is not None and len(jobs) == 1:
        job_name = jobs[0]["name"]
    if path is None:
        return _new_snapshot(bundle, name, source=source, job=job_name)
    _publish_bundle(path, bundle, name=name, source=source, job=job_name)
    return path


def save_bundle(bundle: dict, name: str, append: bool = False) -> Path:
    """Save a job dictionary and return its exact snapshot path.

    New snapshots never replace an existing timestamp. Append updates the nearest
    saved snapshot once, giving repeated job names a numeric suffix. Neither
    operation submits jobs. Callers retain the historical job-name/kind defaults.
    """
    _bundle_name(name, required=True)
    if not isinstance(bundle, dict):
        raise InvalidRequestError('bundle must be a dictionary', field='bundle', stage='save_bundle',
                                  effects={'bundle_write': 'not_started'})
    for key, job in bundle.items():
        identity = {'job': key if isinstance(key, str) else None}
        if not isinstance(key, str) or not key.strip():
            raise InvalidRequestError('Bundle keys must be nonempty job names.', field='name', stage='save_bundle',
                                      effects={'bundle_write': 'not_started'})
        if not isinstance(job, dict):
            raise InvalidRequestError('Each job in the bundle must be a dictionary. If you want to save a single job, use schedule_job() instead.',
                field='job', stage='save_bundle', context=identity, effects={'bundle_write': 'not_started'})
        if not isinstance(job.get('script'), str) or not job['script'].strip():
            raise InvalidRequestError("Each job in the bundle must contain a nonempty 'script' entry to run an application",
                field='script', stage='save_bundle', context=identity, effects={'bundle_write': 'not_started'})
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
    _bundle_name(name, required=True)
    path = (_append_jobs([job], name, source="schedule_job", job_name=job["name"]) if append
            else _new_snapshot({job["name"]: job}, name, source="schedule_job", job=job["name"]))
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
        raise InvalidRequestError('Job names must be nonempty strings.', field='name', stage='validate_definition')
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
    SelectionError: If the name/date selection is invalid, missing or inaccessible.
    SelectionError: If the selected file is missing, unreadable or invalid JSON.
    InvalidRequestError: If the saved job graph is invalid.
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
    file_path = _selected_path(bundle_path)
    jobs = _read_snapshot(file_path)
    dependencies = _validate_saved_graph(jobs, file_path)
    sorted_job_names = tuple(TopologicalSorter(dependencies).static_order())[::-1]
    jobs = order_jobs(jobs, sorted_job_names)
    # AutoSlurm snapshot identity comes from its filename, not mutable mtime.
    saved_date = _snapshot_date(file_path, fallback_to_mtime=True)
    return jobs, dependencies, saved_date
