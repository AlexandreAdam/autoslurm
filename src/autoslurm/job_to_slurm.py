import shlex
import re
import subprocess
from io import TextIOWrapper
from datetime import datetime
from .utils import name_slurm_script
from .storage import ensure_storage_dirs, slurm_dir
from .config import activation_command_from_config
from .transport import remote_storage_root_from_config
from .execution import resolve_execution_context
from .argument_compilation import compile_script_arguments, render_script_arguments


__all__ = ["create_slurm_script"]


def validate_slurm_content(content):
    """Check generated shell syntax without executing activation or application."""
    result = subprocess.run(["bash", "-n"], input=content, capture_output=True, text=True)
    if result.returncode != 0:
        raise ValueError(f"Invalid generated shell script: {result.stderr.strip()}")


def create_slurm_script(job: dict, date: datetime, machine_config: dict, *, context=None) -> str:
    """Creates a SLURM script and saves it locally"""
    ensure_storage_dirs()
    path = slurm_dir()
    slurm_name = name_slurm_script(job, date)
    file_path = path / slurm_name
    with open(file_path, "w") as f:
        write_slurm_content(f, job, machine_config, context=context)
    print(f"Saved SLURM script {slurm_name} locally")
    return slurm_name


def _write_script_args(file: TextIOWrapper, job_args: list[str]) -> None:
    for idx, line in enumerate(job_args):
        suffix = " \\\n" if idx < len(job_args) - 1 else "\n"
        file.write(line + suffix)


def write_slurm_content(file: TextIOWrapper, job: dict, machine_config: dict, *, context=None, resolved=None) -> None:
    """
    Write a SLURM script using resolved paths and the shared literal compiler.
    """
    context = context or resolve_execution_context(machine_config=machine_config, root_resolver=remote_storage_root_from_config)
    machine_config = context.config
    resolved = context.resolve_job(job) if resolved is None else resolved
    arguments = compile_script_arguments(resolved["script_args"])
    env_command = activation_command_from_config(machine_config)
    slurm_account = machine_config.get("slurm_account", "")
    exports = []
    literal = job.get("environment") or {}
    runtime = job.get("runtime_environment") or {}
    if not isinstance(literal, dict) or not isinstance(runtime, dict):
        raise ValueError("environment and runtime_environment must be mappings.")
    if literal.keys() & runtime.keys():
        raise ValueError("An environment variable cannot have both literal and runtime values.")
    for key, value in literal.items():
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) or not isinstance(value, (str, int, float, bool)) or "\x00" in str(value) or "\n" in str(value):
            raise ValueError("Environment names and literal scalar values must be valid shell exports.")
        exports.append(f"export {key}={shlex.quote(str(value))}\n")
    for key, source in runtime.items():
        if any(not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) for name in (key, source)):
            raise ValueError("Runtime environment values must name a single shell variable.")
        exports.append(f'export {key}="${{{source}:?Required runtime variable {source} is unset or empty}}"\n')

    file.write("#!/bin/bash\n")
    if slurm_account:
        file.write(f"#SBATCH --account={slurm_account}\n")
    file.write(f"#SBATCH --output={shlex.quote(resolved['log_pattern'])}\n")
    file.write(f"#SBATCH --job-name={job['name']}\n")
    if resolved["working_directory"]:
        file.write(f"#SBATCH --chdir={shlex.quote(resolved['working_directory'])}\n")

    # SLURM directives
    for key, value in job["slurm"].items():
        if value is not None and key != "output":
            file.write(f"#SBATCH --{key.replace('_', '-')}={value}\n")

    # Environment activation command
    if resolved["working_directory"]:
        file.write(f"cd -- {shlex.quote(resolved['working_directory'])} || exit 1\n")
    if env_command:
        file.write(f"{env_command}\n")
        if resolved["working_directory"]:
            file.write('if [ "$?" -ne 0 ]; then echo "AutoSlurm environment activation failed" >&2; exit 1; fi\n')
            file.write(f"cd -- {shlex.quote(resolved['working_directory'])} || exit 1\n")

    # Main command and arguments
    file.writelines(exports)
    lines = render_script_arguments(arguments)
    if lines:
        file.write(f"{job['script']} \\\n")
        _write_script_args(file, lines)
    else:
        file.write(f"{job['script']}\n")
