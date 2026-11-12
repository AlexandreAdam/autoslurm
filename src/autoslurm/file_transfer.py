"""File movement adapters; bundle persistence never performs transport."""

from datetime import datetime
from pathlib import Path
from typing import Optional
import os
import shlex
import subprocess

from .configuration import load_config
from .definitions import DATE_FORMAT
from .execution import resolve_execution_context
from .storage import ensure_storage_dirs, jobs_dir, slurm_dir
from .transport import scp_host_and_keypath_from_config, remote_storage_root_from_config, ssh_host_from_config

__all__ = ["transfer_slurm_to_remote", "transfer_slurms_to_remote", "transfer_bundle_to_remote"]
_ENSURED_REMOTE_DIRS: set[tuple[str, str]] = set()


def _resolve_machine_config(
    machine_name: Optional[str], machine_config: Optional[dict]
) -> tuple[Optional[str], dict]:
    if machine_name is not None:
        user_config = load_config()
        machine_config = user_config.get(machine_name)
        if not machine_config:
            raise EnvironmentError(
                f"No configuration found for machine: {machine_name}"
            )
    if machine_config is None:
        raise ValueError("Either machine_name or machine_config must be specified")
    return machine_name, machine_config


def _transfer_context(machine_name, machine_config, context):
    if context is not None:
        return context
    machine_name, machine_config = _resolve_machine_config(machine_name, machine_config)
    return resolve_execution_context(machine_name, machine_config, root_resolver=remote_storage_root_from_config)


def _scp_to_remote(local_path: Path, remote_path: str, machine_name: Optional[str], machine_config: dict) -> None:
    hostname, key_path = scp_host_and_keypath_from_config(machine_config, machine_name)
    ssh_command = ["scp"]
    if key_path:
        ssh_command.extend(shlex.split(key_path))
    ssh_command.extend([str(local_path), f"{hostname}:{remote_path}"])
    result = subprocess.run(ssh_command, capture_output=True, text=True)
    if result.returncode != 0:
        raise ValueError(f"Error running scp command: {result.stderr}")


def _ensure_remote_directory(machine_name: Optional[str], machine_config: dict, remote_dir: str) -> None:
    cache_key = (ssh_host_from_config(machine_config, machine_name), remote_dir)
    if cache_key in _ENSURED_REMOTE_DIRS:
        return
    hostname = ssh_host_from_config(machine_config, machine_name)
    result = subprocess.run(
        ["ssh", *shlex.split(hostname), f"mkdir -p {shlex.quote(remote_dir)}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(
            f"Unable to create remote directory '{remote_dir}' for machine '{machine_name or ''}': {message}"
        )
    _ENSURED_REMOTE_DIRS.add(cache_key)


def transfer_slurm_to_remote(
    slurm_name,
    machine_name: Optional[str] = None,
    machine_config: Optional[dict] = None,
    *, context=None,
) -> None:
    """
    Transfers a script from the local machine to a remote machine.
    """
    ensure_storage_dirs()
    local_script_path = slurm_dir() / slurm_name
    context = _transfer_context(machine_name, machine_config, context)
    machine_name, machine_config = context.machine_name, context.config
    remote_path = context.storage_root
    remote_script_path = os.path.join(remote_path, "slurm", slurm_name)
    _ensure_remote_directory(machine_name, machine_config, os.path.join(remote_path, "slurm"))
    _scp_to_remote(local_script_path, remote_script_path, machine_name, machine_config)
    print(f"Saved SLURM script {slurm_name} remotely")


def transfer_slurms_to_remote(
    slurm_names: list[str],
    machine_name: Optional[str] = None,
    machine_config: Optional[dict] = None,
    *, context=None,
) -> None:
    """
    Transfer many SLURM scripts in one SCP call to reduce connection/setup overhead.
    """
    if not slurm_names:
        return
    ensure_storage_dirs()
    context = _transfer_context(machine_name, machine_config, context)
    machine_name, machine_config = context.machine_name, context.config
    remote_path = context.storage_root
    remote_slurm_dir = os.path.join(remote_path, "slurm")
    _ensure_remote_directory(machine_name, machine_config, remote_slurm_dir)
    _ensure_remote_directory(machine_name, machine_config, os.path.join(remote_path, "out"))

    hostname, key_path = scp_host_and_keypath_from_config(machine_config, machine_name)
    scp_command = ["scp"]
    if key_path:
        scp_command.extend(shlex.split(key_path))
    scp_command.extend([str(slurm_dir() / slurm_name) for slurm_name in slurm_names])
    scp_command.append(f"{hostname}:{remote_slurm_dir}/")
    result = subprocess.run(scp_command, capture_output=True, text=True)
    if result.returncode != 0:
        raise ValueError(f"Error running scp command: {result.stderr}")


def transfer_bundle_to_remote(
    bundle_name: str,
    date: datetime,
    machine_name: Optional[str] = None,
    machine_config: Optional[dict] = None,
    *, context=None,
) -> None:
    """
    Transfers the bundle JSON file to the remote machine jobs directory.
    """
    ensure_storage_dirs()
    local_bundle_path = jobs_dir() / f"{bundle_name}_{date.strftime(DATE_FORMAT)}.json"
    context = _transfer_context(machine_name, machine_config, context)
    machine_name, machine_config = context.machine_name, context.config
    remote_path = context.storage_root
    remote_bundle_path = os.path.join(remote_path, "jobs", local_bundle_path.name)
    _ensure_remote_directory(machine_name, machine_config, os.path.join(remote_path, "jobs"))
    _scp_to_remote(local_bundle_path, remote_bundle_path, machine_name, machine_config)
