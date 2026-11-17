"""Exact execution-side tracking views; origin receipts keep their identity.

No discovery, transport or scheduler calls. Derived snapshots use the ordinary
bundle writer and receipt projection, with an explicitly selected execution root.
"""

import copy
from pathlib import Path
import re

EXECUTION_TRACKING_PROTOCOL = 1


def validate_execution_bundle_path(receipt):
    """Validate additive protocol-1 execution-view evidence when present."""
    value = receipt.get('execution_bundle_path')
    if value is None:
        return
    execution = receipt.get('execution')
    root = execution.get('storage_root') if isinstance(execution, dict) else None
    if (not isinstance(value, str) or not isinstance(root, str)
            or not Path(root).is_absolute() or not Path(value).is_absolute()
            or Path(value).parent != Path(root) / 'jobs'
            or re.fullmatch(re.escape(str(receipt.get('bundle'))) + r'_\d{14}\.json', Path(value).name) is None
            or '..' in Path(value).parts
            or receipt.get('execution_receipt_path') != str(Path(root) / 'submissions' / (receipt['submission_id'] + '.execution.json'))):
        raise ValueError('Execution tracking path does not match the producing storage root and bundle.')


def is_execution_receipt(receipt, reference):
    """A receipt's file location selects its view, never its bundle name."""
    return (receipt.get('execution_bundle_path') is not None
            and Path(reference).resolve() == Path(receipt['execution_receipt_path']).resolve()
            and Path(reference).resolve() != Path(receipt['receipt_path']).resolve())


def receipt_view(receipt, reference):
    """Return origin data or a local projection without mutating saved evidence."""
    if not is_execution_receipt(receipt, reference):
        return receipt
    validate_execution_bundle_path(receipt)
    view = copy.deepcopy(receipt)
    view.update(bundle_path=receipt['execution_bundle_path'], receipt_path=str(reference))
    view['execution'].update(is_remote=False, transport={})
    return view


def tracking_path_from_receipt(reference):
    """Resolve a receipt selector, checking the execution view's exact backlink."""
    from .submission import load_submission
    from .record_files import read_json

    receipt = load_submission(reference)
    path = Path(receipt_view(receipt, reference)['bundle_path'])
    if is_execution_receipt(receipt, reference):
        bundle = read_json(path)
        if not isinstance(bundle, dict) or set(bundle) != set(receipt['jobs']):
            raise ValueError('Execution tracking snapshot does not link to the exact selected receipt.')
        for job in bundle.values():
            metadata = job.get('_autoslurm_submission') if isinstance(job, dict) else None
            if (not isinstance(metadata, dict) or metadata.get('submission_id') != receipt['submission_id']
                    or not isinstance(metadata.get('receipt_path'), str)
                    or Path(metadata['receipt_path']).resolve() != Path(reference).resolve()):
                raise ValueError('Execution tracking snapshot does not link to the exact selected receipt.')
    return path


def prepare_execution_tracking(bundle, receipt, children_by_job, root):
    """Validate the exact transmitted definition before any submission effects."""
    from .job_dependency import dependency_graph
    from .bundle_selection import _bundle_name
    from .execution import _validate_recorded_execution

    _bundle_name(receipt['bundle'], required=True)
    if (not isinstance(bundle, dict) or set(bundle) != set(receipt['jobs'])
            or dependency_graph(bundle) != children_by_job
            or receipt.get('execution_bundle_path') is not None):
        raise ValueError('Execution tracking definition does not match the fresh submission graph.')
    execution = receipt['execution']
    if (execution.get('is_remote') is not True or Path(execution['storage_root']) != root
            or Path(receipt['execution_receipt_path']) != root / 'submissions' / (receipt['submission_id'] + '.execution.json')):
        raise ValueError('Execution tracking does not match the selected producing root.')
    snapshot = copy.deepcopy(bundle)
    for name, job in snapshot.items():
        metadata = job.get('_autoslurm_submission', {})
        recorded = job.get('_autoslurm_execution', {})
        if not isinstance(metadata, dict) or not isinstance(recorded, dict):
            raise ValueError(f'Execution tracking job {name!r} has invalid submission/execution metadata.')
        if (job.get('name') != name or not isinstance(job.get('script'), str) or not job['script'].strip()
                or job.get('id') is not None or job.get('_autoslurm_snapshot_kind') != 'submission'
                or metadata.get('submission_id') != receipt['submission_id']
                or metadata.get('receipt_path') != receipt['receipt_path']
                or metadata.get('state') != 'not_submitted'
                or list(job.get('dependencies') or []) != receipt['jobs'][name].get('dependencies')
                or any(recorded.get(key) != execution.get(key) for key in
                       ('machine', 'storage_root', 'results_root', 'software_root', 'transport', 'is_remote'))
                or job.get('machine') != receipt['machine']):
            raise ValueError(f'Execution tracking job {name!r} does not match its submission identity.')
        _validate_recorded_execution(recorded, {'job': name})
        recorded.update(is_remote=False, transport={})
        metadata.update(receipt_path=receipt['execution_receipt_path'])
    return snapshot


def create_execution_tracking(snapshot, receipt, root):
    """Exclusively publish one ordinary snapshot; never replace another attempt."""
    from .save_load_jobs import _new_snapshot

    path = _new_snapshot(snapshot, receipt['bundle'], directory=root / 'jobs',
                         source='create_execution_tracking')
    receipt['execution_bundle_path'] = str(path)


def project_execution_tracking(receipt):
    """Mirror durable receipt facts using the existing exact projection owner."""
    if receipt.get('execution_bundle_path') is not None:
        from .submission import project_receipt

        project_receipt(receipt_view(receipt, receipt['execution_receipt_path']))
