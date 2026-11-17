from __future__ import annotations

import json
import pytest
from pathlib import Path
from types import SimpleNamespace

from autoslurm import remote_fs


def test_resolve_results_path_uses_results_root(monkeypatch) -> None:
    monkeypatch.setattr(
        remote_fs,
        "resolve_machine_config",
        lambda machine=None: (
            "cluster",
            {"results_root": "/mnt/results", "slurm_account": "x", "env_command": "y"},
        ),
    )
    out = remote_fs.resolve_results_path("substructure_lens/results/build_jacobian")
    assert out == "/mnt/results/substructure_lens/results/build_jacobian"


def test_resolve_results_path_uses_remote_storage_when_remote(monkeypatch) -> None:
    monkeypatch.setattr(
        remote_fs,
        "resolve_machine_config",
        lambda machine=None: (
            "cluster",
            {"hostname": "cluster", "slurm_account": "x", "env_command": "y"},
        ),
    )
    monkeypatch.setattr(
        remote_fs,
        "remote_storage_root_from_config",
        lambda cfg, machine_name=None: "/remote/autoslurm",
    )
    out = remote_fs.resolve_results_path("substructure_lens/results/build_jacobian")
    assert out == "/remote/autoslurm/results/substructure_lens/results/build_jacobian"


def test_path_exists_local(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(remote_fs, "resolve_machine_config", lambda machine=None: ("local", {}))
    path = tmp_path / "file"
    path.write_text("science")
    monkeypatch.setattr("subprocess.run", lambda *a, **kw: pytest.fail("Local metadata needs no process"))
    assert remote_fs.path_exists(str(path), machine_name="local")
    assert not remote_fs.path_exists(str(tmp_path / "absent"), machine_name="local")


def test_path_exists_remote(monkeypatch) -> None:
    monkeypatch.setattr(
        remote_fs,
        "resolve_machine_config",
        lambda machine=None: (
            "cluster",
            {"hostname": "cluster", "slurm_account": "x", "env_command": "y"},
        ),
    )
    monkeypatch.setattr(
        "autoslurm.transport.ssh_host_from_config",
        lambda cfg, name=None: "user@cluster",
    )
    calls = {}

    def fake_run(cmd, **kwargs):
        calls["cmd"] = cmd
        return SimpleNamespace(returncode=0, stdout=json.dumps(
            {'version': 1, 'path': '/remote/path', 'state': 'missing', 'kind': None, 'errno': 2}), stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)
    assert not remote_fs.path_exists("/remote/path", machine_name="cluster")
    assert calls["cmd"][0] == "ssh"
    assert calls["cmd"][-1] == "python3 -B -"
