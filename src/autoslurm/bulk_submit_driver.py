from __future__ import annotations

from dataclasses import dataclass
from subprocess import CompletedProcess
import re
import subprocess
import copy
from pathlib import Path
from typing import Callable, Optional

from .bulk_submit import SubmissionRequest, submit_dag_by_levels
from .submission import SubmissionError, validate_receipt, write_receipt
from .run_slurm import get_job_id_from_sbatch_output
from .job_dependency import update_slurm_with_dependencies

__all__ = [
    "BulkSubmitPayload",
    "BulkSubmitDriverResult",
    "submit_payload",
    "parse_job_id_from_parsable",
]


@dataclass(frozen=True)
class BulkSubmitPayload:
    """Structured input for remote bulk submission."""

    children_by_job: dict[str, list[str]]
    slurm_names: dict[str, str]
    slurm_dir: str
    receipt: dict | None = None
    parsable: bool = True


@dataclass(frozen=True)
class BulkSubmitDriverResult:
    """Structured output of remote bulk submission."""

    job_ids: dict[str, str]
    levels: list[list[str]]
    round_trips: int
    receipt: dict | None = None


def parse_job_id_from_parsable(output: str) -> str:
    """
    Parse job id from `sbatch --parsable` output.

    Common formats:
    - "12345"
    - "12345;cluster-name"
    """
    text = (output or "").strip()
    if not text:
        raise ValueError("Empty sbatch output.")
    candidate = text.splitlines()[0].split(";")[0].strip()
    if re.fullmatch(r"\d+", candidate):
        return candidate
    raise ValueError(f"Unable to parse job id from sbatch --parsable output: {output!r}")


def _submit_one(
    request: SubmissionRequest,
    slurm_dir: str,
    run_command: Callable[..., CompletedProcess],
    *, parsable=True,
) -> str:
    script_path = f"{slurm_dir.rstrip('/')}/{request.slurm_name}"
    command = ["sbatch", "--parsable"] if parsable else ["sbatch"]
    if request.dependency_ids:
        if parsable:
            command.extend(["--dependency", f"afterok:{':'.join(request.dependency_ids)}"])
        else:
            update_slurm_with_dependencies(request.slurm_name, request.dependency_ids)
    command.append(script_path)
    result = run_command(command, capture_output=True, text=True)
    if result.returncode < 0:
        raise RuntimeError(f"sbatch was interrupted for {request.job_name!r}; acceptance is unknown.")
    if result.returncode != 0:
        message = (result.stderr or "").strip() or (result.stdout or "").strip()
        raise SchedulerRejection(
            f"sbatch failed for job '{request.job_name}' ({request.slurm_name}): {message}"
        )
    return parse_job_id_from_parsable(result.stdout) if parsable else get_job_id_from_sbatch_output(result.stdout)


class SchedulerRejection(RuntimeError):
    pass


def submit_payload(
    payload: BulkSubmitPayload,
    run_command: Optional[Callable[..., CompletedProcess]] = None,
) -> BulkSubmitDriverResult:
    """
    Execute a payload locally on the cluster host.

    The same driver handles local execution and the prepared remote helper. It
    persists receipt evidence but does not perform transport itself.
    """
    if run_command is None:
        run_command = subprocess.run

    receipt = copy.deepcopy(payload.receipt)
    receipt_path = None
    if receipt is not None:
        validate_receipt(receipt)
        if receipt["execution_finished"] or receipt["state"] not in {"prepared", "submitting"} or any(job["state"] != "not_submitted" or job.get("id") for job in receipt["jobs"].values()):
            raise ValueError("Only a fresh, unsubmitted receipt can start execution.")
        if set(receipt["jobs"]) != set(payload.slurm_names) or set(payload.children_by_job) != set(payload.slurm_names):
            raise ValueError("Receipt, graph and script job identities must match.")
        from .bulk_submit import topological_levels
        topological_levels(payload.children_by_job)
        for name in payload.slurm_names.values():
            path = Path(payload.slurm_dir) / name
            if Path(name).name != name or not path.is_file() or not path.read_text().startswith("#!/bin/bash\n"):
                raise ValueError(f"Invalid or unavailable submission script: {name}")
        receipt_path = Path(payload.slurm_dir).parent / "submissions" / (receipt["submission_id"] + ".json")
        if str(receipt_path) != receipt["execution_receipt_path"]:
            raise ValueError("Receipt path does not match execution storage.")
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        # A persistent claim is deliberately never removed; no replay/resume.
        with receipt_path.with_suffix(".claim").open("x") as claim:
            claim.write(receipt["submission_id"])
        receipt["state"] = "submitting"
        write_receipt(receipt_path, receipt)

    def persist():
        if receipt is not None:
            try:
                write_receipt(receipt_path, receipt)
            except Exception as exc:
                receipt.update(state="uncertain", error=f"Submission receipt storage failed: {exc}", execution_finished=False)
                raise SubmissionError(receipt["error"], receipt) from exc

    def submit_level(requests: list[SubmissionRequest]) -> dict[str, str]:
        ids = {}
        for request in requests:
            outcome = receipt["jobs"][request.job_name] if receipt is not None else None
            if outcome is not None:
                outcome["state"] = "submitting"
                persist()  # Failure here stops before sbatch.
            try:
                job_id = _submit_one(request, payload.slurm_dir, run_command, parsable=payload.parsable)
            except (Exception, KeyboardInterrupt) as exc:
                if receipt is None:
                    raise
                outcome["state"] = "rejected" if isinstance(exc, (SchedulerRejection, FileNotFoundError)) else "uncertain"
                outcome["error"] = str(exc) or type(exc).__name__
                descendants = set()
                pending = list(payload.children_by_job[request.job_name])
                while pending:
                    child = pending.pop()
                    if child not in descendants:
                        descendants.add(child)
                        pending.extend(payload.children_by_job[child])
                for child in descendants:
                    receipt["jobs"][child].update(state="blocked", error=f"Prerequisite {request.job_name!r} was not accepted with a known ID.")
                receipt["state"] = "uncertain" if outcome["state"] == "uncertain" else ("partial" if any(job.get("id") for job in receipt["jobs"].values()) else "rejected")
                receipt["error"] = outcome["error"]
                receipt["execution_finished"] = True
                persist()
                raise SubmissionError(receipt["error"], receipt) from exc
            if outcome is not None:
                outcome.update(state="accepted", id=job_id)
                try:
                    persist()  # Never call another job if receipt storage fails.
                except Exception as exc:
                    receipt.update(state="uncertain", error=f"Accepted ID could not be persisted: {exc}", execution_finished=False)
                    raise SubmissionError(receipt["error"], receipt) from exc
            ids[request.job_name] = job_id
        return ids

    result = submit_dag_by_levels(
        children_by_job=payload.children_by_job,
        slurm_names=payload.slurm_names,
        submit_level=submit_level,
    )
    if receipt is not None:
        receipt.update(state="submitted", execution_finished=True)
        persist()
    return BulkSubmitDriverResult(job_ids=result.job_ids, levels=result.levels, round_trips=result.round_trips, receipt=receipt)
