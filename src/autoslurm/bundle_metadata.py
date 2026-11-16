"""Updates to existing bundle job fields; no transport or scheduler effects."""

from datetime import datetime
from .definitions import DATE_FORMAT
from .storage import jobs_dir
from .errors import InvalidRequestError, SelectionError, selection_failure


def update_job_info_with_id(bundle_name, date, job_name, job_id):
    """Updates the job JSON file with the job ID"""
    update_job_metadata(bundle_name, date, job_name, {"id": job_id})


def update_job_metadata(bundle_name, date, job_name, metadata: dict):
    """Update arbitrary metadata fields for a job inside the bundle."""
    # Lazy import avoids the historical utils -> metadata -> preparation cycle.
    from .save_load_jobs import _publish_bundle, _validate_saved_graph, _read_existing_bundle
    from .bundle_selection import _bundle_name

    _bundle_name(bundle_name, required=True)
    if not isinstance(date, datetime) or date.utcoffset() is not None:
        raise InvalidRequestError("Select a naive saved-snapshot datetime.", field="date", stage="update_job_metadata")
    if not isinstance(job_name, str) or not job_name.strip():
        raise InvalidRequestError("Select a nonempty saved job name.", field="job_name", stage="update_job_metadata")
    path = jobs_dir() / f"{bundle_name}_{date.strftime(DATE_FORMAT)}.json"
    if not isinstance(metadata, dict):
        raise InvalidRequestError("Job metadata must be a mapping.", field="metadata", stage="update_job_metadata",
            context={"bundle": bundle_name, "bundle_path": str(path), "job": job_name}, effects={"bundle_write": "not_started"})
    jobs = _read_existing_bundle(path, name=bundle_name, source="update_job_metadata", job=job_name)
    job = jobs.get(job_name)
    if job is None:
        raise SelectionError(selection_failure(stage="update_job_metadata", problem="missing",
            summary="The selected saved job was not found; the bundle was not changed.",
            context={"bundle": bundle_name, "bundle_path": str(path), "job": job_name, "field": "job_name"}))
    if job.get("id") is not None and "id" in metadata and str(metadata["id"]) != str(job["id"]):
        raise InvalidRequestError("Refusing to replace a known scheduler ID; retain the original submission evidence.",
            field="metadata.id", stage="update_job_metadata",
            context={"bundle": bundle_name, "bundle_path": str(path), "job": job_name}, effects={"bundle_write": "not_started"})
    job.update(metadata)
    _validate_saved_graph(jobs, path)
    _publish_bundle(path, jobs, name=bundle_name, source="update_job_metadata", job=job_name)
