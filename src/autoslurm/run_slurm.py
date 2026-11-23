import os
import re
import shlex
import subprocess
import json
from contextlib import contextmanager
from typing import Optional
from .config import load_config, is_remote_machine
from .transport import ssh_command, remote_storage_root_from_config
from .storage import ensure_storage_dirs, slurm_dir, storage_root, STORAGE_ROOT_ENVIRONMENT_VARIABLE
from .submission import SubmissionError, SUBMISSION_PROTOCOL, validate_receipt
from .remote_readiness import readiness_context, configured_python, run_readiness_probe, check_helper_capabilities
from .ssh_session_resources import OwnedSSHSession

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
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)

    # Check for errors
    if result.returncode != 0:
        raise ValueError(f"Error running sbatch command: {result.stderr}")

    output = result.stdout
    return get_job_id_from_sbatch_output(output)


def _configured_shared_connection(machine_config, machine_name):
    """Inspect effective SSH settings without opening/managing a connection."""
    try:
        result = subprocess.run(
            ssh_command(machine_config, machine_name, options=["-G"]),
            capture_output=True, text=True, timeout=10,
        )
        if (type(result.returncode) is not int or result.returncode or not isinstance(result.stdout, str)
                or len(result.stdout.encode('utf-8')) > 65536):
            return False
        settings = {}
        for line in result.stdout.splitlines():
            fields = line.split(None, 1)
            if len(fields) == 2:
                key = fields[0].lower()
                if key in settings and key in {'controlpath', 'controlpersist', 'controlmaster'}:
                    return False  # Ambiguous output is not proof of user ownership.
                settings[key] = fields[1].strip().lower()
        path = settings.get("controlpath", "none")
        persist = settings.get("controlpersist", "no")
        # ssh -G normalizes a duration to seconds; arbitrary text is not proof
        # that persistence was configured successfully.
        persistent = persist == "yes" or re.fullmatch(r"[1-9][0-9]*", persist) is not None
        return path not in {"", "none"} and (
            settings.get("controlmaster") in {"auto", "autoask"}
            or persistent
        )
    except (OSError, subprocess.SubprocessError, UnicodeError):
        return False  # Configuration inspection failure is not a submit failure.


@contextmanager
def ssh_submission_session(
    machine_config: Optional[dict],
    machine_name: Optional[str] = None,
):
    """
    Reuse configured SSH sharing; otherwise own one short-path master session.
    User-managed connections are never opened/closed explicitly by AutoSlurm.
    """
    if machine_config is None:
        yield None
        return
    machine_config = dict(machine_config)
    if not is_remote_machine(machine_config):
        yield None
        return

    destination = ssh_command(machine_config, machine_name)  # Validate before allocating resources.
    if _configured_shared_connection(machine_config, machine_name):
        yield []
        return

    facts = {'command': 'ssh', 'resource': 'owned_ssh_session'}
    if machine_name is not None:
        facts['machine'] = machine_name
    if 'ssh_alias' in machine_config:
        facts['ssh_alias'] = machine_config['ssh_alias']
    session = OwnedSSHSession.create(destination, facts)
    primary = None
    try:
        session.open()
        yield list(session.options)
    except BaseException as error:
        primary = error  # Evidence/resource protection; bugs and interrupts stay original.
        raise
    finally:
        issues = session.cleanup()
        cleanup_primary = primary
        if cleanup_primary is None and issues:
            cleanup_primary = issues[0].error
        session.finish(cleanup_primary, issues)
        if primary is None and issues:
            raise issues[0].error


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
        timeout=300,
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
        # Session cleanup is observed by this workstation after helper dispatch,
        # never owned by the execution-side submission response.
        receipt.pop('session_cleanup_diagnostics', None)
        if result.returncode != 0 or not response.get("ok"):
            raise SubmissionError(response.get("error") or "Remote submission stopped.", receipt)
        if payload.get('tracking_bundle') is not None and receipt.get('execution_bundle_path') is None:
            raise SubmissionError('Remote helper did not confirm execution-side tracking; retain this receipt and do not resubmit.', receipt)
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
    python = configured_python(config, context.machine_name)
    facts = readiness_context(config, context.machine_name, field='venv_path', executable=python, path=python)
    facts['storage_root'] = context.storage_root
    command = shlex.join(["env", f"{STORAGE_ROOT_ENVIRONMENT_VARIABLE}={context.storage_root}", python, "-m", "autoslurm.apps.bulk_submit_driver", "--capabilities"])
    output = run_readiness_probe(ssh_command(config, context.machine_name, command),
                                 stage='probe_helper', context=facts)
    from .execution_tracking import EXECUTION_TRACKING_PROTOCOL
    check_helper_capabilities(output, {'submission_protocol': SUBMISSION_PROTOCOL,
                                      'execution_tracking': EXECUTION_TRACKING_PROTOCOL}, context=facts)
