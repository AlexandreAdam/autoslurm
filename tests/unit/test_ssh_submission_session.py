"""Connection ownership and short sockets, without running SSH."""

import json
import os
import subprocess
from pathlib import Path

import pytest

from autoslurm import run_slurm
from autoslurm.execution import ExecutionContext


PROFILE = {"ssh_alias": "research-gpu", "venv_path": "/env"}


@pytest.mark.parametrize("sharing", [
    "controlmaster auto\ncontrolpersist no",
    "controlmaster autoask\ncontrolpersist no",
    "controlmaster no\ncontrolpersist 600",
    "controlmaster no\ncontrolpersist yes",
])
def test_configured_connection_used_by_both_submit_callers(monkeypatch, sharing):
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if "-G" in command:
            return subprocess.CompletedProcess(
                command, 0, sharing + "\nControlPath\t/Users/x/.ssh/.%r@%h:%p\n", ""
            )
        if command[-1].startswith("sbatch "):
            output = "Submitted batch job 123\n"
        else:
            assert "autoslurm.apps.bulk_submit_driver" in command[-1]
            output = json.dumps({"ok": True, "job_ids": {"job": "124"}})
        return subprocess.CompletedProcess(command, 0, output, "")

    monkeypatch.setattr(run_slurm.subprocess, "run", run)
    monkeypatch.setattr(run_slurm.tempfile, "mkdtemp", lambda **kw: pytest.fail("User owns socket"))
    context = ExecutionContext("cluster", PROFILE, "/state", "/results", "/results", True)
    with run_slurm.ssh_submission_session(PROFILE, "cluster") as options:
        assert options == []
        assert run_slurm.run_slurm_remotely("job.slurm", ssh_options=options, context=context) == "123"
        assert run_slurm.run_bulk_submit_driver_remotely(
            {"slurm_dir": "/state/slurm"}, ssh_options=options, context=context,
        ) == {"job": "124"}
    assert calls[0] == ["ssh", "-G", "research-gpu"]
    assert len(calls) == 3
    assert all("-MNf" not in cmd and "-O" not in cmd and "-o" not in cmd for cmd in calls)
    assert all(cmd[1] == "research-gpu" for cmd in calls[1:])


@pytest.mark.parametrize("probe", [
    "controlmaster auto\ncontrolpath none\ncontrolpersist 600",
    "controlmaster no\ncontrolpath /tmp/user\ncontrolpersist no",
    "controlmaster no\ncontrolpath /tmp/user\ncontrolpersist 0",
    "controlmaster no\ncontrolpath /tmp/user\ncontrolpersist nonsense",
    "unreadable output",
    None,
    1,
    OSError("ssh unavailable"),
    subprocess.TimeoutExpired("ssh", 10),
])
def test_owned_session_short_even_with_long_tmpdir(monkeypatch, tmp_path, probe):
    long_temp = tmp_path / ("long-macos-path-" * 8)
    long_temp.mkdir()
    monkeypatch.setenv("TMPDIR", str(long_temp))
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if "-G" in command:
            if isinstance(probe, Exception):
                raise probe
            return subprocess.CompletedProcess(command, probe if isinstance(probe, int) else 0, probe, "")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(run_slurm.subprocess, "run", run)
    with run_slurm.ssh_submission_session(PROFILE) as options:
        control = next(item.split("=", 1)[1] for item in options if item.startswith("ControlPath="))
        assert control.startswith("/tmp/asl-ssh-")
        assert len((control.replace("%C", "x" * 40) + "." + "x" * 16).encode()) < 100
        folder = Path(control).parent
        assert folder.is_dir()
        assert "-MNf" in calls[1]
    assert not folder.exists()
    assert len(calls) == 3  # One config observation, one open, one close; no retries.
    assert calls[-1][-3:] == ["-O", "exit", "research-gpu"]


def test_missing_tmp_uses_default_directory_and_cleanup_preserves_body_error(monkeypatch, tmp_path):
    calls = []
    real_isdir = os.path.isdir
    monkeypatch.setattr(run_slurm.os.path, "isdir", lambda path: False if path == "/tmp" else real_isdir(path))
    folder = tmp_path / "session"
    folder.mkdir()

    def make_directory(**kwargs):
        assert kwargs == {"prefix": "asl-ssh-", "dir": None}
        return str(folder)

    def run(command, **kwargs):
        calls.append(command)
        if "-O" in command:
            raise OSError("cleanup failed")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(run_slurm.tempfile, "mkdtemp", make_directory)
    monkeypatch.setattr(run_slurm.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="body failure"):
        with run_slurm.ssh_submission_session(PROFILE):
            raise RuntimeError("body failure")
    assert not folder.exists()
    assert len(calls) == 3


@pytest.mark.parametrize("profile", [None, {}, {"results_root": "/results"}])
def test_local_session_has_no_ssh_or_temporary_directory(monkeypatch, profile):
    monkeypatch.setattr(run_slurm.subprocess, "run", lambda *a, **kw: pytest.fail("Local SSH"))
    monkeypatch.setattr(run_slurm.tempfile, "mkdtemp", lambda **kw: pytest.fail("Local socket"))
    with run_slurm.ssh_submission_session(profile) as options:
        assert options is None
