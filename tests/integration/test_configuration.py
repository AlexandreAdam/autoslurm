import os
import json
import socket
import pytest
from unittest.mock import patch, MagicMock
from autoslurm.apps.configuration import main
from autoslurm.storage import jobs_dir, slurm_dir

EXAMPLE_CONFIG = {
    "local": {
        "env_command": "source /path/to/local/venv/bin/activate",
        "slurm_account": "def-bengioy",
    },
    "remote_machine_w_key": {
        "env_command": "source /path/to/remote/venv/bin/activate",
        "slurm_account": "rrg-account_name",
        "hosturl": "machine.domain.com",
        "username": "user1",
        "key_path": "~/.ssh/id1_rsa",
    },
    "remote_machine_wo_key": {
        "env_command": "source /path/to/remote/venv/bin/activate",
        "slurm_account": "rrg-account_name",
        "hosturl": "machine.domain.com",
        "username": "user1",
    },
    "remote_machine_w_hostname": {
        "env_command": "source /path/to/remote/venv/bin/activate",
        "slurm_account": "rrg-account_name",
        "hostname": "machine",
    },
}


def setup_mock_subprocess_run():
    def mock_subprocess_run(cmd, *args, **kwargs):
        assert cmd[0] == "ssh"
        assert cmd[2].startswith("mkdir -p ~/.autoslurm/")
        return MagicMock(returncode=0, stderr="")

    return mock_subprocess_run


@pytest.mark.parametrize("hostname_resolvable", [True, False])
def test_autoslurm_configuration(
    hostname_resolvable,
    tmp_path,
    monkeypatch,
):
    from autoslurm.storage import set_storage_root, ensure_storage_dirs
    storage_root = tmp_path / "storage"
    set_storage_root(storage_root)
    ensure_storage_dirs()

    with patch("builtins.input", return_value="4"), patch(
        "socket.gethostbyname"
    ) as mock_gethostbyname, patch("subprocess.run") as mock_run:
        if hostname_resolvable:
            mock_gethostbyname.return_value = "127.0.0.1"
        else:
            mock_gethostbyname.side_effect = socket.gaierror
        mock_run.side_effect = setup_mock_subprocess_run()

        config_path = tmp_path / "config.json"
        with open(config_path, "w") as f:
            json.dump(EXAMPLE_CONFIG, f)

        with patch("autoslurm.apps.configuration.CONFIG_FILE_PATH", str(config_path)), patch(
            "autoslurm.utils.CONFIG_FILE_PATH", str(config_path)
        ):
            main()

    assert jobs_dir().exists(), "Jobs directory should be created under storage root."
    assert slurm_dir().exists(), "SLURM directory should be created under storage root."
    if hostname_resolvable:
        assert any("mkdir -p ~/.autoslurm/jobs" in str(call.args[0][2]) for call in mock_run.call_args_list)
    else:
        assert mock_run.call_count == 0
