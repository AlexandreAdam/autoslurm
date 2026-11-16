"""Refresh only receipt links belonging to exact selected tracking snapshots."""

from pathlib import Path
import copy

from .errors import DiagnosticError
from .inspection_collection import load_run, apply_receipt_to_jobs
from .submission import load_submission, refresh_submission, SubmissionError


def refresh_run_receipts(runs):
    """Retain per-run read failures while allowing scheduler/log collection."""
    failures = {}
    refreshed = set()
    observed = {}
    for run in runs:
        errors = failures.setdefault(str(run.path), [])
        for reference in run.submissions:
            path = reference['receipt_path']
            try:
                receipt = load_submission(path)
                if (Path(receipt['bundle_path']).resolve() != run.path
                        or Path(receipt['receipt_path']).resolve() != Path(path).resolve()
                        or receipt['submission_id'] != reference['submission_id']
                        or set(receipt['jobs']) != {job['name'] for job in run.jobs}
                        or any(job.get('id') and str(job['id']) != receipt['jobs'][job['name']].get('id') for job in run.jobs)):
                    raise ValueError('Receipt identity does not match the exact selected tracking snapshot; refresh was not started.')
                key = str(Path(path).resolve())
                if receipt['execution']['is_remote'] and key not in refreshed:
                    refreshed.add(key)
                    observed[key] = refresh_submission(path)
            except (SubmissionError, ValueError, OSError) as error:
                if isinstance(error, SubmissionError):
                    observed[str(Path(path).resolve())] = error.receipt
                entry = {'source': 'receipt_refresh', 'message': str(error), 'path': path}
                if isinstance(error, DiagnosticError) and error.diagnostic is not None:
                    entry['diagnostic'] = error.diagnostic.to_dict()
                errors.append(entry)
    output = []
    for run in runs:
        updated = load_run(run.path)
        if updated.date is None and run.date is not None:
            errors = updated.errors
            updated = copy.deepcopy(run)
            updated.errors.extend(errors)
        for reference in run.submissions:
            receipt = observed.get(str(Path(reference['receipt_path']).resolve()))
            if receipt is not None:
                try:
                    apply_receipt_to_jobs(updated.jobs, receipt)
                    updated.submissions = [item for item in updated.submissions if item['submission_id'] != receipt['submission_id']]
                    updated.submissions.append({**reference, 'state': receipt['state']})
                except ValueError as error:
                    updated.errors.append({'source': 'receipt_refresh', 'message': str(error), 'path': reference['receipt_path']})
        updated.errors.extend(failures[str(run.path)])
        output.append(updated)
    return output
