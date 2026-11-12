"""Shared SSH addressing and explicit remote helper-root discovery."""

from typing import Optional
from pathlib import PurePosixPath
import shlex
import subprocess

from .configuration import activation_command_from_config
from .storage import STORAGE_ROOT_ENVIRONMENT_VARIABLE


def scp_host_and_keypath_from_config(machine_config: dict,
                                     machine_name: Optional[str] = None) -> tuple[str, str]:
    """Return the configured destination and shell-quoted identity options.

    A hostname alias retains the historical SSH-config behavior. Structured
    username/hosturl profiles carry a separate key path, treated as one value.
    """
    hostname = machine_config.get("hostname")
    if hostname is not None:
        return hostname, ""
    machine = machine_name or ""
    if machine_config.get("username") is None:
        raise AttributeError(f"'username' must be provided when 'hostname' is not specified for machine {machine}.")
    if machine_config.get("hosturl") is None:
        raise AttributeError(f"'hosturl' must be provided if 'hostname' is not specified for machine {machine}.")
    host = f"{machine_config['username']}@{machine_config['hosturl']}"
    key = machine_config.get("key_path")
    return host, shlex.join(["-i", key]) if key is not None else ""


def ssh_host_from_config(machine_config: dict, machine_name: Optional[str] = None) -> str:
    """Historical string form; all SSH/SCP identity handling has one owner."""
    host, options = scp_host_and_keypath_from_config(machine_config, machine_name)
    return f"{options} {host}" if options else host


def ssh_command(machine_config: dict, machine_name: Optional[str] = None,
                remote_command: Optional[str] = None, *, options=None) -> list[str]:
    """Construct one SSH argument vector without discovering configuration or I/O."""
    command = ["ssh", *(options or []), *shlex.split(ssh_host_from_config(machine_config, machine_name))]
    if remote_command is not None:
        command.append(remote_command)
    return command


def remote_storage_root_from_config(
    machine_config: dict, machine_name: Optional[str] = None
) -> str:
    """Resolve legacy storage or verify an explicitly selected helper root.

    `storage_root` selects isolated remote state. It must be absolute, and the
    selected environment must support the selector and report the same root.
    Legacy `path` remains supported only when no explicit selector is present.
    """
    explicit = "storage_root" in machine_config
    if explicit:
        requested = machine_config["storage_root"]
        if not isinstance(requested, str) or not requested.strip() or not PurePosixPath(requested).is_absolute():
            raise ValueError("Machine storage_root must be a nonempty absolute POSIX path.")
        requested = str(PurePosixPath(requested))
    elif machine_config.get("path"):
        return str(machine_config["path"])
    env_command = activation_command_from_config(machine_config)
    python_probe = "from autoslurm.storage import storage_root; print(storage_root())"
    python_command = f"python -c {shlex.quote(python_probe)}"
    if explicit:
        # Importing the new constant rejects helpers that ignore the selector.
        python_probe = "from autoslurm.storage import STORAGE_ROOT_ENVIRONMENT_VARIABLE, storage_root; print(storage_root())"
        python_command = shlex.join([
            "env", f"{STORAGE_ROOT_ENVIRONMENT_VARIABLE}={requested}",
            "python", "-c", python_probe,
        ])
    command_parts = []
    if env_command:
        command_parts.append(env_command)
    command_parts.append(python_command)
    remote_command = " && ".join(command_parts)
    result = subprocess.run(
        ssh_command(machine_config, machine_name, f"bash -lc {shlex.quote(remote_command)}"),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(
            f"Unable to determine remote storage root for machine '{machine_name or ''}': {message}"
        )
    remote_root = result.stdout.strip()
    if not remote_root or not PurePosixPath(remote_root).is_absolute():
        raise RuntimeError(
            f"Unable to determine remote storage root for machine '{machine_name or ''}': expected an absolute path"
        )
    if explicit and remote_root != requested:
        raise RuntimeError(
            f"Remote storage root mismatch: requested {requested!r}, helper reported {remote_root!r}."
        )
    return remote_root
