from typing import Optional
from datetime import datetime
import json
from pathlib import Path
from io import StringIO
from .job_to_slurm import create_slurm_script
from .job_to_slurm import write_slurm_content
from .execution import resolve_execution_context, EXECUTION_METADATA_KEY
from .legacy_submit_driver import submit_jobs_legacy_remote
from .job_dependency import update_slurm_with_dependencies
from .run_slurm import (
    run_slurm_locally,
    ssh_submission_session,
    run_bulk_submit_driver_remotely,
)
from .save_load_jobs import (
    load_bundle,
    load_bundle_from_path,
    save_bundle,
    transfer_bundle_to_remote,
    transfer_slurms_to_remote,
    SNAPSHOT_KIND_KEY,
)
from .utils import (
    machine_config as resolve_machine_config,
    update_job_info_with_id,
    update_job_metadata,
    remote_storage_root_from_config,
)

__all__ = ["submit_jobs", "preview_bundle"]


# Backward-compatibility alias kept for tests/callers that patched the legacy
# singular name.
def transfer_slurm_to_remote(*args, **kwargs):
    return transfer_slurms_to_remote(*args, **kwargs)


def preview_bundle(bundle_path, *, machine=None, machine_overrides=None):
    """Validate and render an exact definition without scripts or scheduler effects."""
    machine, config = resolve_machine_config(args=None, machine=machine, overrides=machine_overrides)
    context = resolve_execution_context(machine, config, root_resolver=remote_storage_root_from_config)
    jobs, _, _ = load_bundle_from_path(bundle_path)
    context.validate_jobs(jobs)
    rendered = {}
    for job in jobs:
        output = StringIO()
        write_slurm_content(output, job, config, context=context)
        rendered[job["name"]] = {**context.resolve_job(job), "script": output.getvalue()}
    return {"machine": machine, "bundle_path": str(Path(bundle_path).resolve()), "jobs": rendered}


def submit_jobs(
    name: str,
    machine: Optional[str] = None,
    machine_overrides: Optional[dict] = None,
    date: Optional[datetime] = None,
    bundle_path: Optional[str | Path] = None,
    *, context=None,
):
    """
    Run a job with SLURM either locally or on a remote machine. This is the main function of the scheduler module.
    It assumes the job configuration is stored in a JSON file. The logic to save jobs to a JSON file is implemented in the "save_load_jobs" module.

    Parameters:
        - name (str): The name of the job bundle to be scheduled.
        - machine (Optional[str]): Name of the configured machine to use (defaults to the configured default).
        - machine_overrides (Optional[dict]): Overrides applied on top of the selected machine configuration.
        - date (Optional[datetime]): Select the nearest saved definition timestamp when bundle_path is absent.
        - bundle_path (Optional[str | Path]): Exact saved definition to import into a new submission snapshot.

    Raises:
        - EnvironmentError: If no configuration is found for the specified machine.

    """
    if context is None:
        machine, machine_config = resolve_machine_config(args=None, machine=machine, overrides=machine_overrides)
        context = resolve_execution_context(machine, machine_config, root_resolver=remote_storage_root_from_config)
    else:
        if machine is not None and machine != context.machine_name:
            raise ValueError("Selected machine conflicts with the supplied execution context.")
        if machine_overrides is not None and machine_overrides != context.config:
            raise ValueError("Machine overrides conflict with the supplied execution context.")
        machine, machine_config = context.machine_name, context.config
    if "hostname" not in machine_config and "hosturl" not in machine_config:
        host = "localhost"
    else:
        host = machine_config.get("hostname", machine_config.get("hosturl"))

    if bundle_path is None:
        jobs, dependencies, date = load_bundle(name, date)
        context.validate_jobs(jobs)
    else:
        jobs, _, _ = load_bundle_from_path(bundle_path)
        context.validate_jobs(jobs)
        with open(bundle_path, "r") as file:
            bundle = json.load(file)
        if isinstance(bundle, dict):
            for job in bundle.values():
                if isinstance(job, dict):
                    job[SNAPSHOT_KIND_KEY] = "submission"
        submission_path = save_bundle(bundle, name)
        jobs, dependencies, date = load_bundle_from_path(submission_path)

    # Mark the persisted snapshot as a submission artifact.
    for job in jobs:
        update_job_metadata(name, date, job["name"], {
            SNAPSHOT_KIND_KEY: "submission", "machine": machine,
            EXECUTION_METADATA_KEY: context.resolve_job(job),
        })
    slurm_names = {}
    for job in jobs:
        if job.get("script", None) is None:
            raise ValueError(
                "'script' entry is missing from one of the jobs in the configuration file {job_name}"
            )
        elif job.get("name", None) is None:
            raise ValueError(
                "'name' entry is missing from one of the jobs in the configuration file {job_name}"
            )
        slurm_name = create_slurm_script(job, date, machine_config, context=context)
        slurm_names[job["name"]] = slurm_name

    is_remote = context.is_remote
    if is_remote:
        transfer_slurm_to_remote(list(slurm_names.values()), machine_config=machine_config, context=context)

    with ssh_submission_session(machine_config, machine) as ssh_options:
        if is_remote:
            remote_root = context.storage_root
            payload = {
                "children_by_job": dependencies,
                "slurm_names": slurm_names,
                "slurm_dir": f"{remote_root.rstrip('/')}/slurm",
            }
            try:
                job_ids = run_bulk_submit_driver_remotely(
                    payload,
                    machine_config=machine_config,
                    ssh_options=ssh_options,
                    context=context,
                )
            except Exception:
                # Fallback path preserves legacy behavior if driver unavailable.
                job_ids = submit_jobs_legacy_remote(
                    jobs,
                    slurm_names,
                    machine_config,
                    ssh_options=ssh_options,
                    context=context,
                )
            for job in jobs:
                job_name = job["name"]
                job_id = job_ids[job_name]
                print(f"Submitted job {job_name} with ID {job_id} at {host}")
                job_metadata = {"machine": machine}
                update_job_metadata(name, date, job_name, job_metadata)
                for dependent_job_name in dependencies.get(job_name, []):
                    update_slurm_with_dependencies(slurm_names[dependent_job_name], job_id)
                update_job_info_with_id(name, date, job_name, job_id)
        else:
            for job in jobs:
                slurm_name = slurm_names[job["name"]]
                job_id = run_slurm_locally(slurm_name)
                print(f"Submitted job {job['name']} with ID {job_id} locally")

                job_metadata = {"machine": machine}
                update_job_metadata(name, date, job["name"], job_metadata)
                for dependent_job_name in dependencies.get(job["name"], []):
                    update_slurm_with_dependencies(slurm_names[dependent_job_name], job_id)
                update_job_info_with_id(name, date, job["name"], job_id)

    if is_remote:
        transfer_bundle_to_remote(name, date, machine_config=machine_config, context=context)
