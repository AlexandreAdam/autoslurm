from __future__ import annotations

from dataclasses import dataclass
from subprocess import CompletedProcess
import re
import subprocess
from typing import Callable, Optional

from .bulk_submit import SubmissionRequest, submit_dag_by_levels

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


@dataclass(frozen=True)
class BulkSubmitDriverResult:
    """Structured output of remote bulk submission."""

    job_ids: dict[str, str]
    levels: list[list[str]]
    round_trips: int


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
) -> str:
    script_path = f"{slurm_dir.rstrip('/')}/{request.slurm_name}"
    command = ["sbatch", "--parsable"]
    if request.dependency_ids:
        command.extend(["--dependency", f"afterok:{':'.join(request.dependency_ids)}"])
    command.append(script_path)
    result = run_command(command, capture_output=True, text=True)
    if result.returncode != 0:
        message = (result.stderr or "").strip() or (result.stdout or "").strip()
        raise RuntimeError(
            f"sbatch failed for job '{request.job_name}' ({request.slurm_name}): {message}"
        )
    return parse_job_id_from_parsable(result.stdout)


def submit_payload(
    payload: BulkSubmitPayload,
    run_command: Optional[Callable[..., CompletedProcess]] = None,
) -> BulkSubmitDriverResult:
    """
    Execute a payload locally on the cluster host.

    This function is intended to power a future remote entrypoint. It does not
    perform transport itself.
    """
    if run_command is None:
        run_command = subprocess.run

    def submit_level(requests: list[SubmissionRequest]) -> dict[str, str]:
        return {
            request.job_name: _submit_one(request, payload.slurm_dir, run_command)
            for request in requests
        }

    result = submit_dag_by_levels(
        children_by_job=payload.children_by_job,
        slurm_names=payload.slurm_names,
        submit_level=submit_level,
    )
    return BulkSubmitDriverResult(
        job_ids=result.job_ids, levels=result.levels, round_trips=result.round_trips
    )

