"""File movement adapters; bundle persistence never performs transport."""

from datetime import datetime
from pathlib import Path
from typing import Optional
import os
import shlex
import subprocess

from .config import load_config
from .definitions import DATE_FORMAT
from .execution import resolve_execution_context
from .storage import ensure_storage_dirs, jobs_dir, slurm_dir
from .transport import scp_host_and_keypath_from_config, remote_storage_root_from_config, ssh_command

__all__ = ["transfer_slurm_to_remote", "transfer_slurms_to_remote", "transfer_bundle_to_remote"]


def _resolve_machine_config(
    machine_name: Optional[str], machine_config: Optional[dict]
) -> tuple[Optional[str], dict]:
    if machine_config is None and machine_name is not None:
        user_config = load_config()
        machine_config = user_config.get("machines", {}).get(machine_name)
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
    command = ["scp"]
    if key_path:
        command.extend(shlex.split(key_path))
    command.extend([str(local_path), f"{hostname}:{remote_path}"])
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise ValueError(f"Error running scp command: {result.stderr}")


def _ensure_remote_directories(machine_name, machine_config, *directories):
    """Check each staging operation; remote directories can disappear between calls."""
    result = subprocess.run(
        ssh_command(machine_config, machine_name, "mkdir -p " + " ".join(shlex.quote(path) for path in directories)),
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"Unable to create remote directories for machine '{machine_name or ''}': {message}")


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
    _ensure_remote_directories(machine_name, machine_config, os.path.join(remote_path, "slurm"))
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
    _ensure_remote_directories(machine_name, machine_config, remote_slurm_dir, os.path.join(remote_path, "out"))

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
    _ensure_remote_directories(machine_name, machine_config, os.path.join(remote_path, "jobs"))
    _scp_to_remote(local_bundle_path, remote_bundle_path, machine_name, machine_config)


def pull_storage_directory(context, directory: str, local_target: Path, *, mutable=False):
    """Copy one storage subtree; None means an explicitly absent remote directory.

    Connection/probe failure is distinct from absence. Output is returned to the
    caller for presentation; mutable logs use checksums, immutable records retain
    the existing ignore-existing sync policy.
    """
    source_path = f"{context.storage_root.rstrip('/')}/{directory}/"
    local_target.mkdir(parents=True, exist_ok=True)
    probe = subprocess.run(
        ssh_command(context.config, context.machine_name, f"test -d {shlex.quote(source_path.rstrip('/'))}"),
        capture_output=True, text=True,
    )
    if probe.returncode == 1:
        return None
    if probe.returncode != 0:
        message = probe.stderr.strip() or probe.stdout.strip()
        raise RuntimeError(f"Unable to inspect '{directory}' on machine '{context.machine_name}': {message}")
    host, key_options = scp_host_and_keypath_from_config(context.config, context.machine_name)
    result = subprocess.run(
        ["rsync", "-a", "--checksum" if mutable else "--ignore-existing",
         "-e", shlex.join(["ssh", *shlex.split(key_options)]),
         f"{host}:{source_path}", f"{local_target}/"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"Failed to sync '{directory}' from machine '{context.machine_name}': {message}")
    return result.stdout.strip()
