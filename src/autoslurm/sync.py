from __future__ import annotations

from typing import Optional

from .storage import storage_root
from .execution import resolve_execution_context, is_remote_machine
from .transport import remote_storage_root_from_config
from .file_transfer import pull_storage_directory
from .config import machine_config as resolve_machine_config

SYNC_DIRECTORIES = ("jobs", "slurm", "out")


def sync_machine(machine_name: Optional[str] = None) -> None:
    resolved_name, machine = resolve_machine_config(machine=machine_name)

    if not is_remote_machine(machine):
        print(f"Machine '{resolved_name}' is local; nothing to sync.")
        return

    context = resolve_execution_context(resolved_name, machine, root_resolver=remote_storage_root_from_config)
    local_root = storage_root()

    for directory in SYNC_DIRECTORIES:
        output = pull_storage_directory(context, directory, local_root / directory,
                                        mutable=directory == "out")
        if output is None:
            print(f"Skipping missing remote directory '{directory}' on '{resolved_name}'.")
        elif output:
            print(output)

    print(f"Synced jobs, slurm, and out from '{resolved_name}'.")
