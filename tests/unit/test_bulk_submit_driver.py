from types import SimpleNamespace

import pytest

from autoslurm.bulk_submit_driver import (
    BulkSubmitPayload,
    parse_job_id_from_parsable,
    submit_payload,
)


def test_parse_job_id_from_parsable_variants():
    assert parse_job_id_from_parsable("12345\n") == "12345"
    assert parse_job_id_from_parsable("12345;cluster-a\n") == "12345"


def test_parse_job_id_from_parsable_invalid():
    with pytest.raises(ValueError):
        parse_job_id_from_parsable("Submitted batch job 12345")


def test_submit_payload_wide_graph_uses_dependency_flags():
    payload = BulkSubmitPayload(
        children_by_job={"A": ["C"], "B": ["C"], "C": []},
        slurm_names={"A": "A.sh", "B": "B.sh", "C": "C.sh"},
        slurm_dir="/remote/autoslurm/slurm",
    )
    calls: list[list[str]] = []
    ids = {"A.sh": "101", "B.sh": "102", "C.sh": "103"}

    def fake_run(cmd, capture_output=True, text=True):
        calls.append(cmd)
        script = cmd[-1].split("/")[-1]
        return SimpleNamespace(returncode=0, stdout=f"{ids[script]}\n", stderr="")

    result = submit_payload(payload, run_command=fake_run)

    assert result.round_trips == 2
    assert result.job_ids == {"A": "101", "B": "102", "C": "103"}
    c_call = [cmd for cmd in calls if cmd[-1].endswith("/C.sh")][0]
    assert "--dependency" in c_call
    dep_idx = c_call.index("--dependency")
    assert c_call[dep_idx + 1] == "afterok:101:102"


def test_submit_payload_raises_on_sbatch_failure():
    payload = BulkSubmitPayload(
        children_by_job={"A": []},
        slurm_names={"A": "A.sh"},
        slurm_dir="/remote/autoslurm/slurm",
    )

    def fake_run(_cmd, capture_output=True, text=True):
        return SimpleNamespace(returncode=1, stdout="", stderr="permission denied")

    with pytest.raises(RuntimeError):
        submit_payload(payload, run_command=fake_run)

