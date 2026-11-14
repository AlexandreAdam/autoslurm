"""Machine configuration normalization, selection and persistence."""

from typing import Optional
from argparse import Namespace
import os
import json
import shlex
import re
from pathlib import Path
from collections.abc import Mapping

from .record_files import atomic_json
from .definitions import MACHINE_KEYS
from .storage import config_file_path, STORAGE_ROOT_ENVIRONMENT_VARIABLE
from .machine_paths import absolute_machine_path
from .errors import ConfigurationError, DiagnosticCause, configuration_failure

__all__ = ["load_config", "save_config", "machine_config", "activation_command_from_config"]


LEGACY_CONNECTION_FIELDS = ("hostname", "hosturl", "username", "key_path")


def _configuration_error(message=None, *, field=None, machine=None, path=None,
                         stage="validate_profile", problem="invalid", cause=None,
                         detail=None, context=None):
    facts = dict(context or {})
    for key, value in (("field", field), ("machine", machine), ("path", str(path) if path is not None else None)):
        if value is not None:
            facts[key] = value
    diagnostic = configuration_failure(stage=stage, problem=problem, summary=message,
        context=facts, cause=DiagnosticCause.from_exception(cause, detail=detail) if cause is not None else None,
        effects={"config_write": "not_started"})
    return ConfigurationError(diagnostic)


def _validate_activation_settings(profile, *, machine=None, path=None):
    for field in ("venv_path", "env_command"):
        if profile.get(field) is not None and not isinstance(profile[field], str):
            raise _configuration_error(f"{field} must be a string or unset.",
                                       field=field, machine=machine, path=path)


def validate_ssh_alias(alias, *, machine=None, path=None):
    """One literal SSH-config selector, never an option, username or command."""
    if not isinstance(alias, str) or re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", alias) is None:
        raise _configuration_error("ssh_alias must be one nonempty SSH config alias without a username, options or whitespace.",
                                   field="ssh_alias", machine=machine, path=path)
    return alias


def recorded_transport(config):
    """Save aliases for new profiles; retain old transport shapes when reading history."""
    if "ssh_alias" in config:
        return {"ssh_alias": validate_ssh_alias(config["ssh_alias"])}
    return {key: config[key] for key in LEGACY_CONNECTION_FIELDS if key in config}


def normalize_machine_profile(profile, *, machine=None, path=None):
    """Use two scientific roots; reject ambiguous old input/output configurations."""
    if not isinstance(profile, Mapping):
        raise _configuration_error("Machine profile must be a dictionary.",
                                   field="machines", machine=machine, path=path)
    profile = dict(profile)
    _validate_activation_settings(profile, machine=machine, path=path)
    account = profile.get("slurm_account")
    if account is None or (isinstance(account, str) and not account.strip()):
        profile.pop("slurm_account", None)
    elif isinstance(account, str):
        profile["slurm_account"] = account.strip()
    else:
        raise _configuration_error("slurm_account must be a string or unset.",
                                   field="slurm_account", machine=machine, path=path)
    alias = profile.get("ssh_alias", profile.get("hostname"))
    if "ssh_alias" in profile or profile.get("hostname") is not None:
        profile["ssh_alias"] = validate_ssh_alias(alias, machine=machine, path=path)
    elif any(profile.get(key) is not None for key in LEGACY_CONNECTION_FIELDS):
        raise _configuration_error("Configure ssh_alias; put HostName, User and IdentityFile in your SSH config. Use asl config --machine NAME --ssh-alias ALIAS.",
                                   field="ssh_alias", machine=machine, path=path)
    for key in LEGACY_CONNECTION_FIELDS:
        profile.pop(key, None)
    for key in ("software_root", "results_root", "project_root"):
        if key in profile:
            try:
                profile[key] = absolute_machine_path(profile[key], f"Machine {key}")
            except ValueError as error:
                context = {"logical_path": profile[key]} if isinstance(profile[key], str) else {}
                raise _configuration_error(str(error), field=key, machine=machine, path=path,
                                           cause=error, context=context) from error
    if "project_root" in profile:
        old = profile.pop("project_root")
        if "results_root" in profile and profile["results_root"] != old:
            raise _configuration_error(
                "project_root has been merged into results_root. Choose one results_root "
                "for inputs, working directories and outputs, and remove project_root "
                "from the machine profile. Existing saved execution paths are unchanged.",
                field="results_root", machine=machine, path=path,
            )
        profile["results_root"] = old
    return profile


def is_remote_machine(config):
    """One data-only rule for current and recorded transport profiles."""
    return "ssh_alias" in config or bool(config.get("hostname") or config.get("hosturl") or config.get("username"))


def activation_command_from_config(machine_config: dict) -> str:
    """Return environment activation command from structured machine config."""
    if not isinstance(machine_config, Mapping):
        raise _configuration_error("Machine profile must be a dictionary.", field="machines")
    _validate_activation_settings(machine_config)
    env_command = machine_config.get("env_command", "")
    commands = [env_command.strip()] if isinstance(env_command, str) and env_command.strip() else []
    venv_path = machine_config.get("venv_path")
    if isinstance(venv_path, str) and venv_path.strip():
        commands.append(f"source {shlex.quote(venv_path)}/bin/activate")
    return " && ".join(commands)


def _normalize_config(raw: dict, *, profile_overrides=None, machine=None, path=None) -> dict:
    """
    Normalize the configuration to ensure the structure contains 'machines',
    'default_machine', and an alias 'local' that points to the default machine.
    """
    if not isinstance(raw, Mapping):
        raise _configuration_error("Configuration must be a dictionary.", field="configuration", path=path,
                                   stage="validate_configuration")
    raw = dict(raw)
    machines = raw.get("machines")
    if "machines" not in raw:
        machines = {
            name: value
            for name, value in raw.items()
            if name not in {"default_machine", "bundle_filter_mode"}
        }
    if not isinstance(machines, Mapping):
        raise _configuration_error("The 'machines' entry must be a dictionary.", field="machines", path=path,
                                   stage="validate_configuration")
    for name, profile in machines.items():
        if not isinstance(name, str) or not name.strip() or name in {"machines", "default_machine", "bundle_filter_mode"}:
            raise _configuration_error("Machine names must be nonempty strings distinct from configuration metadata keys.",
                                       field="machines", path=path, stage="validate_configuration")
        if not isinstance(profile, Mapping):
            raise _configuration_error("Machine profile must be a dictionary.",
                                       field="machines", machine=name, path=path, stage="validate_configuration")
    if machine is not None and not isinstance(machine, str):
        raise _configuration_error("Selected machine must be a name string.", field="machine", path=path,
                                   stage="select_profile")
    if profile_overrides:
        selected = machine or raw.get("default_machine") or ("local" if "local" in machines else next(iter(machines), None))
        if not isinstance(selected, str) or selected not in machines:
            raise _configuration_error("No configuration found for the selected machine.",
                                       field="machine", machine=selected if isinstance(selected, str) else None,
                                       path=path, stage="select_profile")
        machines = dict(machines)
        profile = dict(machines[selected])
        profile.update(profile_overrides)
        if "results_root" in profile_overrides:
            profile.pop("project_root", None)
        if "ssh_alias" in profile_overrides:
            for key in LEGACY_CONNECTION_FIELDS:
                profile.pop(key, None)
        machines[selected] = profile
    machines = {name: normalize_machine_profile(value, machine=name, path=path)
                for name, value in machines.items()}
    default_machine = raw.get("default_machine")
    if default_machine is None:
        if "local" in machines:
            default_machine = "local"
        elif machines:
            default_machine = next(iter(machines))
        else:
            raise _configuration_error("No machines defined in the configuration file.",
                                       field="machines", path=path, stage="validate_configuration")
    if not isinstance(default_machine, str) or default_machine not in machines:
        raise _configuration_error("Default machine not found in the configuration file.", field="default_machine",
                                   machine=default_machine if isinstance(default_machine, str) else None,
                                   path=path, stage="validate_configuration")
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
    normalized = _normalize_config(config, path=path)
    data = {
        "machines": normalized["machines"],
        "default_machine": normalized["default_machine"],
        "bundle_filter_mode": normalized["bundle_filter_mode"],
    }
    atomic_json(path, data, indent=4)


def _read_config_file(path):
    try:
        with open(path, "r", encoding="utf-8") as stream:
            return json.load(stream)
    except FileNotFoundError as error:
        # A dangling link or a concurrently created entry must not become a
        # first-use/reset invitation. Publication race protection is separate.
        try:
            path.lstat()
        except FileNotFoundError:
            problem = "missing"
        except OSError as metadata_error:
            raise _configuration_error(path=path, problem="unreadable", stage="read_configuration",
                                       cause=metadata_error) from metadata_error
        else:
            problem = "unreadable"
        raise _configuration_error(path=path, problem=problem, stage="read_configuration", cause=error) from error
    except OSError as error:
        raise _configuration_error(path=path, problem="unreadable", stage="read_configuration", cause=error) from error
    except (json.JSONDecodeError, UnicodeError) as error:
        detail = (f"Invalid JSON at line {error.lineno}, column {error.colno}."
                  if isinstance(error, json.JSONDecodeError) else "Configuration must contain UTF-8 JSON text.")
        raise _configuration_error(path=path, problem="corrupt", stage="read_configuration", cause=error,
                                   detail=detail) from error


def _read_config():
    """Return raw data and source path; only actual absence permits legacy lookup."""
    path = config_file_path()
    try:
        return _read_config_file(path), path
    except ConfigurationError as primary:
        if primary.diagnostic.code != "resource_missing" or STORAGE_ROOT_ENVIRONMENT_VARIABLE in os.environ:
            raise
        legacy = path.parent / "src" / path.name
        try:
            return _read_config_file(legacy), legacy
        except ConfigurationError as secondary:
            if secondary.diagnostic.code == "resource_missing":
                raise primary from primary.__cause__
            raise


def load_config() -> dict:
    """Read and normalize local profiles without contacting any machine."""
    return _load_config_with_path()[0]


def _load_config_with_path():
    """Keep the actual source identity beside normalized data for this operation."""
    raw, path = _read_config()
    return _normalize_config(raw, path=path), path


def set_machine_settings(machine=None, *, software_root=None, results_root=None, ssh_alias=None,
                         slurm_account=None, clear_slurm_account=False):
    """Save profile settings without connecting; None keeps the existing account."""
    if machine is not None and not isinstance(machine, str):
        raise _configuration_error("Selected machine must be a name string.", field="machine", stage="select_profile")
    if clear_slurm_account and slurm_account is not None:
        raise _configuration_error("Set or clear slurm_account, not both.", field="slurm_account",
                                   machine=machine, stage="validate_settings")
    settings = {key: value for key, value in (("software_root", software_root), ("results_root", results_root), ("ssh_alias", ssh_alias), ("slurm_account", slurm_account)) if value is not None}
    if clear_slurm_account:
        settings["slurm_account"] = None
    if not settings:
        raise _configuration_error("Provide software_root, results_root, ssh_alias or an account update.",
                                   field="settings", machine=machine, stage="validate_settings")
    raw, path = _read_config()
    config = _normalize_config(raw, profile_overrides=settings, machine=machine, path=path)
    save_config(config)
    return machine or config["default_machine"]


def machine_config(
    args: Optional[Namespace] = None,
    machine: Optional[str] = None,
    overrides: Optional[dict] = None,
) -> tuple[str, dict]:
    config, path = _load_config_with_path()
    machines = config["machines"]
    if overrides is not None and not isinstance(overrides, Mapping):
        raise _configuration_error("Machine overrides must be a dictionary.", field="overrides",
                                   stage="validate_settings", path=path)
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
    if not isinstance(machine_name, str) or machine_name not in machines:
        raise _configuration_error("No configuration found for the selected machine.", field="machine",
                                   machine=machine_name if isinstance(machine_name, str) else None,
                                   path=path, stage="select_profile")
    machine_config_ = dict(machines.get(machine_name, {}))
    machine_config_.update(final_overrides)
    try:
        machine_config_ = normalize_machine_profile(machine_config_, machine=machine_name, path=path)
    except ConfigurationError as error:
        if final_overrides:
            error.diagnostic = error.diagnostic.with_context(source="profile_overrides")
        raise
    if not activation_command_from_config(machine_config_):
        raise _configuration_error(
            "Either 'venv_path' or legacy 'env_command' must be provided. "
            "Rerun with --venv_path option or rerun asl config.", field="venv_path", machine=machine_name,
            path=path, stage="select_profile",
        )
    return machine_name, machine_config_
