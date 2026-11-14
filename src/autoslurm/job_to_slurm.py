import shlex
import re
import subprocess
from io import TextIOWrapper, StringIO
from datetime import datetime
from .utils import name_slurm_script
from .storage import ensure_storage_dirs, slurm_dir
from .config import activation_command_from_config
from .transport import remote_storage_root_from_config
from .execution import resolve_execution_context
from .argument_compilation import compile_script_arguments, render_script_arguments
from .errors import InvalidRequestError, DiagnosticCause


__all__ = ["create_slurm_script"]


def validate_slurm_content(content):
    """Check generated shell syntax without executing activation or application."""
    result = subprocess.run(["bash", "-n"], input=content, capture_output=True, text=True)
    if result.returncode != 0:
        if result.returncode != 2:
            # A killed/unavailable checker is not evidence of invalid shell syntax.
            raise subprocess.CalledProcessError(result.returncode, ["bash", "-n"],
                                                output=result.stdout, stderr=result.stderr)
        # Bash can echo arbitrary application/environment literals in stderr.
        # Report the observed rejection without copying those values.
        line = re.search(r"\bline ([0-9]+):", result.stderr or "")
        location = f" at line {line[1]}" if line else ""
        raise InvalidRequestError(f"Invalid generated shell script{location}; inspect the preview's command and environment setup.",
            field="script", stage="validate_shell",
            cause=DiagnosticCause("ShellSyntaxError", "bash -n rejected the generated script.", returncode=result.returncode))


def create_slurm_script(job: dict, date: datetime, machine_config: dict, *, context=None) -> str:
    """Creates a SLURM script and saves it locally"""
    output = StringIO()
    write_slurm_content(output, job, machine_config, context=context)
    ensure_storage_dirs()
    path = slurm_dir()
    slurm_name = name_slurm_script(job, date)
    file_path = path / slurm_name
    with open(file_path, "w") as f:
        f.write(output.getvalue())
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
    try:
        _validate_render_definition(job)
        context = context or resolve_execution_context(machine_config=machine_config, root_resolver=remote_storage_root_from_config)
        _write_slurm_content(file, job, context, resolved)
    except InvalidRequestError as error:
        error.diagnostic = error.diagnostic.with_context(
            job=job.get("name") if isinstance(job, dict) and isinstance(job.get("name"), str) else None)
        if context is not None:
            error.diagnostic = error.diagnostic.with_context(machine=context.machine_name)
        raise


def _validate_render_definition(job, *, stage="render_script"):
    """Shared structural guards for preparation and direct script creation."""
    facts = {"job": job.get("name") if isinstance(job, dict) and isinstance(job.get("name"), str) else None}
    def invalid(message, field):
        return InvalidRequestError(message, field=field, stage=stage, context=facts)
    if not isinstance(job, dict):
        raise invalid("Every job must be a dictionary.", "job")
    if not isinstance(job.get("script"), str) or not job["script"].strip() or "\x00" in job["script"]:
        raise invalid("Every job needs a nonempty application command without NUL characters.", "script")
    if not isinstance(job.get("name"), str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", job["name"]):
        raise invalid("Job names must be simple names without path separators.", "name")
    if not isinstance(job.get("slurm", {}), dict):
        raise invalid("Job slurm options must be a mapping.", "slurm")
    for field in ("script_args", "environment", "runtime_environment"):
        if job.get(field) is not None and not isinstance(job[field], dict):
            raise invalid(f"{field} must be a mapping.", field)
    for key, value in job.get("slurm", {}).items():
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", key):
            raise invalid("Slurm option names must be simple directive names.", "slurm")
        if value is not None and (type(value) not in (str, int, float, bool)
                or any(ord(c) < 32 or ord(c) == 127 for c in str(value))):
            raise invalid("Slurm directives must be scalar values without control characters.", f"slurm.{key}")


def _write_slurm_content(file, job, context, resolved):
    machine_config = context.config
    resolved = context.resolve_job(job) if resolved is None else resolved
    arguments = compile_script_arguments(resolved["script_args"])
    env_command = activation_command_from_config(machine_config)
    slurm_account = machine_config.get("slurm_account", "")
    exports = []
    literal = job.get("environment") or {}
    runtime = job.get("runtime_environment") or {}
    if literal.keys() & runtime.keys():
        raise InvalidRequestError("An environment variable cannot have both literal and runtime values.", field="environment", stage="render_script")
    for key, value in literal.items():
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) or type(value) not in (str, int, float, bool) or any(ord(c) < 32 or ord(c) == 127 for c in str(value)):
            raise InvalidRequestError("Environment names and literal scalar values must be valid shell exports.", field="environment", stage="render_script")
        exports.append(f"export {key}={shlex.quote(str(value))}\n")
    for key, source in runtime.items():
        if any(not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) for name in (key, source)):
            raise InvalidRequestError("Runtime environment values must name a single shell variable.", field="runtime_environment", stage="render_script")
        exports.append(f'export {key}="${{{source}:?Required runtime variable {source} is unset or empty}}"\n')

    file.write("#!/bin/bash\n")
    if slurm_account:
        file.write(f"#SBATCH --account={slurm_account}\n")
    file.write(f"#SBATCH --output={shlex.quote(resolved['log_pattern'])}\n")
    file.write(f"#SBATCH --job-name={job['name']}\n")
    if resolved["working_directory"]:
        file.write(f"#SBATCH --chdir={shlex.quote(resolved['working_directory'])}\n")

    # SLURM directives
    slurm_options = dict(job["slurm"])
    if job.get("dependencies") and all(
        slurm_options.get(key) is None
        for key in ("kill_on_invalid_dep", "kill-on-invalid-dep")
    ):
        slurm_options["kill_on_invalid_dep"] = "yes"
    for key, value in slurm_options.items():
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
