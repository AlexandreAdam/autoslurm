import pytest
from autoslurm.legacy_submit_driver import submit_jobs_legacy_remote


def test_legacy_graph_submission_stops_before_any_external_effect():
    with pytest.raises(RuntimeError, match="retired"):
        submit_jobs_legacy_remote([{"name": "A"}], {"A": "A.sh"}, {"hostname": "remote"})
