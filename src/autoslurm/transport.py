"""Shared SSH addressing and explicit remote helper-root discovery."""

from typing import Optional
from pathlib import PurePosixPath
import shlex
import subprocess

from .configuration import activation_command_from_config
from .storage import STORAGE_ROOT_ENVIRONMENT_VARIABLE


def ssh_host_from_config(
    machine_config: dict, machine_name: Optional[str] = None
) -> str:
    hostname = machine_config.get("hostname", None)
    machine = machine_name if machine_name is not None else ""
    if hostname is None:
        if machine_config.get("username", None) is None:
            raise AttributeError(
                f"'username' must be provided when 'hostname' is not specified. "
                f"Rerun with --username option or rerun autoslurm-configuration to edit the configuration for the machine {machine}."
            )
        elif machine_config.get("hosturl", None) is None:
            raise AttributeError(
                "'hosturl' must be provided if 'hostname' is not specified. "
                "Rerun with --hosturl option or rerun autoslurm-configuration to edit the configuration for the machine {machine}."
            )
        hostname = f"{machine_config['username']}@{machine_config['hosturl']}"
        if machine_config.get("key_path", None) is not None:
            # Add the key path to the ssh command
            hostname = f"-i {machine_config['key_path']} {hostname}"
    return hostname


def scp_host_and_keypath_from_config(
    machine_config: dict, machine_name: Optional[str] = None
) -> str:
    hostname = machine_config.get("hostname", None)
    machine = machine_name if machine_name is not None else ""
    if hostname is None:
        if machine_config.get("username", None) is None:
            raise AttributeError(
                f"'username' must be provided when 'hostname' is not specified. "
                f"Rerun with --username option or rerun autoslurm-configuration to edit the configuration for the machine {machine}."
            )
        elif machine_config.get("hosturl", None) is None:
            raise AttributeError(
                "'hosturl' must be provided if 'hostname' is not specified. "
                "Rerun with --hosturl option or rerun autoslurm-configuration to edit the configuration for the machine {machine}."
            )
        hostname = f"{machine_config['username']}@{machine_config['hosturl']}"
        if machine_config.get("key_path", None) is not None:
            # # Add the key path to the ssh command
            key_path = f"-i {machine_config['key_path']}"
        else:
            key_path = ""
    else:
        key_path = ""
    return hostname, key_path


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
    hostname = ssh_host_from_config(machine_config, machine_name)
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
        ["ssh", *shlex.split(hostname), f"bash -lc {shlex.quote(remote_command)}"],
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
