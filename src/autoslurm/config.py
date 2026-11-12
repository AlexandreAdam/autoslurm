"""Machine configuration normalization, selection and persistence."""

from typing import Optional
from argparse import Namespace
import os
import json
import shlex
import posixpath
from pathlib import Path, PurePosixPath

from .record_files import atomic_json
from .definitions import MACHINE_KEYS
from .storage import config_file_path, STORAGE_ROOT_ENVIRONMENT_VARIABLE

__all__ = ["load_config", "save_config", "machine_config", "activation_command_from_config"]


def absolute_machine_path(value, label):
    """Normalize an infrastructure path without probing a local or remote host."""
    if not isinstance(value, (str, Path)) or not str(value).strip() or not PurePosixPath(str(value)).is_absolute():
        raise ValueError(f"{label} must be a nonempty absolute machine path.")
    return posixpath.normpath(str(value))


def normalize_machine_profile(profile):
    """Use two scientific roots; reject ambiguous old input/output configurations."""
    profile = dict(profile)
    for key in ("software_root", "results_root", "project_root"):
        if key in profile:
            profile[key] = absolute_machine_path(profile[key], f"Machine {key}")
    if "project_root" in profile:
        old = profile.pop("project_root")
        if "results_root" in profile and profile["results_root"] != old:
            raise ValueError(
                "project_root has been merged into results_root. Choose one results_root "
                "for inputs, working directories and outputs, and remove project_root "
                "from the machine profile. Existing saved execution paths are unchanged."
            )
        profile["results_root"] = old
    return profile


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


def _normalize_config(raw: dict, *, root_overrides=None, machine=None) -> dict:
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
    if root_overrides:
        selected = machine or raw.get("default_machine") or ("local" if "local" in machines else next(iter(machines), None))
        if selected not in machines:
            raise ValueError(f"No configuration found for machine: {selected}")
        machines = dict(machines)
        profile = dict(machines[selected])
        profile.update(root_overrides)
        if "results_root" in root_overrides:
            profile.pop("project_root", None)
        machines[selected] = profile
    machines = {name: normalize_machine_profile(value) if isinstance(value, dict) else value
                for name, value in machines.items()}
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
        "machines": {name: normalize_machine_profile(value) for name, value in config["machines"].items()},
        "default_machine": config["default_machine"],
        "bundle_filter_mode": str(config.get("bundle_filter_mode", "active")).strip().lower(),
    }
    atomic_json(path, data, indent=4)


def _read_config():
    """Read raw configuration so an explicit root edit can resolve an old split."""
    path = config_file_path()
    legacy_path = path.parent / "src" / path.name
    if STORAGE_ROOT_ENVIRONMENT_VARIABLE not in os.environ and not path.exists() and legacy_path.exists():
        path = legacy_path
    if not path.exists():
        raise EnvironmentError(
            f"Configuration file not found at {path}. Please use `asl config` to create the configurations for autoslurm."
        )
    with open(path, "r") as file:
        raw = json.load(file)
    return raw


def load_config() -> dict:
    """Read and normalize local profiles without contacting any machine."""
    return _normalize_config(_read_config())


def set_machine_roots(machine=None, *, software_root=None, results_root=None):
    """Save explicitly selected roots, preserving other fields and historical runs."""
    roots = {key: value for key, value in (("software_root", software_root), ("results_root", results_root)) if value is not None}
    if not roots:
        raise ValueError("Provide software_root or results_root.")
    config = _normalize_config(_read_config(), root_overrides=roots, machine=machine)
    save_config(config)
    return machine or config["default_machine"]


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
    machine_config_ = normalize_machine_profile(machine_config_)
    if machine_config_.get("slurm_account") is None:
        raise AttributeError(
            "'slurm_account' account must be provided. Rerun with --slurm_account option or rerun asl config to edit the configuration for the machine."
        )
    if not activation_command_from_config(machine_config_):
        raise AttributeError(
            "Either 'venv_path' or legacy 'env_command' must be provided. "
            "Rerun with --venv_path option or rerun asl config."
        )
    return machine_name, machine_config_
