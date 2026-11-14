"""Durable submission evidence and exact, read-only recovery inspection."""

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shlex
import subprocess

from .record_files import atomic_json
from .storage import storage_root
from .transport import ssh_command
from .errors import DiagnosticError

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
    atomic_json(path, receipt)


def validate_receipt(receipt, expected=None):
    if not isinstance(receipt, dict) or receipt.get("protocol") != SUBMISSION_PROTOCOL:
        raise ValueError("Unsupported submission receipt protocol.")
    if not re.fullmatch(r"[a-f0-9]{32}", str(receipt.get("submission_id", ""))):
        raise ValueError("Invalid submission identity.")
    if not isinstance(receipt.get("jobs"), dict) or not receipt["jobs"]:
        raise ValueError("Submission receipt has no jobs.")
    if receipt.get("state") not in {"prepared", "submitting", "submitted", "rejected", "partial", "uncertain"} or not isinstance(receipt.get("execution_finished"), bool):
        raise ValueError("Invalid overall submission evidence.")
    allowed = {"not_submitted", "submitting", "accepted", "rejected", "uncertain", "blocked"}
    for job in receipt["jobs"].values():
        if not isinstance(job, dict) or job.get("state") not in allowed:
            raise ValueError("Invalid per-job submission evidence.")
        if job.get("state") == "accepted" and not re.fullmatch(r"\d+", str(job.get("id", ""))):
            raise ValueError("Accepted job has no valid scheduler ID.")
    if receipt.get("state") == "submitted" and (not receipt.get("execution_finished") or any(job["state"] != "accepted" for job in receipt["jobs"].values())):
        raise ValueError("Submitted receipt must contain final accepted IDs for every job.")
    if expected:
        if receipt["submission_id"] != expected["submission_id"] or set(receipt["jobs"]) != set(expected["jobs"]):
            raise ValueError("Receipt does not match the selected submission.")
        for key in ("bundle", "bundle_path", "planned_path", "receipt_path", "execution_receipt_path", "machine", "execution"):
            if receipt.get(key) != expected.get(key):
                raise ValueError(f"Receipt changed the selected submission's {key}.")
        for name, job in expected["jobs"].items():
            if job.get("id") and receipt["jobs"][name].get("id") != job["id"]:
                raise ValueError("Receipt would discard or replace a known scheduler ID.")
    return receipt


def load_submission(receipt_path):
    """Read exact local submission evidence; no scheduler or network calls."""
    return validate_receipt(json.loads(Path(receipt_path).read_text()))


def list_submissions(bundle_name=None):
    """Rediscover receipts in the selected installation, newest first."""
    receipts = [load_submission(path) for path in (storage_root() / "submissions").glob("*.json")]
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
    bundle = json.loads(path.read_text())
    for name, outcome in receipt["jobs"].items():
        job = bundle[name]
        if job.get(SUBMISSION_METADATA_KEY, {}).get("submission_id") != receipt["submission_id"]:
            raise ValueError("Tracking snapshot belongs to a different submission.")
        job[SUBMISSION_METADATA_KEY] = {
            "submission_id": receipt["submission_id"], "receipt_path": receipt["receipt_path"],
            "state": outcome["state"], "error": outcome.get("error"),
        }
        if outcome.get("id"):
            if job.get("id") and str(job["id"]) != outcome["id"]:
                raise ValueError("Refusing to replace a known scheduler ID.")
            job["id"] = outcome["id"]
    atomic_json(path, bundle)


def refresh_submission(receipt_path):
    """Fetch this execution receipt only; never run a scheduler command."""
    current = load_submission(receipt_path)
    execution = current["execution"]
    try:
        if not execution["is_remote"]:
            project_receipt(current)
            return current
        result = subprocess.run(ssh_command(execution["transport"], current["machine"], "cat -- " + shlex.quote(current["execution_receipt_path"])), capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "Execution receipt is unavailable.")
        observed = validate_receipt(json.loads(result.stdout), current)
        # Retain workstation identity/paths even if a helper receives stale data.
        for key in ("bundle", "bundle_path", "planned_path", "receipt_path", "execution_receipt_path", "machine", "execution"):
            observed[key] = current[key]
        if not observed["execution_finished"]:
            mark_unobserved(observed, "Helper has not recorded a final submission outcome.")
        current = observed
        write_receipt(receipt_path, observed)
        project_receipt(observed)
        return observed
    except Exception as exc:
        current["observation_error"] = str(exc)
        try:
            write_receipt(receipt_path, current)
        except Exception as storage_error:
            current["tracking_error"] = str(storage_error)
        raise SubmissionError(f"Receipt refresh failed: {exc}", current) from exc
