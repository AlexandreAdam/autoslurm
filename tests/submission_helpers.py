import copy
from pathlib import Path


def accepted_receipt(payload, ids):
    receipt = copy.deepcopy(payload["receipt"])
    receipt.update(state="submitted", execution_finished=True)
    if payload.get('tracking_bundle') is not None:
        receipt['execution_bundle_path'] = str(Path(receipt['execution']['storage_root']) / 'jobs'
                                             / (receipt['bundle'] + '_20000101000000.json'))
    for name, job_id in ids.items():
        receipt["jobs"][name].update(state="accepted", id=job_id)
    return receipt
