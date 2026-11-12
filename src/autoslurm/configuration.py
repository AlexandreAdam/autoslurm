"""Machine configuration normalization, selection and persistence."""

from typing import Optional
from argparse import Namespace
import os
import json
import shlex

from .record_files import atomic_json
from .definitions import MACHINE_KEYS
from .storage import config_file_path, STORAGE_ROOT_ENVIRONMENT_VARIABLE

__all__ = ["load_config", "save_config", "machine_config", "activation_command_from_config"]


def is_remote_machine(config):
    """One data-only rule for current and recorded transport profiles."""
    return bool(config.get("hostname") or config.get("hosturl") or config.get("username"))


def activation_command_from_config(machine_config: dict) -> str:
    """Return environment activation command from structured machine config."""
    venv_path = machine_config.get("venv_path")
    if isinstance(venv_path, str) and venv_path.strip():
        return f"source {shlex.quote(venv_path)}/bin/activate"
    env_command = machine_config.get("env_command", "")
    if isinstance(env_command, str):
        return env_command.strip()
    return ""


def _normalize_config(raw: dict) -> dict:
    """
    Normalize the configuration to ensure the structure contains 'machines',
    'default_machine', and an alias 'local' that points to the default machine.
    """
    raw = dict(raw)
    machines = raw.get("machines")
    if machines is None:
        machines = {
            name: value
            for name, value in raw.items()
            if name != "default_machine"
        }
    if not isinstance(machines, dict):
        raise EnvironmentError("The 'machines' entry must be a dictionary.")
    default_machine = raw.get("default_machine")
    if default_machine is None:
        if "local" in machines:
            default_machine = "local"
        elif machines:
            default_machine = next(iter(machines))
        else:
            raise EnvironmentError("No machines defined in the configuration file.")
    if default_machine not in machines:
        raise EnvironmentError(
            f"Default machine '{default_machine}' not found in the configuration file."
        )
    bundle_filter_mode = str(raw.get("bundle_filter_mode", "active")).strip().lower()
    if bundle_filter_mode not in {"active", "all"}:
        bundle_filter_mode = "active"
    normalized = {
        "machines": machines,
        "default_machine": default_machine,
        "bundle_filter_mode": bundle_filter_mode,
    }
    normalized["local"] = machines[default_machine]
    normalized.update(machines)
    return normalized


def save_config(config: dict) -> None:
    """Persist normalized config fields back to autoslurm config JSON."""
    path = config_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "machines": config["machines"],
        "default_machine": config["default_machine"],
        "bundle_filter_mode": str(config.get("bundle_filter_mode", "active")).strip().lower(),
    }
    atomic_json(path, data, indent=4)


def load_config() -> dict:
    """
    Loads the configuration file.

    Returns:
    dict: The loaded configuration.

    Raises:
    EnvironmentError: If the configuration file is not found.
    """
    path = config_file_path()
    legacy_path = path.parent / "src" / path.name
    if STORAGE_ROOT_ENVIRONMENT_VARIABLE not in os.environ and not path.exists() and legacy_path.exists():
        path = legacy_path
    if not path.exists():
        raise EnvironmentError(
            f"Configuration file not found at {path}. Please use `autoslurm configuration` to create the configurations for autoslurm."
        )
    with open(path, "r") as file:
        raw = json.load(file)
    return _normalize_config(raw)


def machine_config(
    args: Optional[Namespace] = None,
    machine: Optional[str] = None,
    overrides: Optional[dict] = None,
) -> tuple[str, dict]:
    config = load_config()
    machines = config["machines"]
    final_overrides = dict(overrides or {})
    machine_name = machine
    if args is not None:
        machine_name = machine_name or args.machine
        if args.hosturl is not None or args.hostname is not None:
            for key in ["slurm_account"]:
                if getattr(args, key, None) is None:
                    raise AttributeError(
                        f"Custom machine configuration with 'hosturl' requires {key}."
                    )
            for key in MACHINE_KEYS:
                value = getattr(args, key, None)
                if value is not None:
                    final_overrides[key] = value
        over_keys = ["env_command", "venv_path", "slurm_account"]
        for key in over_keys:
            value = getattr(args, key, None)
            if value is not None:
                final_overrides[key] = value
    if machine_name is None:
        machine_name = config["default_machine"]
    if machine_name not in machines:
        raise EnvironmentError(
            f"No configuration found for machine: {machine_name}"
        )
    machine_config_ = dict(machines.get(machine_name, {}))
    machine_config_.update(final_overrides)
    if machine_config_.get("slurm_account") is None:
        raise AttributeError(
            "'slurm_account' account must be provided. Rerun with --slurm_account option or rerun autoslurm-configuration to edit the configuration for the machine."
        )
    if not activation_command_from_config(machine_config_):
        raise AttributeError(
            "Either 'venv_path' or legacy 'env_command' must be provided. "
            "Rerun with --venv_path option or rerun autoslurm-configuration."
        )
    return machine_name, machine_config_
