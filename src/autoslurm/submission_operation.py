"""Submission stages: records, scripts, dispatch, then durable outcome evidence.

The per-job acceptance/persistence ordering remains in bulk_submit_driver. This
module coordinates one prepared operation and never retries scheduler dispatch.
"""

import copy
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from uuid import uuid4

from .bulk_submit_driver import BulkSubmitPayload, submit_payload
from .bundle_preparation import PreparedBundle
from .execution import ExecutionContext, EXECUTION_METADATA_KEY
from .run_slurm import ssh_submission_session, run_bulk_submit_driver_remotely
from .save_load_jobs import save_bundle, SNAPSHOT_KIND_KEY
from .file_transfer import transfer_slurms_to_remote
from .storage import storage_root
from .submission import (
    SubmissionError, SUBMISSION_METADATA_KEY, SUBMISSION_PROTOCOL,
    write_receipt, project_receipt, mark_unobserved,
)


class DispatchPhase(Enum):
    NOT_STARTED = "not_started"
    STARTED = "started"
    OBSERVED = "observed"


@dataclass
class SubmissionOperation:
    receipt: dict
    script_names: dict[str, str]
    local_script_directory: Path
    execution_script_directory: str
    phase: DispatchPhase = DispatchPhase.NOT_STARTED


def create_submission_operation(name, planned_path, bundle, context):
    """Create one tracking snapshot and its in-memory operation evidence."""
    local_root = storage_root()
    if not context.is_remote and str(local_root) != context.storage_root:
        raise ValueError("Selected storage root changed after execution context resolution.")
    submission_id = uuid4().hex
    receipt_path = local_root / "submissions" / (submission_id + ".json")
    execution_receipt_path = str(Path(context.storage_root) / "submissions" / (submission_id + ".json"))
    snapshot = {}
    for prepared in bundle.jobs:
        definition = copy.deepcopy(prepared.definition)
        definition.update({
            SNAPSHOT_KIND_KEY: "submission",
            "machine": context.machine_name,
            EXECUTION_METADATA_KEY: copy.deepcopy(prepared.execution),
            SUBMISSION_METADATA_KEY: {
                "submission_id": submission_id,
                "receipt_path": str(receipt_path),
                "state": "not_submitted",
            },
        })
        snapshot[prepared.name] = definition
    submission_path = save_bundle(snapshot, name).resolve()
    receipt = {
        "protocol": SUBMISSION_PROTOCOL,
        "submission_id": submission_id,
        "bundle": name,
        "planned_path": str(planned_path),
        "bundle_path": str(submission_path),
        "receipt_path": str(receipt_path),
        "execution_receipt_path": execution_receipt_path,
        "machine": context.machine_name,
        "execution": copy.deepcopy(bundle.jobs[0].execution),
        "state": "prepared",
        "execution_finished": False,
        "jobs": {
            job.name: {"state": "not_submitted",
                       "dependencies": copy.deepcopy(job.definition.get("dependencies") or [])}
            for job in bundle.jobs
        },
    }
    return SubmissionOperation(
        receipt=receipt,
        script_names={job.name: f"{job.name}_{submission_id}.sh" for job in bundle.jobs},
        local_script_directory=local_root / "slurm",
        execution_script_directory=str(Path(context.storage_root) / "slurm"),
    )


def stage_submission_scripts(operation, bundle):
    """Write exactly the text checked during preparation, before dispatch."""
    for job in bundle.jobs:
        path = operation.local_script_directory / operation.script_names[job.name]
        path.write_text(job.script)


def dispatch_submission(operation, bundle, context):
    """Cross the scheduler boundary once, recording when its outcome is observed."""
    if not context.is_remote:
        operation.phase = DispatchPhase.STARTED
        result = submit_payload(BulkSubmitPayload(
            bundle.children_by_job, operation.script_names,
            str(operation.local_script_directory), operation.receipt, parsable=False,
        ))
        operation.receipt = result.receipt
        operation.phase = DispatchPhase.OBSERVED
        return
    transfer_slurms_to_remote(
        list(operation.script_names.values()), machine_config=context.config, context=context,
    )
    with ssh_submission_session(context.config, context.machine_name) as ssh_options:
        operation.receipt["state"] = "submitting"
        write_receipt(operation.receipt["receipt_path"], operation.receipt)
        operation.phase = DispatchPhase.STARTED
        operation.receipt = run_bulk_submit_driver_remotely(
            {"children_by_job": bundle.children_by_job,
             "slurm_names": operation.script_names,
             "slurm_dir": operation.execution_script_directory,
             "receipt": operation.receipt},
            machine_config=context.config, ssh_options=ssh_options, context=context,
        )
        # Record this inside the session so cleanup errors cannot erase acceptance.
        operation.phase = DispatchPhase.OBSERVED


def record_submission_failure(operation, error, *, remote):
    """Classify an observed failure without reading, writing or dispatching work."""
    receipt = operation.receipt
    message = str(error) or type(error).__name__
    if isinstance(error, SubmissionError):
        receipt = operation.receipt = error.receipt
        if remote and not receipt["execution_finished"]:
            mark_unobserved(receipt, message)
    elif operation.phase is DispatchPhase.STARTED:
        mark_unobserved(receipt, message)
    else:
        receipt["error"] = message
        if operation.phase is not DispatchPhase.OBSERVED:
            receipt.update(state="rejected", execution_finished=True)


def persist_submission_evidence(operation):
    """Keep the receipt authoritative, then mirror it into its exact snapshot."""
    write_receipt(operation.receipt["receipt_path"], operation.receipt)
    project_receipt(operation.receipt)


def execute_prepared_bundle(name: str, planned_path: Path, bundle: PreparedBundle,
                            context: ExecutionContext) -> dict:
    """Coordinate stage ordering; lower functions own each stage's decisions."""
    operation = create_submission_operation(name, planned_path, bundle, context)
    try:
        write_receipt(operation.receipt["receipt_path"], operation.receipt)
        stage_submission_scripts(operation, bundle)
        dispatch_submission(operation, bundle, context)
    except (Exception, KeyboardInterrupt) as error:
        record_submission_failure(operation, error, remote=context.is_remote)
        try:
            persist_submission_evidence(operation)
        except (Exception, KeyboardInterrupt) as storage_error:
            operation.receipt["tracking_error"] = str(storage_error)
        receipt = operation.receipt
        raise SubmissionError(
            f"Submission {receipt['state']}; receipt {receipt['receipt_path']}: {error}", receipt,
        ) from error
    try:
        persist_submission_evidence(operation)
    except (Exception, KeyboardInterrupt) as error:
        operation.receipt["tracking_error"] = str(error)
        raise SubmissionError(
            f"Submission evidence could not be mirrored; receipt {operation.receipt['receipt_path']}: {error}",
            operation.receipt,
        ) from error
    return operation.receipt
