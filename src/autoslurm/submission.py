"""Durable submission evidence and exact, read-only recovery inspection."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re

from .record_files import atomic_json, read_json, _read_error
from .storage import storage_root
from .errors import DiagnosticError, DiagnosticCause, SelectionError, RecordWriteError, _receipt_fetch_failure
from .receipt_fetch import read_execution_receipt
from .execution_tracking import validate_execution_bundle_path, is_execution_receipt

__all__ = ["SubmissionError", "load_submission", "list_submissions", "refresh_submission"]
SUBMISSION_METADATA_KEY = "_autoslurm_submission"
SUBMISSION_PROTOCOL = 1


class SubmissionError(DiagnosticError):
    """Submission stopped; receipt preserves known outcomes and exact identity."""

    def __init__(self, message, receipt, *, diagnostic=None):
        super().__init__(message, diagnostic=diagnostic)
        self.receipt = receipt


def write_receipt(path, receipt):
    receipt["updated_at"] = datetime.now(timezone.utc).isoformat()
    try:
        atomic_json(path, receipt)
    except RecordWriteError as error:
        error.diagnostic = error.diagnostic.with_context(**_receipt_context(path, receipt), source="write_receipt")
        raise


def _receipt_context(path, receipt=None):
    facts = {"receipt_path": str(path), "resource": "submission_receipt"}
    if isinstance(receipt, dict):
        facts.update({key: receipt[key] for key in ("bundle", "bundle_path", "machine", "submission_id")
                      if isinstance(receipt.get(key), str)})
    return facts


def validate_receipt(receipt, expected=None):
    if not isinstance(receipt, dict) or receipt.get("protocol") != SUBMISSION_PROTOCOL:
        raise ValueError("Unsupported submission receipt protocol.")
    if not re.fullmatch(r"[a-f0-9]{32}", str(receipt.get("submission_id", ""))):
        raise ValueError("Invalid submission identity.")
    if not isinstance(receipt.get("jobs"), dict) or not receipt["jobs"]:
        raise ValueError("Submission receipt has no jobs.")
    if not isinstance(receipt.get("state"), str) or receipt["state"] not in {"prepared", "submitting", "submitted", "rejected", "partial", "uncertain"} or not isinstance(receipt.get("execution_finished"), bool):
        raise ValueError("Invalid overall submission evidence.")
    allowed = {"not_submitted", "submitting", "accepted", "rejected", "uncertain", "blocked"}
    for job in receipt["jobs"].values():
        if not isinstance(job, dict) or not isinstance(job.get("state"), str) or job["state"] not in allowed:
            raise ValueError("Invalid per-job submission evidence.")
        if job.get("state") == "accepted" and not re.fullmatch(r"\d+", str(job.get("id", ""))):
            raise ValueError("Accepted job has no valid scheduler ID.")
    if receipt.get("state") == "submitted" and (not receipt.get("execution_finished") or any(job["state"] != "accepted" for job in receipt["jobs"].values())):
        raise ValueError("Submitted receipt must contain final accepted IDs for every job.")
    validate_execution_bundle_path(receipt)
    if expected:
        if receipt["submission_id"] != expected["submission_id"] or set(receipt["jobs"]) != set(expected["jobs"]):
            raise ValueError("Receipt does not match the selected submission.")
        for key in ("bundle", "bundle_path", "planned_path", "receipt_path", "execution_receipt_path", "machine", "execution"):
            if receipt.get(key) != expected.get(key):
                raise ValueError(f"Receipt changed the selected submission's {key}.")
        for name, job in expected["jobs"].items():
            if job.get("id") and receipt["jobs"][name].get("id") != job["id"]:
                raise ValueError("Receipt would discard or replace a known scheduler ID.")
        if expected.get('execution_bundle_path') is not None and receipt.get('execution_bundle_path') != expected['execution_bundle_path']:
            raise ValueError('Receipt changed the selected execution tracking path.')
    return receipt


def load_submission(receipt_path):
    """Read exact local submission evidence; no scheduler or network calls."""
    if (not isinstance(receipt_path, (str, Path)) or not str(receipt_path).strip()
            or any(ord(char) < 32 or ord(char) == 127 for char in str(receipt_path))):
        raise _read_error("", code="invalid_argument", stage="select_receipt",
                          context={"field": "receipt_path"}, summary="Select a nonempty receipt path without control characters.")
    path = Path(receipt_path)
    context = _receipt_context(path)
    receipt = read_json(path, context=context)
    try:
        validate_receipt(receipt)
        for key in ("bundle", "bundle_path", "planned_path", "receipt_path", "execution_receipt_path", "machine", "updated_at"):
            if not isinstance(receipt.get(key), str) or not receipt[key].strip():
                raise ValueError(f"Submission receipt has no valid {key}.")
        if not isinstance(receipt.get("execution"), dict) or type(receipt["execution"].get("is_remote")) is not bool:
            raise ValueError("Submission receipt has no valid execution identity.")
        if any(not isinstance(name, str) or not name.strip() for name in receipt["jobs"]):
            raise ValueError("Submission receipt has invalid job names.")
    except ValueError as error:
        raise _read_error(path, code="record_invalid", stage="validate_receipt", cause=error,
                          context=_receipt_context(path, receipt), summary=str(error)) from error
    return receipt


def list_submissions(bundle_name=None):
    """Rediscover receipts in the selected installation, newest first."""
    directory = storage_root() / "submissions"
    try:
        with os.scandir(directory) as entries:
            paths = [Path(entry.path) for entry in entries if entry.name.endswith(".json") and not entry.name.startswith(".")]
    except FileNotFoundError as error:
        try:
            directory.lstat()
        except FileNotFoundError:
            return []
        except OSError as observed:
            raise _read_error(directory, code="resource_inaccessible", stage="list_receipts", cause=observed,
                              context={"resource": "submission_directory"}) from observed
        raise _read_error(directory, code="resource_inaccessible", stage="list_receipts", cause=error,
                          context={"resource": "submission_directory"}) from error
    except OSError as error:
        raise _read_error(directory, code="resource_inaccessible", stage="list_receipts", cause=error,
                          context={"resource": "submission_directory"}) from error
    receipts = [load_submission(path) for path in sorted(paths)]
    return sorted((item for item in receipts if bundle_name is None or item["bundle"] == bundle_name), key=lambda item: item["updated_at"], reverse=True)


def mark_unobserved(receipt, message):
    receipt["state"] = "uncertain"
    receipt["error"] = message
    receipt["execution_finished"] = False
    for job in receipt["jobs"].values():
        if job["state"] not in {"accepted", "rejected", "blocked"}:
            job["state"] = "uncertain"
            job["error"] = "Execution-side outcome has not been observed."


def project_receipt(receipt):
    """Project known evidence into the existing exact tracking snapshot."""
    path = Path(receipt["bundle_path"])
    facts = {**_receipt_context(receipt["receipt_path"], receipt), "resource": "tracking_snapshot", "source": "project_receipt"}
    bundle = read_json(path, context=facts)
    if not isinstance(bundle, dict) or any(not isinstance(bundle.get(name), dict) for name in receipt["jobs"]):
        raise _read_error(path, code="record_invalid", stage="project_receipt", context=facts,
                          summary="Tracking snapshot is missing the selected submission's jobs.")
    for name, outcome in receipt["jobs"].items():
        job = bundle[name]
        metadata = job.get(SUBMISSION_METADATA_KEY)
        if not isinstance(metadata, dict) or metadata.get("submission_id") != receipt["submission_id"]:
            raise _read_error(path, code="record_invalid", stage="project_receipt", context={**facts, "job": name},
                              summary="Tracking snapshot belongs to a different submission.")
        job[SUBMISSION_METADATA_KEY] = {
            "submission_id": receipt["submission_id"], "receipt_path": receipt["receipt_path"],
            "state": outcome["state"], "error": outcome.get("error"),
        }
        if outcome.get("id"):
            if job.get("id") and str(job["id"]) != outcome["id"]:
                raise _read_error(path, code="record_invalid", stage="project_receipt", context={**facts, "job": name},
                                  summary="Refusing to replace a known scheduler ID.")
            job["id"] = outcome["id"]
    try:
        atomic_json(path, bundle)
    except RecordWriteError as error:
        error.diagnostic = error.diagnostic.with_context(**facts)
        raise


def refresh_submission(receipt_path):
    """Fetch this execution receipt only; never run a scheduler command."""
    current = load_submission(receipt_path)
    execution = current["execution"]
    try:
        if is_execution_receipt(current, receipt_path):
            # The helper owns this incremental receipt. Never rewrite it or SSH
            # back to the cluster from an execution-side inspection.
            return current
        if not execution["is_remote"]:
            project_receipt(current)
            return current
        text = read_execution_receipt(current)
        try:
            observed = validate_receipt(json.loads(text), current)
        except ValueError as native:
            facts = {key: current[key] for key in ('machine', 'submission_id', 'receipt_path')}
            facts.update(path=current['execution_receipt_path'], resource='execution_receipt')
            raise DiagnosticError(_receipt_fetch_failure('protocol', facts,
                DiagnosticCause(type(native).__name__, 'Receipt JSON or selected submission identity was invalid.'))) from native
        # Retain workstation identity/paths even if a helper receives stale data.
        for key in ("bundle", "bundle_path", "planned_path", "receipt_path", "execution_receipt_path", "machine", "execution"):
            observed[key] = current[key]
        if not observed["execution_finished"]:
            mark_unobserved(observed, "Helper has not recorded a final submission outcome.")
        current = observed
        current.pop("observation_error", None)
        write_receipt(receipt_path, observed)
        project_receipt(observed)
        return observed
    except Exception as exc:
        current["observation_error"] = str(exc)
        try:
            write_receipt(receipt_path, current)
        except Exception as storage_error:
            current["tracking_error"] = str(storage_error)
            if isinstance(storage_error, DiagnosticError) and storage_error.diagnostic is not None:
                current["tracking_diagnostic"] = storage_error.diagnostic.to_dict()
        raise SubmissionError(f"Receipt refresh failed: {exc}", current,
            diagnostic=exc.diagnostic if isinstance(exc, DiagnosticError) else None) from exc
