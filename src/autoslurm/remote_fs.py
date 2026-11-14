"""Path lookup through the same context used for preview and execution."""

import shlex
import subprocess
from pathlib import PurePosixPath

from .execution import resolve_execution_context, execution_context_from_snapshot, is_remote_machine
from .config import machine_config as resolve_machine_config
from .transport import remote_storage_root_from_config, ssh_command
from .errors import InvalidRequestError

__all__ = ["resolve_results_path", "path_exists"]


def _context(machine_name, context, bundle_path, job_name):
    if bundle_path is not None:
        if context is not None or machine_name is not None:
            raise InvalidRequestError("Select either a saved execution or a current machine/context.", field="bundle_path", stage="resolve_path", context={"bundle_path": str(bundle_path)})
        return execution_context_from_snapshot(bundle_path, job_name)
    if context is not None:
        return context
    name, config = resolve_machine_config(machine=machine_name)
    return resolve_execution_context(name, config, root_resolver=remote_storage_root_from_config)


def resolve_results_path(relative_path, *, machine_name=None, context=None, bundle_path=None, job_name=None):
    """Resolve results using a current context or the exact producing saved job."""
    if isinstance(relative_path, str) and PurePosixPath(relative_path).is_absolute() and context is None and bundle_path is None:
        # Preserve absolute local lookup without discovery, using the same validation.
        from .execution import ExecutionContext
        return ExecutionContext(machine_name, {}, "/", "/", "/", False).resolve_path(relative_path)
    selected = _context(machine_name, context, bundle_path, job_name)
    return selected.resolve_path(relative_path, "results")


def path_exists(path, *, machine_name=None, context=None, base="results", bundle_path=None, job_name=None):
    """Check a declared-base path on the selected or recorded producing machine."""
    if isinstance(path, str) and PurePosixPath(path).is_absolute() and context is None and bundle_path is None:
        name, config = resolve_machine_config(machine=machine_name)
        from .execution import ExecutionContext
        resolved = ExecutionContext(name, config, "/", "/", "/", is_remote_machine(config)).resolve_path(path, base)
        remote = is_remote_machine(config)
    else:
        selected = _context(machine_name, context, bundle_path, job_name)
        resolved, remote = selected.resolve_path(path, base), selected.is_remote
        name, config = selected.machine_name, selected.config
    if remote:
        command = ssh_command(config, name, f"test -e {shlex.quote(resolved)}")
    else:
        command = ["test", "-e", resolved]
    result = subprocess.run(command, capture_output=True, text=True)
    return result.returncode == 0
