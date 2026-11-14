import argparse
import json
import shlex
import subprocess
import sys
from typing import Dict, Optional

from ..config import activation_command_from_config, load_config, save_config, is_remote_machine, normalize_machine_profile, set_machine_settings, _read_config, _load_config_with_path
from ..errors import ConfigurationError, configuration_failure
from .error_output import exit_with_error
from ..transport import ssh_command, remote_storage_root_from_config
from ..storage import config_file_path


def _refresh_config_aliases(config: Dict[str, Dict]):
    default = config["default_machine"]
    config["local"] = config["machines"][default]
    for name, machine in config["machines"].items():
        config[name] = machine


def _validation_shell_command(machine: Dict) -> str:
    python_probe = "import autoslurm; print(autoslurm.__file__)"
    python_command = f"python -c {shlex.quote(python_probe)}"
    env_command = activation_command_from_config(machine)
    if env_command:
        shell_command = f"{env_command} && {python_command}"
    else:
        shell_command = python_command
    return shell_command


def _validate_machine(machine: Dict, name: str) -> bool:
    if is_remote_machine(machine):
        ssh_probe = ssh_command(machine, name, "true")
        result = subprocess.run(ssh_probe, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"[{name}] SSH connectivity check: failed")
            message = result.stderr.strip() or result.stdout.strip()
            if message:
                print(message)
            return False
        print(f"[{name}] SSH connectivity check: passed")

        validation_command = _validation_shell_command(machine)
        result = subprocess.run(
            ssh_command(
                machine, name, f"bash -lc {shlex.quote(validation_command)}"
            ),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"[{name}] Python environment check: failed")
            message = result.stderr.strip() or result.stdout.strip()
            if message:
                print(message)
            return False
        print(f"[{name}] Python environment check: passed")
        output = result.stdout.strip()
        if output:
            print(output)
        if "storage_root" in machine:
            try:
                root = remote_storage_root_from_config(machine, name)
            except (RuntimeError, ValueError) as exc:
                print(f"[{name}] Storage root check: failed: {exc}")
                return False
            print(f"[{name}] Storage root check: passed: {root}")
        return True

    validation_command = _validation_shell_command(machine)
    result = subprocess.run(["bash", "-lc", validation_command], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[{name}] Python environment check: failed")
        message = result.stderr.strip() or result.stdout.strip()
        if message:
            print(message)
        return False
    print(f"[{name}] Python environment check: passed")
    output = result.stdout.strip()
    if output:
        print(output)
    return True


def _validate_machine_selection(config: Dict):
    name = _select_machine(config, "Choose a machine to validate:")
    if not name:
        return
    machine = config["machines"][name]
    _validate_machine(machine, name)

def _prompt_text(prompt: str, default: Optional[str] = None, required: bool = False) -> str:
    suffix = f" [{default}]" if default else ""
    if not required:
        suffix += " (optional; '-' clears, Enter keeps current value)"
    while True:
        value = input(f"{prompt}{suffix}: ").strip()
        if value == "-":
            if required:
                print("This field is required and cannot be cleared.")
                continue
            return ""
        if value:
            return value
        if default:
            return default
        if required:
            print("This field is required.")
            continue
        return ""


def _prompt_yes_no(prompt: str, default: str = "n") -> bool:
    default = default.lower()
    choices = "Y/n" if default == "y" else "y/N"
    while True:
        value = input(f"{prompt} [{choices}]: ").strip().lower()
        if not value:
            value = default
        if value in ("y", "yes"):
            return True
        if value in ("n", "no"):
            return False
        print("Please answer 'y' or 'n'.")


def _prompt_machine_name(config: Dict, default: str = "machine") -> str:
    existing = set(config["machines"].keys())
    suggested = default
    counter = 1
    while suggested in existing:
        suggested = f"{default}_{counter}"
        counter += 1
    while True:
        name = _prompt_text("Machine name", default=suggested, required=True)
        if name in existing:
            print(f"A machine named '{name}' already exists. Choose another name.")
            continue
        return name


def _prompt_machine_details(existing: Optional[Dict] = None) -> Dict:
    existing = normalize_machine_profile(existing or {})
    venv_path = _prompt_text(
        "Python virtual environment path (absolute or machine-local path to venv root; autoslurm uses <venv_path>/bin/activate)",
        existing.get("venv_path"),
        required=True,
    )
    env_command = _prompt_text(
        "Environment setup command (runs before venv activation; e.g. module load jax/0.11.0)",
        existing.get("env_command"),
    )
    slurm_account = _prompt_text(
        "SLURM account (omit #SBATCH --account when unset)",
        existing.get("slurm_account"),
    )
    remote_default = is_remote_machine(existing)
    is_remote = _prompt_yes_no("Is this a remote machine?", default="y" if remote_default else "n")
    machine = {"venv_path": venv_path, "slurm_account": slurm_account}
    if env_command:
        machine["env_command"] = env_command
    software_root = _prompt_text(
        "Software root (optional absolute directory for repositories and prepared environments)",
        existing.get("software_root"),
    )
    if software_root:
        machine["software_root"] = software_root
    results_root = _prompt_text(
        "Results root (optional absolute data directory for inputs, working directories and outputs)",
        existing.get("results_root"),
    )
    if results_root:
        machine["results_root"] = results_root
    if is_remote:
        if "storage_root" in existing:
            machine["storage_root"] = existing["storage_root"]
        machine["ssh_alias"] = _prompt_text(
            "SSH config alias (Host entry in ~/.ssh/config)", existing.get("ssh_alias"), required=True,
        )
    return normalize_machine_profile(machine)


def _select_machine(config: Dict, prompt: str) -> Optional[str]:
    machines = list(config["machines"].keys())
    if not machines:
        print("No machines are configured yet.")
        return None
    print(prompt)
    for idx, name in enumerate(machines, start=1):
        default_marker = " (default)" if name == config["default_machine"] else ""
        print(f"  {idx}) {name}{default_marker}")
    while True:
        selection = input("Select a number: ").strip()
        if not selection:
            return machines[0]
        if not selection.isdigit():
            print("Please enter a valid number.")
            continue
        idx = int(selection) - 1
        if 0 <= idx < len(machines):
            return machines[idx]
        print("Selection out of range.")


def _create_machine(config: Dict):
    name = _prompt_machine_name(config)
    machine = _prompt_machine_details()
    config["machines"][name] = machine
    _refresh_config_aliases(config)
    save_config(config)
    print(f"Saved machine '{name}'. Running validation...")
    _validate_machine(machine, name)
    if _prompt_yes_no("Make this the default machine?", default="n"):
        config["default_machine"] = name
        _refresh_config_aliases(config)
        save_config(config)


def _update_machine(config: Dict):
    name = _select_machine(config, "Choose a machine to update:")
    if not name:
        return
    machine = _prompt_machine_details(existing=config["machines"][name])
    config["machines"][name] = machine
    _refresh_config_aliases(config)
    save_config(config)
    print(f"Saved machine '{name}'. Running validation...")
    _validate_machine(machine, name)


def _rename_machine(config: Dict):
    old_name = _select_machine(config, "Choose a machine to rename:")
    if not old_name:
        return
    new_name = _prompt_text("New machine name", default=old_name, required=True)
    if new_name == old_name:
        return
    if new_name in config["machines"]:
        print(f"A machine named '{new_name}' already exists. Choose another name.")
        return
    config["machines"][new_name] = config["machines"].pop(old_name)
    if config["default_machine"] == old_name:
        config["default_machine"] = new_name
    _refresh_config_aliases(config)
    save_config(config)


def _change_default_machine(config: Dict):
    name = _select_machine(config, "Choose a machine to become the default:")
    if not name:
        return
    if name == config["default_machine"]:
        print(f"'{name}' is already the default machine.")
        return
    config["default_machine"] = name
    _refresh_config_aliases(config)
    save_config(config)


def _set_default_machine_by_name(config: Dict, name: str, *, path):
    if name not in config["machines"]:
        raise ConfigurationError(configuration_failure(stage="select_profile",
            summary="Selected default machine was not found in configuration.",
            context={"machine": name, "field": "default_machine", "path": str(path)},
            effects={"config_write": "not_started"}))
    if name == config["default_machine"]:
        print(f"'{name}' is already the default machine.")
        return
    config["default_machine"] = name
    _refresh_config_aliases(config)
    save_config(config)


def _create_default_machine():
    print("No AutoSlurm configuration file found. Configure the default machine.")
    config = {"machines": {}, "default_machine": ""}
    name = _prompt_machine_name(config)
    machine = _prompt_machine_details()
    config["machines"][name] = machine
    config["default_machine"] = name
    _refresh_config_aliases(config)
    save_config(config)
    print(f"Default machine saved: {name}")
    return config


def _menu_loop(config: Dict):
    while True:
        print("\nConfigured machines:")
        for name in config["machines"]:
            default_marker = " (default)" if name == config["default_machine"] else ""
            print(f"  - {name}{default_marker}")
        print("\nActions:")
        print("  1) Edit machine fields")
        print("  2) Add machine")
        print("  3) Rename machine")
        print("  4) Set default machine")
        print("  5) Validate machine (SSH + Python env)")
        print("  6) Exit")
        choice = input("Choice: ").strip()
        if choice == "1":
            _update_machine(config)
        elif choice == "2":
            _create_machine(config)
        elif choice == "3":
            _rename_machine(config)
        elif choice == "4":
            _change_default_machine(config)
        elif choice == "5":
            _validate_machine_selection(config)
        elif choice == "6":
            print("Configuration saved.")
            break
        else:
            print("Please choose a valid option (1-6).")


def display_config():
    data, _ = _read_config()
    print(json.dumps(data, indent=4))


def display_config_summary():
    config = load_config()
    print("machine type default ssh_alias slurm_account venv_path software_root results_root")
    for name, machine in config["machines"].items():
        machine_type = "remote" if is_remote_machine(machine) else "local"
        slurm_account = machine.get("slurm_account", "-")
        default_marker = "yes" if name == config["default_machine"] else "no"
        venv_path = machine.get("venv_path", "")
        alias = machine.get("ssh_alias", "-")
        results_root = machine.get("results_root") or "<storage_root>/results"
        software_root = machine.get("software_root") or "<storage_root>/software"
        print(f"{name} {machine_type} {default_marker} {alias} {slurm_account} {venv_path} {software_root} {results_root}")


def _main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(
        prog="asl config",
        description="Configure AutoSlurm machines with separate software and data locations.",
        epilog=(
            "software_root holds repositories and prepared environments. "
            "results_root is the shared base for relative inputs, working directories and outputs. "
            "Keep relative output_dir values in bundles. Defaults: <storage_root>/software "
            "and <storage_root>/results. Saving config never clones or installs software."
        ),
    )
    parser.add_argument("--view", action="store_true", help="Print raw configuration JSON and exit.")
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print one-line machine summaries (type/default/ssh_alias/account/venv/software_root/results_root) and exit.",
    )
    parser.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help="Open interactive configuration editor.",
    )
    parser.add_argument(
        "--set-default",
        help="Set default machine by exact name and exit.",
    )
    parser.add_argument("--ssh-alias", help="Set the SSH config Host alias; SSH manages hostname, user and keys.")
    parser.add_argument("--machine", help="Machine to update (default: configured default).")
    parser.add_argument("--debug", action="store_true", help="Show original exceptions and causes for configuration failures.")
    parser.add_argument("--software-root", help="Set the absolute software directory without connecting to the machine.")
    parser.add_argument("--results-root", help="Set the absolute shared input/output directory; merges an old project_root setting.")
    account = parser.add_mutually_exclusive_group()
    account.add_argument("--slurm-account", help="Set the optional #SBATCH --account value without connecting to the machine.")
    account.add_argument("--clear-slurm-account", action="store_true", help="Remove the configured account; omit its #SBATCH --account directive.")
    if argv is None:
        argv = sys.argv[1:]
    if not argv or argv == ["--debug"]:
        parser.print_help()
        return
    args = parser.parse_args(argv)

    if any(value is not None for value in (args.software_root, args.results_root, args.ssh_alias, args.slurm_account)) or args.clear_slurm_account:
        if args.view or args.summary or args.interactive or args.set_default is not None:
            parser.error("Profile updates cannot be combined with view, summary, interactive or set-default.")
        selected = set_machine_settings(args.machine, software_root=args.software_root, results_root=args.results_root, ssh_alias=args.ssh_alias,
                                        slurm_account=args.slurm_account, clear_slurm_account=args.clear_slurm_account)
        print(f"Saved settings for machine '{selected}'.")
        return
    if args.machine is not None:
        parser.error("--machine requires --ssh-alias, --software-root, --results-root, --slurm-account or --clear-slurm-account.")

    if args.view:
        display_config()
        return

    if args.summary:
        display_config_summary()
        return

    if args.interactive:
        _interactive_config()
        return

    if args.set_default is not None:
        config, path = _load_config_with_path()
        _set_default_machine_by_name(config, args.set_default, path=path)
        return

    _interactive_config()


def _interactive_config():
    try:
        config = load_config()
    except ConfigurationError as error:
        if error.diagnostic.code == "resource_missing":
            _create_default_machine()
            return
        raise
    _menu_loop(config)


def main(argv: list[str] | None = None):
    selected_args = list(sys.argv[1:] if argv is None else argv)
    try:
        return _main(selected_args)
    except ConfigurationError as error:
        exit_with_error(error, debug="--debug" in selected_args)
