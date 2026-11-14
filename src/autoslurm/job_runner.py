"""Public preview/submission coordination over shared prepared bundles."""

from datetime import datetime
from pathlib import Path
import re
from typing import Optional

from .bundle_preparation import prepare_bundle, validate_prepared_bundle
from .execution import resolve_execution_context
from .run_slurm import probe_submission_helper
from .save_load_jobs import load_bundle_from_path
from .bundle_selection import select_bundle_snapshot
from .submission_operation import execute_prepared_bundle
from .config import machine_config as resolve_machine_config
from .errors import InvalidRequestError
from .transport import remote_storage_root_from_config

__all__ = ["submit_jobs", "preview_bundle"]


def _select_context(machine, overrides, context=None):
    if context is None:
        name, config = resolve_machine_config(args=None, machine=machine, overrides=overrides)
        return resolve_execution_context(name, config, root_resolver=remote_storage_root_from_config)
    if machine is not None and machine != context.machine_name:
        raise ValueError("Selected machine conflicts with the supplied execution context.")
    if overrides is not None and overrides != context.config:
        raise ValueError("Machine overrides conflict with the supplied execution context.")
    return context


def _prepare_selected_bundle(path, context):
    try:
        jobs, children_by_job, _ = load_bundle_from_path(path)
        prepared = prepare_bundle(jobs, children_by_job, context)
    except InvalidRequestError as error:
        error.diagnostic = error.diagnostic.with_context(bundle_path=str(path), machine=context.machine_name)
        raise
    validate_prepared_bundle(prepared, context)
    return prepared


def preview_bundle(bundle_path, *, machine=None, machine_overrides=None):
    """Validate/render an exact definition with the same rules as submission."""
    context = _select_context(machine, machine_overrides)
    prepared = _prepare_selected_bundle(bundle_path, context)
    return {
        "machine": context.machine_name,
        "bundle_path": str(Path(bundle_path).resolve()),
        "jobs": {job.name: {**job.execution, "script": job.script} for job in prepared.jobs},
    }


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
    context = _select_context(machine, machine_overrides, context)
    selected = select_bundle_snapshot(name, bundle_path=bundle_path, desired_date=date, prefer_draft=False)
    planned_path = Path(selected["path"]).resolve()
    prepared = _prepare_selected_bundle(planned_path, context)
    if context.is_remote:
        probe_submission_helper(context)
    receipt = execute_prepared_bundle(name, planned_path, prepared, context)
    _print_submission_receipt(receipt)
    return receipt


def _print_submission_receipt(receipt):
    for name, outcome in receipt["jobs"].items():
        print(f"Submitted job {name} with ID {outcome['id']} at {receipt['machine']}")
    print(f"Submission receipt: {receipt['receipt_path']}")
