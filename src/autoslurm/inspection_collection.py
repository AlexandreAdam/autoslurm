"""Explicit file/configuration loading and scheduler observation collection."""

import copy
from dataclasses import dataclass
from datetime import datetime
import hashlib
from pathlib import Path

from .array_status import parent_job_id
from .execution import EXECUTION_METADATA_KEY, producing_machine
from .save_load_jobs import load_bundle_from_path
from .scheduler import query_scheduler
from .submission import load_submission, SUBMISSION_METADATA_KEY
from .utils import load_config


@dataclass
class InspectionRun:
    path: Path
    jobs: list
    date: datetime | None
    submissions: list
    errors: list
    fingerprint: str | None


def _load_selected(path):
    jobs, _, date = load_bundle_from_path(path)
    jobs = copy.deepcopy(jobs)
    receipt_refs = {job[SUBMISSION_METADATA_KEY]["receipt_path"] for job in jobs if job.get(SUBMISSION_METADATA_KEY)}
    errors = []
    receipts = []
    for reference in receipt_refs:
        try:
            receipt = load_submission(reference)
            if set(receipt["jobs"]) != {job["name"] for job in jobs}:
                raise ValueError("Receipt and selected bundle jobs disagree.")
            for job in jobs:
                if job.get(SUBMISSION_METADATA_KEY, {}).get("submission_id") != receipt["submission_id"]:
                    raise ValueError("Receipt and selected bundle identity disagree.")
            for job in jobs:
                outcome = receipt["jobs"][job["name"]]
                if job.get("id") and outcome.get("id") != str(job["id"]):
                    raise ValueError("Receipt would discard a known scheduler ID.")
            for job in jobs:
                outcome = receipt["jobs"][job["name"]]
                if outcome.get("id"):
                    job["id"] = outcome["id"]
                job[SUBMISSION_METADATA_KEY] = {**job[SUBMISSION_METADATA_KEY], **outcome}
            receipts.append({"submission_id": receipt["submission_id"], "state": receipt["state"], "receipt_path": reference})
        except (OSError, ValueError, KeyError) as exc:
            errors.append({"source": "receipt", "message": str(exc), "path": reference})
    return jobs, date, receipts, errors


def load_run(path):
    """Load one exact run and local receipt evidence, isolating broken records."""
    path = Path(path).resolve()
    try:
        before = path.read_bytes()
        jobs, date, receipts, errors = _load_selected(path)
        after = path.read_bytes()
        if before != after:
            raise ValueError("Definition changed while it was being inspected; retry observation.")
        return InspectionRun(path, jobs, date, receipts, errors, hashlib.sha256(before).hexdigest())
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        return InspectionRun(path, [], None, [],
            [{"source": "definition", "message": str(error), "path": str(path)}], None)


def load_machine_profiles(jobs):
    if all(EXECUTION_METADATA_KEY in job or job.get("machine") is None for job in jobs):
        return {}, None
    try:
        profiles = load_config().get("machines", {})
        if not isinstance(profiles, dict):
            raise ValueError("Machine profiles must be a mapping.")
        return profiles, None
    except (OSError, ValueError, TypeError, AttributeError) as error:
        return {}, str(error)


def collect_observations(jobs, profiles):
    """Query each producing machine once, excluding invalid job identities."""
    groups = {}
    for job in jobs:
        identity = parent_job_id(job.get("id"))
        if identity is None:
            continue
        try:
            key, config = producing_machine(job, profiles)
        except ValueError:
            continue  # Pure projection will retain the per-job configuration error.
        group = groups.setdefault(key, {"ids": [], "config": config, "machine": job.get("machine")})
        group["ids"].append(identity)
    return {key: query_scheduler(group["ids"], group["config"], group["machine"])
            for key, group in groups.items()}
