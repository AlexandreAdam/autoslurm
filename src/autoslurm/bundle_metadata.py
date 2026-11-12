"""Updates to existing bundle job fields; no transport or scheduler effects."""

import json
from .record_files import atomic_json
from .definitions import DATE_FORMAT
from .storage import ensure_storage_dirs, jobs_dir


def update_job_info_with_id(bundle_name, date, job_name, job_id):
    """Updates the job JSON file with the job ID"""
    update_job_metadata(bundle_name, date, job_name, {"id": job_id})


def update_job_metadata(bundle_name, date, job_name, metadata: dict):
    """Update arbitrary metadata fields for a job inside the bundle."""
    ensure_storage_dirs()
    path = jobs_dir() / f"{bundle_name}_{date.strftime(DATE_FORMAT)}.json"
    with open(path, "r") as f:
        jobs = json.load(f)
    job = jobs.get(job_name)
    if job is None:
        raise KeyError(f"Job '{job_name}' not found in bundle '{bundle_name}'.")
    job.update(metadata)
    atomic_json(path, jobs, indent=4)
