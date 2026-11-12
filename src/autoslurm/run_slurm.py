import os
import re
import shlex
import subprocess
import json
import tempfile
import shutil
from contextlib import contextmanager
from typing import Optional
from .config import load_config
from .transport import ssh_command, remote_storage_root_from_config
from .storage import ensure_storage_dirs, slurm_dir, storage_root, STORAGE_ROOT_ENVIRONMENT_VARIABLE
from .submission import SubmissionError, SUBMISSION_PROTOCOL, validate_receipt

__all__ = [
    "get_job_id_from_sbatch_output",
    "run_slurm_remotely",
    "run_slurm_locally",
    "ssh_submission_session",
    "run_bulk_submit_driver_remotely",
    "probe_submission_helper",
]


def get_job_id_from_sbatch_output(output):
    """Extracts the job ID from the output of an sbatch command."""
    match = re.search(r"Submitted batch job (\d+)", output)
    if match:
        return match.group(1)
    else:
        raise ValueError(f"Unable to capture job ID from sbatch output {output}")


def run_slurm_remotely(
    slurm_name,
    machine: Optional[str] = None,
    machine_config: Optional[dict] = None,
    ssh_options: Optional[list[str]] = None,
    *, context=None,
):
    """
    Runs a SLURM script on a remote machine via SSH and captures the job ID.

    Args:
        slurm_name (str): The name of the SLURM script to run.
        machine (Optional[str]): The name of the machine to run the script on.
        machine_config (Optional[dict]): The configuration details for the remote machine.

    Returns:
        str: The job ID assigned by SLURM.

    """
    if context is not None:
        machine_config = context.config
    if machine is not None and context is None:
        machine_config = load_config().get(machine)
        if not machine_config:
            raise EnvironmentError(f"No configuration found for machine: {machine}")

    remote_path = context.storage_root if context else remote_storage_root_from_config(
        machine_config, machine
    )
    script_path = os.path.join(remote_path, "slurm", slurm_name)
    command = ssh_command(machine_config, machine, f"sbatch {shlex.quote(script_path)}", options=ssh_options)

    # Run the sbatch command on the remote machine
    result = subprocess.run(command, capture_output=True, text=True)

    # Check for errors
    if result.returncode != 0:
        raise ValueError(f"Error running sbatch command: {result.stderr}")

    output = result.stdout
    return get_job_id_from_sbatch_output(output)


@contextmanager
def ssh_submission_session(
    machine_config: Optional[dict],
    machine_name: Optional[str] = None,
):
    """
    Provide SSH options that reuse a single multiplexed connection for repeated submits.
    Falls back to no-op when no remote host is configured.
    """
    if machine_config is None:
        yield None
        return
    if not (machine_config.get("hostname") or machine_config.get("hosturl")):
        yield None
        return

    tmpdir = tempfile.mkdtemp(prefix="autoslurm-ssh-")
    control_path = os.path.join(tmpdir, "cm-%C")
    ssh_options = [
        "-o",
        "ControlMaster=auto",
        "-o",
        f"ControlPath={control_path}",
        "-o",
        "ControlPersist=600",
    ]

    try:
        open_command = ssh_command(machine_config, machine_name, options=[*ssh_options, "-MNf"])
        result = subprocess.run(open_command, capture_output=True, text=True)
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(
                f"Unable to open SSH multiplexed session for '{machine_name or machine_config.get('hostname', machine_config.get('hosturl', ''))}': {message}"
            )
        yield ssh_options
    finally:
        try:
            close_command = ssh_command(machine_config, machine_name, options=[*ssh_options, "-O", "exit"])
            subprocess.run(close_command, capture_output=True, text=True)
        except Exception:
            pass  # Connection cleanup must not erase an already observed receipt.
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


def run_slurm_locally(slurm_name):
    """Runs a SLURM script locally and captures the job ID."""
    ensure_storage_dirs()
    script_path = os.path.join(slurm_dir(), slurm_name)

    result = subprocess.run(["sbatch", script_path], capture_output=True, text=True)
    return get_job_id_from_sbatch_output(result.stdout)


def run_bulk_submit_driver_remotely(
    payload: dict,
    machine: Optional[str] = None,
    machine_config: Optional[dict] = None,
    ssh_options: Optional[list[str]] = None,
    *, context=None,
) -> dict:
    """
    Execute the internal bulk-submit driver on a remote machine and return job ids.
    """
    if context is not None:
        machine_config = context.config
    if machine is not None and context is None:
        machine_config = load_config().get(machine)
        if not machine_config:
            raise EnvironmentError(f"No configuration found for machine: {machine}")

    command = ssh_command(machine_config, machine, options=ssh_options)
    venv_path = machine_config.get("venv_path")
    if not (isinstance(venv_path, str) and venv_path.strip()):
        raise RuntimeError(
            "Bulk remote submission requires 'venv_path' in machine configuration."
        )
    python_executable = f"{venv_path.rstrip('/')}/bin/python"
    if context is not None or "storage_root" in machine_config:
        remote_root = context.storage_root if context else remote_storage_root_from_config(machine_config, machine)
        if payload.get("slurm_dir") != f"{remote_root.rstrip('/')}/slurm":
            raise ValueError("Bulk payload script directory does not match the selected storage root.")
        command.append(shlex.join([
            "env", f"{STORAGE_ROOT_ENVIRONMENT_VARIABLE}={remote_root}",
            python_executable, "-m", "autoslurm.apps.bulk_submit_driver",
        ]))
    else:
        command.extend([python_executable, "-m", "autoslurm.apps.bulk_submit_driver"])

    result = subprocess.run(
        command,
        input=json.dumps(payload),
        capture_output=True,
        text=True,
    )
    try:
        response = json.loads(result.stdout.strip() or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Remote bulk submit driver returned invalid JSON: {result.stdout!r}"
        ) from exc
    if payload.get("receipt") is not None:
        receipt = validate_receipt(response.get("receipt"), payload["receipt"])
        if result.returncode != 0 or not response.get("ok"):
            raise SubmissionError(response.get("error") or "Remote submission stopped.", receipt)
        if receipt.get("state") != "submitted" or not receipt.get("execution_finished"):
            raise SubmissionError("Remote submission did not report a final acceptance outcome.", receipt)
        return receipt
    if result.returncode != 0 or not response.get("ok", False):
        raise RuntimeError(response.get("error", "Remote bulk submit failed."))
    if "job_ids" not in response:
        raise RuntimeError("Remote bulk submit response missing 'job_ids'.")
    return response["job_ids"]


def probe_submission_helper(context):
    """Fail before dispatch if the prepared helper cannot persist receipts."""
    config = context.config
    venv = config.get("venv_path")
    if not isinstance(venv, str) or not venv.strip():
        raise RuntimeError("Receipt-capable remote submission requires a prepared venv_path.")
    command = shlex.join(["env", f"{STORAGE_ROOT_ENVIRONMENT_VARIABLE}={context.storage_root}", venv.rstrip("/") + "/bin/python", "-m", "autoslurm.apps.bulk_submit_driver", "--capabilities"])
    result = subprocess.run(ssh_command(config, context.machine_name, command), capture_output=True, text=True)
    try:
        capable = result.returncode == 0 and json.loads(result.stdout).get("submission_protocol") == SUBMISSION_PROTOCOL
    except (ValueError, AttributeError):
        capable = False
    if not capable:
        raise RuntimeError("Remote helper does not support submission receipts; prepare the matching helper before submitting.")
