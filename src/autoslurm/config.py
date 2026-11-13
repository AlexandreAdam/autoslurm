"""Machine configuration normalization, selection and persistence."""

from typing import Optional
from argparse import Namespace
import os
import json
import shlex
import re
from pathlib import Path

from .record_files import atomic_json
from .definitions import MACHINE_KEYS
from .storage import config_file_path, STORAGE_ROOT_ENVIRONMENT_VARIABLE
from .machine_paths import absolute_machine_path

__all__ = ["load_config", "save_config", "machine_config", "activation_command_from_config"]


LEGACY_CONNECTION_FIELDS = ("hostname", "hosturl", "username", "key_path")


def validate_ssh_alias(alias):
    """One literal SSH-config selector, never an option, username or command."""
    if not isinstance(alias, str) or re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", alias) is None:
        raise ValueError("ssh_alias must be one nonempty SSH config alias without a username, options or whitespace.")
    return alias


def recorded_transport(config):
    """Save aliases for new profiles; retain old transport shapes when reading history."""
    if "ssh_alias" in config:
        return {"ssh_alias": validate_ssh_alias(config["ssh_alias"])}
    return {key: config[key] for key in LEGACY_CONNECTION_FIELDS if key in config}


def normalize_machine_profile(profile):
    """Use two scientific roots; reject ambiguous old input/output configurations."""
    profile = dict(profile)
    account = profile.get("slurm_account")
    if account is None or (isinstance(account, str) and not account.strip()):
        profile.pop("slurm_account", None)
    elif isinstance(account, str):
        profile["slurm_account"] = account.strip()
    else:
        raise ValueError("slurm_account must be a string or unset.")
    alias = profile.get("ssh_alias", profile.get("hostname"))
    if "ssh_alias" in profile or profile.get("hostname") is not None:
        profile["ssh_alias"] = validate_ssh_alias(alias)
    elif any(profile.get(key) is not None for key in LEGACY_CONNECTION_FIELDS):
        raise ValueError("Configure ssh_alias; put HostName, User and IdentityFile in your SSH config. Use asl config --machine NAME --ssh-alias ALIAS.")
    for key in LEGACY_CONNECTION_FIELDS:
        profile.pop(key, None)
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
    return "ssh_alias" in config or bool(config.get("hostname") or config.get("hosturl") or config.get("username"))


def activation_command_from_config(machine_config: dict) -> str:
    """Return environment activation command from structured machine config."""
    venv_path = machine_config.get("venv_path")
    if isinstance(venv_path, str) and venv_path.strip():
        return f"source {shlex.quote(venv_path)}/bin/activate"
    env_command = machine_config.get("env_command", "")
    if isinstance(env_command, str):
        return env_command.strip()
    return ""


def _normalize_config(raw: dict, *, profile_overrides=None, machine=None) -> dict:
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
    if profile_overrides:
        selected = machine or raw.get("default_machine") or ("local" if "local" in machines else next(iter(machines), None))
        if selected not in machines:
            raise ValueError(f"No configuration found for machine: {selected}")
        machines = dict(machines)
        profile = dict(machines[selected])
        profile.update(profile_overrides)
        if "results_root" in profile_overrides:
            profile.pop("project_root", None)
        if "ssh_alias" in profile_overrides:
            for key in LEGACY_CONNECTION_FIELDS:
                profile.pop(key, None)
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


def set_machine_settings(machine=None, *, software_root=None, results_root=None, ssh_alias=None,
                         slurm_account=None, clear_slurm_account=False):
    """Save profile settings without connecting; None keeps the existing account."""
    if clear_slurm_account and slurm_account is not None:
        raise ValueError("Set or clear slurm_account, not both.")
    settings = {key: value for key, value in (("software_root", software_root), ("results_root", results_root), ("ssh_alias", ssh_alias), ("slurm_account", slurm_account)) if value is not None}
    if clear_slurm_account:
        settings["slurm_account"] = None
    if not settings:
        raise ValueError("Provide software_root, results_root, ssh_alias or an account update.")
    config = _normalize_config(_read_config(), profile_overrides=settings, machine=machine)
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
        alias = getattr(args, "ssh_alias", None)
        if alias is not None:
            final_overrides["ssh_alias"] = alias
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
    if not activation_command_from_config(machine_config_):
        raise AttributeError(
            "Either 'venv_path' or legacy 'env_command' must be provided. "
            "Rerun with --venv_path option or rerun asl config."
        )
    return machine_name, machine_config_
