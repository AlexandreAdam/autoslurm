"""Shared SSH addressing and explicit remote helper-root discovery."""

from typing import Optional
import shlex

from .config import activation_command_from_config, validate_ssh_alias
from .storage import STORAGE_ROOT_ENVIRONMENT_VARIABLE
from .remote_readiness import readiness_context, configured_root, run_readiness_probe, parse_storage_root


def scp_host_and_keypath_from_config(machine_config: dict,
                                     machine_name: Optional[str] = None) -> tuple[str, str]:
    """Return the configured destination and shell-quoted identity options.

    Current profiles use only ssh_alias and delegate connection details to SSH.
    Older recorded transports remain readable for existing job management.
    """
    if "ssh_alias" in machine_config:
        return validate_ssh_alias(machine_config["ssh_alias"]), ""
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
    destination = ([validate_ssh_alias(machine_config["ssh_alias"])] if "ssh_alias" in machine_config
                   else shlex.split(ssh_host_from_config(machine_config, machine_name)))
    command = ["ssh", *(options or []), *destination]
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
    facts = readiness_context(machine_config, machine_name, field='storage_root', executable='python')
    if explicit:
        requested = configured_root(machine_config['storage_root'], context=facts)
        facts['path'] = requested
        facts['storage_root'] = requested
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
    output = run_readiness_probe(
        ssh_command(machine_config, machine_name, f"bash -lc {shlex.quote(remote_command)}"),
        stage='probe_storage_root', context=facts)
    return parse_storage_root(output, requested=requested if explicit else None, context=facts)
