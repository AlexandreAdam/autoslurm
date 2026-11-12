from typing import Optional
import copy
import re
from uuid import uuid4
from datetime import datetime
from pathlib import Path
from io import StringIO
from .job_to_slurm import write_slurm_content, validate_slurm_content
from .execution import resolve_execution_context, EXECUTION_METADATA_KEY
from .run_slurm import (
    ssh_submission_session,
    run_bulk_submit_driver_remotely,
    probe_submission_helper,
)
from .save_load_jobs import (
    load_bundle_from_path,
    save_bundle,
    transfer_slurms_to_remote,
    SNAPSHOT_KIND_KEY,
    select_bundle_snapshot,
)
from .utils import (
    machine_config as resolve_machine_config,
    remote_storage_root_from_config,
)

from .bulk_submit_driver import BulkSubmitPayload, submit_payload
from .storage import storage_root, slurm_dir
from .submission import (
    SubmissionError, SUBMISSION_METADATA_KEY, SUBMISSION_PROTOCOL,
    write_receipt, project_receipt, mark_unobserved,
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
        validate_slurm_content(output.getvalue())
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
    """Submit once, returning a receipt; SubmissionError carries partial evidence."""

    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name):
        raise ValueError("Bundle name must be a simple nonempty name without path separators.")
    if context is None:
        machine, config = resolve_machine_config(args=None, machine=machine, overrides=machine_overrides)
        context = resolve_execution_context(machine, config, root_resolver=remote_storage_root_from_config)
    else:
        if machine is not None and machine != context.machine_name:
            raise ValueError("Selected machine conflicts with the supplied execution context.")
        if machine_overrides is not None and machine_overrides != context.config:
            raise ValueError("Machine overrides conflict with the supplied execution context.")
        machine, config = context.machine_name, context.config
    selected = select_bundle_snapshot(name, bundle_path=bundle_path, desired_date=date, prefer_draft=False)
    planned_path = Path(selected["path"]).resolve()
    jobs, dependencies, _ = load_bundle_from_path(planned_path)
    if not jobs:
        raise ValueError("Cannot submit an empty bundle.")
    if any(job.get("id") or job.get(SUBMISSION_METADATA_KEY) or job.get(SNAPSHOT_KIND_KEY) == "submission" for job in jobs):
        raise ValueError("Refusing to resubmit a submission snapshot; inspect its receipt and prepare a new definition explicitly.")
    context.validate_jobs(jobs)
    # Render the entire graph before creating scripts, receipts or scheduler effects.
    rendered = {}
    for job in jobs:
        if not isinstance(job.get("script"), str) or not job["script"].strip():
            raise ValueError("Every job needs a nonempty application command.")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", job["name"]):
            raise ValueError("Job names must be simple names without path separators.")
        if job["slurm"].get("dependency") is not None:
            raise ValueError("Declare dependencies in the job graph, not Slurm options.")
        output = StringIO()
        write_slurm_content(output, job, config, context=context)
        rendered[job["name"]] = output.getvalue()
    for content in rendered.values():
        validate_slurm_content(content)
    if context.is_remote:
        probe_submission_helper(context)
    submission_id = uuid4().hex
    receipt_path = storage_root() / "submissions" / (submission_id + ".json")
    execution_root = context.storage_root if context.is_remote else str(storage_root())
    execution_receipt_path = str(Path(execution_root) / "submissions" / (submission_id + ".json"))
    snapshot = {job["name"]: copy.deepcopy(job) for job in jobs}
    for job in snapshot.values():
        job.update({SNAPSHOT_KIND_KEY: "submission", "machine": machine,
                    EXECUTION_METADATA_KEY: context.resolve_job(job),
                    SUBMISSION_METADATA_KEY: {"submission_id": submission_id, "receipt_path": str(receipt_path), "state": "not_submitted"}})
    submission_path = save_bundle(snapshot, name).resolve()
    receipt = {
        "protocol": SUBMISSION_PROTOCOL, "submission_id": submission_id, "bundle": name,
        "planned_path": str(planned_path), "bundle_path": str(submission_path),
        "receipt_path": str(receipt_path), "execution_receipt_path": execution_receipt_path,
        "machine": machine, "execution": context.resolve_job(jobs[0]),
        "state": "prepared", "execution_finished": False,
        "jobs": {job["name"]: {"state": "not_submitted", "dependencies": job.get("dependencies") or []} for job in jobs},
    }
    write_receipt(receipt_path, receipt)
    slurm_names = {}
    dispatched = False
    observed_final = False
    try:
        # Unique identity also prevents script collisions across concurrent bundles.
        for job_name, content in rendered.items():
            script_name = f"{job_name}_{submission_id}.sh"
            (slurm_dir() / script_name).write_text(content)
            slurm_names[job_name] = script_name
        if context.is_remote:
            transfer_slurm_to_remote(list(slurm_names.values()), machine_config=config, context=context)
            with ssh_submission_session(config, machine) as ssh_options:
                receipt["state"] = "submitting"
                write_receipt(receipt_path, receipt)
                dispatched = True
                receipt = run_bulk_submit_driver_remotely(
                    {"children_by_job": dependencies, "slurm_names": slurm_names,
                     "slurm_dir": str(Path(execution_root) / "slurm"), "receipt": receipt},
                    machine_config=config, ssh_options=ssh_options, context=context,
                )
                observed_final = True
        else:
            dispatched = True
            receipt = submit_payload(BulkSubmitPayload(dependencies, slurm_names, str(slurm_dir()), receipt, parsable=False)).receipt
            observed_final = True
    except (Exception, KeyboardInterrupt) as exc:
        if isinstance(exc, SubmissionError):
            receipt = exc.receipt
            if context.is_remote and not receipt["execution_finished"]:
                mark_unobserved(receipt, str(exc))
        elif dispatched and not observed_final:
            mark_unobserved(receipt, str(exc) or type(exc).__name__)
        else:
            receipt["error"] = str(exc) or type(exc).__name__
            if not observed_final:
                receipt.update(state="rejected", execution_finished=True)
        try:
            write_receipt(receipt_path, receipt)
            project_receipt(receipt)
        except Exception as storage_error:
            receipt["tracking_error"] = str(storage_error)
        raise SubmissionError(f"Submission {receipt['state']}; receipt {receipt_path}: {exc}", receipt) from exc
    try:
        write_receipt(receipt_path, receipt)
        project_receipt(receipt)
    except Exception as exc:
        receipt["tracking_error"] = str(exc)
        raise SubmissionError(f"Submission evidence could not be mirrored; receipt {receipt_path}: {exc}", receipt) from exc
    for job_name, outcome in receipt["jobs"].items():
        print(f"Submitted job {job_name} with ID {outcome['id']} at {machine}")
    print(f"Submission receipt: {receipt_path}")
    return receipt
