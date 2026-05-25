from unittest.mock import patch

from autoslurm.legacy_submit_driver import submit_jobs_legacy_remote


@patch("autoslurm.legacy_submit_driver.run_slurm_remotely")
def test_submit_jobs_legacy_remote(mock_remote):
    jobs = [{"name": "A"}, {"name": "B"}]
    slurm_names = {"A": "A.sh", "B": "B.sh"}
    machine_config = {"hostname": "remote", "venv_path": "/venv"}

    def side_effect(slurm_name, machine_config=None, ssh_options=None, machine=None):
        return {"A.sh": "101", "B.sh": "202"}[slurm_name]

    mock_remote.side_effect = side_effect

    result = submit_jobs_legacy_remote(
        jobs, slurm_names, machine_config, ssh_options=["-o", "ControlMaster=auto"]
    )

    assert result == {"A": "101", "B": "202"}

