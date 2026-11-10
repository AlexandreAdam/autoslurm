from pathlib import Path
import socket
import subprocess

import pytest
from autoslurm import storage


def pytest_configure(config):
    config.addinivalue_line("markers", "local_processes: allow local Python/bash fixture execution, never cluster commands")


@pytest.fixture(autouse=True)
def offline_commands(monkeypatch, request):
    """Unexpected external effects fail even if production code catches errors."""
    real_popen = subprocess.Popen

    def local_popen(command, *args, **kwargs):
        allowed = request.node.get_closest_marker("local_processes")
        if allowed and isinstance(command, (list, tuple)) and command and not kwargs.get("shell"):
            if Path(command[0]).name in {"python", "python3", "bash"}:
                return real_popen(command, *args, **kwargs)
        pytest.fail(f"Unmocked external command in offline test: {command!r}")

    def no_network(*args, **kwargs):
        pytest.fail("Unmocked network access in offline test")

    monkeypatch.setattr(subprocess, "Popen", local_popen)
    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket, "getaddrinfo", no_network)


@pytest.fixture(autouse=True)
def isolate_storage(tmp_path, monkeypatch):
    monkeypatch.delenv(storage.STORAGE_ROOT_ENVIRONMENT_VARIABLE, raising=False)
    monkeypatch.setattr(storage, "_override_root", None)
    storage_root = tmp_path / "autoslurm_storage"
    storage.set_storage_root(storage_root)
    storage.ensure_storage_dirs()
    yield storage_root
