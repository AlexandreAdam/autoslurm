from __future__ import annotations

from typing import Optional
from dataclasses import replace

from .storage import storage_root
from .execution import resolve_execution_context, is_remote_machine
from .transport import remote_storage_root_from_config
from .file_transfer import pull_storage_directory
from .config import machine_config as resolve_machine_config
from .errors import DiagnosticError

SYNC_DIRECTORIES = ("jobs", "slurm", "out")


def sync_machine(machine_name: Optional[str] = None) -> None:
    resolved_name, machine = resolve_machine_config(machine=machine_name)

    if not is_remote_machine(machine):
        print(f"Machine '{resolved_name}' is local; nothing to sync.")
        return

    context = resolve_execution_context(resolved_name, machine, root_resolver=remote_storage_root_from_config)
    local_root = storage_root()

    completed = {}
    for directory in SYNC_DIRECTORIES:
        try:
            output = pull_storage_directory(context, directory, local_root / directory,
                                            mutable=directory == "out")
        except DiagnosticError as error:
            if error.diagnostic is not None:
                effects = {f'sync_{name}': completed.get(name, 'not_started') for name in SYNC_DIRECTORIES}
                effects[f'sync_{directory}'] = error.diagnostic.effects.get('file_transfer', 'not_started')
                error.diagnostic = replace(error.diagnostic, effects={**error.diagnostic.effects, **effects})
            raise
        completed[directory] = 'succeeded' if output is not None else 'not_started'
        if output is None:
            print(f"Skipping missing remote directory '{directory}' on '{resolved_name}'.")
        elif output:
            print(output)

    print(f"Synced jobs, slurm, and out from '{resolved_name}'.")
