import copy


def accepted_receipt(payload, ids):
    receipt = copy.deepcopy(payload["receipt"])
    receipt.update(state="submitted", execution_finished=True)
    for name, job_id in ids.items():
        receipt["jobs"][name].update(state="accepted", id=job_id)
    return receipt
