"""Import validated native tracking into one explicitly selected controller view.

Scheduler/SSH execution stays in existing adapters. This module never submits.
"""

import copy
import hashlib
import json
import os
from pathlib import Path
import re

from .config import recorded_transport
from .execution import EXECUTION_METADATA_KEY, _validate_recorded_execution
from .execution_tracking import receipt_view
from .job_dependency import dependency_graph
from .record_files import read_json, atomic_json, _write_error
from .errors import DiagnosticError, SelectionError, selection_failure, _tracking_sync_failure
from .receipt_fetch import read_execution_receipt, MAX_RECEIPT_BYTES
from .submission import (SUBMISSION_METADATA_KEY, RECEIPT_IDENTITY_FIELDS,
                         validate_receipt, merge_submission_observation, _project_receipt_data)

MAX_BUNDLE_BYTES = 8 * 1024 * 1024
_SNAPSHOT = re.compile(r".+_\d{14}\.json")


def _invalid(path, message):
    return SelectionError(_tracking_sync_failure({"bundle_path": str(path)}, message))


def _identity(bundle):
    if not isinstance(bundle, dict) or any(not isinstance(job, dict) for job in bundle.values()):
        raise ValueError("Tracking jobs must be a dictionary of job definitions.")
    metadata = [job.get(SUBMISSION_METADATA_KEY) for job in bundle.values()]
    if not any(metadata):
        return None
    if any(not isinstance(item, dict) for item in metadata):
        raise ValueError("Tracking snapshot mixes missing and recorded submission identities.")
    identities = {item.get("submission_id") for item in metadata}
    if len(identities) != 1 or not re.fullmatch(r"[a-f0-9]{32}", str(next(iter(identities)))):
        raise ValueError("Tracking snapshot has inconsistent submission identities.")
    return next(iter(identities))


def _read_bundle(path):
    if path.is_symlink():
        raise _invalid(path, "Tracking sync does not import symbolic-link snapshots.")
    bundle = read_json(path, max_bytes=MAX_BUNDLE_BYTES)
    if not isinstance(bundle, dict) or not bundle:
        raise ValueError("Tracking snapshot must contain jobs.")
    dependency_graph(bundle)
    if any(job.get("name") != name for name, job in bundle.items()):
        raise ValueError("Tracking snapshot job names disagree with its keys.")
    return bundle


def _definition(bundle):
    result = copy.deepcopy(bundle)
    for job in result.values():
        for field in ("id", "machine", SUBMISSION_METADATA_KEY, "_autoslurm_snapshot_kind"):
            job.pop(field, None)
        execution = job.get(EXECUTION_METADATA_KEY)
        if isinstance(execution, dict):
            for field in ("machine", "is_remote", "transport"):
                execution.pop(field, None)
    return result


def _assert_known_ids(bundle, receipt):
    if set(bundle) != set(receipt["jobs"]):
        raise ValueError("Receipt and snapshot have different jobs.")
    for name, job in bundle.items():
        known = job.get("id")
        if known is not None and str(known) != str(receipt["jobs"][name].get("id")):
            raise ValueError("Sync would discard or replace a known scheduler ID.")
        if list(job.get("dependencies") or []) != receipt["jobs"][name].get("dependencies", []):
            raise ValueError("Receipt and snapshot dependency definitions disagree.")


def _remote_receipt(bundle, source_path, context):
    identity = _identity(bundle)
    references = {job[SUBMISSION_METADATA_KEY].get("receipt_path") for job in bundle.values()}
    permitted = {str(Path(context.storage_root) / "submissions" / (identity + suffix))
                 for suffix in (".json", ".execution.json")}
    if len(references) != 1 or not references <= permitted:
        raise ValueError("Source receipt is not the exact submission under the selected remote root.")
    reference = next(iter(references))
    request = {"machine": context.machine_name, "submission_id": identity,
               "receipt_path": reference, "execution_receipt_path": reference,
               "execution": {"transport": recorded_transport(context.config)}}
    text = read_execution_receipt(request)
    receipt = validate_receipt(json.loads(text))
    if receipt["submission_id"] != identity or receipt.get("sync_origin"):
        raise ValueError("Source receipt identity is not a native submission.")
    for field in RECEIPT_IDENTITY_FIELDS:
        if field != "execution" and (not isinstance(receipt.get(field), str) or not receipt[field]):
            raise ValueError("Source receipt is missing immutable identity fields.")
    view = receipt_view(receipt, reference)
    if (view["bundle_path"] != str(source_path) or view["receipt_path"] != reference
            or receipt["execution_receipt_path"] != reference
            or receipt["execution"].get("storage_root") != context.storage_root):
        raise ValueError("Source receipt does not link to this exact native tracking snapshot/root.")
    if not re.fullmatch(re.escape(receipt["bundle"]) + r"_\d{14}\.json", source_path.name):
        raise ValueError("Source bundle label and exact tracking filename disagree.")
    for job in bundle.values():
        if (job.get("machine") != view["machine"]
                or any(job[EXECUTION_METADATA_KEY].get(key) != view["execution"].get(key)
                       for key in ("machine", "storage_root", "results_root", "software_root", "is_remote", "transport"))):
            raise ValueError("Source job execution disagrees with its exact receipt view.")
    _assert_known_ids(bundle, receipt)
    return receipt


def _backup(path, previous, root, identity):
    digest = hashlib.sha256(json.dumps(previous, sort_keys=True).encode()).hexdigest()
    backup = root / "sync_backups" / identity / (path.name + "." + digest + ".json")
    if backup.exists():
        if read_json(backup) != previous:
            raise _invalid(path, "Existing sync backup conflicts with the retained original.")
    else:
        atomic_json(backup, previous, exclusive=True)


def _publish(path, value, previous, root, identity):
    if previous is not None:
        if read_json(path) != previous:
            raise _invalid(path, "Local tracking changed during sync; retain both observations and run sync explicitly again.")
        if value == previous:
            return False
        _backup(path, previous, root, identity)
        if read_json(path) != previous:
            raise _invalid(path, "Local tracking changed while its backup was being saved; it was retained.")
    atomic_json(path, value, exclusive=previous is None)
    return True


def _local_index(root, errors):
    index = {}
    try:
        with os.scandir(root / "jobs") as entries:
            paths = sorted(Path(entry.path) for entry in entries if entry.name.endswith(".json"))
    except FileNotFoundError:
        paths = []
    except OSError as error:
        raise SelectionError(selection_failure(stage="sync_tracking", problem="unreadable",
            context={"path": str(root / "jobs")})) from error
    for path in paths:
        if not _SNAPSHOT.fullmatch(path.name):
            continue
        try:
            bundle = read_json(path, max_bytes=MAX_BUNDLE_BYTES)
            identity = _identity(bundle)
            if identity:
                bundle = _read_bundle(path)
                index.setdefault(identity, []).append((path, bundle))
        except DiagnosticError as error:
            errors.append(error)
        except (ValueError, TypeError) as error:
            errors.append(_invalid(path, str(error)))
    return index


def _controller_receipt(observed, current, raw_receipt, target, receipt_path, context):
    """Build a pinned controller receipt while retaining source identity."""
    if current and not raw_receipt:
        receipt = merge_submission_observation(current, observed)
    else:
        receipt = copy.deepcopy(observed)
        receipt["sync_origin"] = {key: copy.deepcopy(observed.get(key))
                                  for key in (*RECEIPT_IDENTITY_FIELDS, "execution_bundle_path")}
        receipt.update(bundle_path=str(target), planned_path=str(target), receipt_path=str(receipt_path),
                       machine=context.machine_name)
        receipt["execution"].update(machine=context.machine_name, is_remote=True,
                                    transport=recorded_transport(context.config))
        receipt = merge_submission_observation(receipt, observed)
    # A timestamp-only remote/local refresh difference is not new evidence.
    if current and {k: v for k, v in current.items() if k != "updated_at"} == {k: v for k, v in receipt.items() if k != "updated_at"}:
        receipt = current
    return receipt


def _import_one(bundle, source_path, context, root, matches):
    identity = _identity(bundle)
    for job in bundle.values():
        execution = job.get(EXECUTION_METADATA_KEY)
        _validate_recorded_execution(execution, {"bundle_path": str(source_path)})
        if execution["storage_root"] != context.storage_root or execution["is_remote"]:
            raise ValueError("Only native execution views under the selected source root can be imported.")
    observed = _remote_receipt(bundle, source_path, context)
    receipt_path = root / "submissions" / (identity + ".json")
    if receipt_path.is_symlink():
        raise ValueError("Sync does not replace symbolic-link receipts.")
    current = read_json(receipt_path, max_bytes=MAX_RECEIPT_BYTES) if receipt_path.exists() else None
    raw_receipt = bool(current and not current.get("sync_origin")
                       and current.get("receipt_path") != str(receipt_path))
    if raw_receipt:
        validate_receipt(observed, current)
    canonical = None
    for path, previous in matches:
        if _definition(previous) != _definition(bundle):
            raise ValueError("Existing submission identity has different job definitions or producing paths.")
        _assert_known_ids(previous, observed)
        for job in previous.values():
            execution = job.get(EXECUTION_METADATA_KEY, {})
            if execution.get("is_remote"):
                if (execution.get("transport") != recorded_transport(context.config)
                        or execution.get("machine") != context.machine_name):
                    raise ValueError("Existing controller view has a different pinned transport/profile.")
            elif (execution.get("storage_root") != context.storage_root
                  or job[SUBMISSION_METADATA_KEY].get("receipt_path") != bundle[job["name"]][SUBMISSION_METADATA_KEY]["receipt_path"]):
                raise ValueError("A local submission is not a verified raw copy of the selected source.")
        if current and not raw_receipt and str(path) == current.get("bundle_path"):
            canonical = (path, previous)
    if current and not raw_receipt:
        validate_receipt(current)
        if (current.get("receipt_path") != str(receipt_path)
                or current.get("machine") != context.machine_name
                or not current.get("execution", {}).get("is_remote")
                or current["execution"].get("transport") != recorded_transport(context.config)):
            raise ValueError("Existing receipt is not this controller's pinned remote view.")
        target = Path(current["bundle_path"])
        if target.parent != root / "jobs" or (matches and canonical is None):
            raise ValueError("Existing receipt does not link to the exact local tracking snapshot.")
    elif canonical is None and matches:
        canonical = next((item for item in matches if item[0].name == source_path.name), matches[0])
    if canonical:
        target, previous = canonical
    else:
        previous = None
        if not current or raw_receipt:
            target = root / "jobs" / source_path.name
        # A filename collision is never a reason to merge unrelated attempts.
        if target.exists():
            raise ValueError("Selected import filename already belongs to another record; retain it.")
    receipt = _controller_receipt(observed, current, raw_receipt, target, receipt_path, context)
    incoming = copy.deepcopy(bundle)
    for name, job in incoming.items():
        job["machine"] = context.machine_name
        job[EXECUTION_METADATA_KEY].update(machine=context.machine_name, is_remote=True,
                                          transport=recorded_transport(context.config))
        job[SUBMISSION_METADATA_KEY] = {"submission_id": identity, "receipt_path": str(receipt_path)}
    _project_receipt_data(incoming, receipt)
    changed = _publish(receipt_path, receipt, current, root, identity)
    changed = _publish(target, incoming, previous, root, identity) or changed
    for path, redundant in matches:
        if path == target:
            continue
        if read_json(path) != redundant:
            raise _invalid(path, "Redundant snapshot changed during sync; it was retained.")
        _backup(path, redundant, root, identity)
        if read_json(path) != redundant:
            raise _invalid(path, "Redundant tracking changed while backing up; it was retained.")
        try:
            path.unlink()
        except OSError as error:
            raise _write_error(error, path, "sync_redundant",
                               {"canonical_view": "succeeded", "duplicate_retirement": "unknown"}) from error
    return target, incoming, changed


def import_tracking_directory(staged, context, root):
    """Retain per-item failures while importing healthy, exactly linked neighbours."""
    errors = []
    index = _local_index(root, errors)
    counts = {"updated": 0, "unchanged": 0, "skipped": 0, "not_attempted": 0}
    paths = sorted(staged.glob("*.json"))
    attempted = set()
    for number, path in enumerate(paths):
        if not _SNAPSHOT.fullmatch(path.name):
            counts["skipped"] += 1
            continue
        try:
            bundle = _read_bundle(path)
            identity = _identity(bundle)
            if not identity:
                counts["skipped"] += 1
                continue
            attempted.add(identity)
            executions = [job.get(EXECUTION_METADATA_KEY) for job in bundle.values()]
            if all(isinstance(item, dict) and (item.get("is_remote") or
                   item.get("storage_root") != context.storage_root) for item in executions):
                counts["skipped"] += 1
                continue
            source = Path(context.storage_root) / "jobs" / path.name
            target, imported, changed = _import_one(bundle, source, context, root, index.get(identity, []))
            index[identity] = [(target, imported)]
            counts["updated" if changed else "unchanged"] += 1
        except DiagnosticError as error:
            errors.append(error)
            if error.diagnostic and error.diagnostic.code in {"transport_failed", "command_timeout", "command_unavailable", "command_failed"}:
                counts["not_attempted"] = len(paths) - number - 1
                break  # Do not retry a failed machine once per remaining run.
        except (ValueError, TypeError, KeyError) as error:
            errors.append(_invalid(Path(context.storage_root) / "jobs" / path.name, str(error)))
    for identity, matches in index.items():
        if identity in attempted:
            continue
        for path, bundle in matches:
            if all(job.get(EXECUTION_METADATA_KEY, {}).get("is_remote") is False
                   and job[EXECUTION_METADATA_KEY].get("storage_root") == context.storage_root
                   for job in bundle.values()):
                errors.append(_invalid(path, "Local raw tracking copy has no verified source snapshot; retained without guessing a repair."))
    return counts, errors
