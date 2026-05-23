import shlex
import json
from unittest.mock import MagicMock

from autoslurm.apps.sync import main as sync_main
from autoslurm.storage import config_file_path, ensure_storage_dirs, set_storage_root, storage_root
from autoslurm.sync import sync_machine


def _write_config(config: dict) -> None:
    with open(config_file_path(), "w") as file:
        json.dump(config, file)


def test_sync_local_default_noop(tmp_path, monkeypatch, capsys):
    set_storage_root(tmp_path / "storage")
    ensure_storage_dirs()
    _write_config(
        {
            "machines": {
                "local": {
                    "env_command": "source /path/to/local/venv/bin/activate",
                    "slurm_account": "def-bengioy",
                }
            },
            "default_machine": "local",
        }
    )

    calls = []

    def mock_run(*args, **kwargs):
        calls.append(args[0])
        return MagicMock(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("subprocess.run", mock_run)

    sync_machine()

    output = capsys.readouterr().out
    assert "nothing to sync" in output
    assert calls == []


def test_sync_main_defaults_to_configured_machine(tmp_path, monkeypatch, capsys):
    set_storage_root(tmp_path / "storage")
    ensure_storage_dirs()
    _write_config(
        {
            "machines": {
                "local": {
                    "env_command": "source /path/to/local/venv/bin/activate",
                    "slurm_account": "def-bengioy",
                }
            },
            "default_machine": "local",
        }
    )

    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: MagicMock(returncode=0, stdout="", stderr=""))

    sync_main([])

    assert "nothing to sync" in capsys.readouterr().out


def test_sync_main_dispatches_without_args(monkeypatch):
    seen = {}

    def fake_sync_machine(machine_name=None):
        seen["machine_name"] = machine_name

    monkeypatch.setattr("autoslurm.apps.sync.sync_machine", fake_sync_machine)

    sync_main([])

    assert seen["machine_name"] is None


def test_sync_remote_pulls_storage(tmp_path, monkeypatch):
    set_storage_root(tmp_path / "storage")
    ensure_storage_dirs()
    _write_config(
        {
            "machines": {
                "remote": {
                    "env_command": "source /path/to/remote/venv/bin/activate",
                    "slurm_account": "rrg-account_name",
                    "hosturl": "machine.domain.com",
                    "username": "user1",
                    "key_path": "~/.ssh/id1_rsa",
                }
            },
            "default_machine": "remote",
        }
    )

    calls = []

    def mock_run(cmd, *args, **kwargs):
        calls.append(cmd)
        if cmd[0] == "ssh" and cmd[-1].startswith("bash -lc "):
            return MagicMock(returncode=0, stdout="/remote/autoslurm\n", stderr="")
        if cmd[0] == "ssh" and cmd[-1].startswith("test -d "):
            return MagicMock(returncode=0, stdout="", stderr="")
        if cmd[0] == "rsync":
            assert "--ignore-existing" in cmd
            assert cmd[cmd.index("-e") + 1] == shlex.join(["ssh", "-i", "~/.ssh/id1_rsa"])
            assert cmd[-2] in {
                "user1@machine.domain.com:/remote/autoslurm/jobs/",
                "user1@machine.domain.com:/remote/autoslurm/slurm/",
                "user1@machine.domain.com:/remote/autoslurm/out/",
            }
            assert cmd[-1] in {
                f"{storage_root()}/jobs/",
                f"{storage_root()}/slurm/",
                f"{storage_root()}/out/",
            }
            return MagicMock(returncode=0, stdout="", stderr="")
        raise AssertionError(f"Unexpected command: {cmd}")

    monkeypatch.setattr("subprocess.run", mock_run)

    sync_machine()

    assert len([cmd for cmd in calls if cmd[0] == "rsync"]) == 3


def test_sync_remote_skips_missing_dirs(tmp_path, monkeypatch, capsys):
    set_storage_root(tmp_path / "storage")
    ensure_storage_dirs()
    _write_config(
        {
            "machines": {
                "remote": {
                    "env_command": "source /path/to/remote/venv/bin/activate",
                    "slurm_account": "rrg-account_name",
                    "hosturl": "machine.domain.com",
                    "username": "user1",
                }
            },
            "default_machine": "remote",
        }
    )

    calls = []

    def mock_run(cmd, *args, **kwargs):
        calls.append(cmd)
        if cmd[0] == "ssh" and cmd[-1].startswith("bash -lc "):
            return MagicMock(returncode=0, stdout="/remote/autoslurm\n", stderr="")
        if cmd[0] == "ssh" and cmd[-1].startswith("test -d "):
            return MagicMock(returncode=1, stdout="", stderr="")
        raise AssertionError(f"Unexpected command: {cmd}")

    monkeypatch.setattr("subprocess.run", mock_run)

    sync_machine()

    output = capsys.readouterr().out
    assert "Skipping missing remote directory" in output
    assert len([cmd for cmd in calls if cmd[0] == "rsync"]) == 0
