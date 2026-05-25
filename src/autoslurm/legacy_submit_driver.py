from __future__ import annotations

from typing import Optional

from .run_slurm import run_slurm_remotely

__all__ = ["submit_jobs_legacy_remote"]


def submit_jobs_legacy_remote(
    jobs: list[dict],
    slurm_names: dict[str, str],
    machine_config: dict,
    ssh_options: Optional[list[str]] = None,
) -> dict[str, str]:
    """
    Legacy fallback path: submit one remote sbatch per job.
    """
    job_ids: dict[str, str] = {}
    for job in jobs:
        job_name = job["name"]
        slurm_name = slurm_names[job_name]
        job_id = run_slurm_remotely(
            slurm_name,
            machine_config=machine_config,
            ssh_options=ssh_options,
        )
        job_ids[job_name] = job_id
    return job_ids

