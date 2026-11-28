from __future__ import annotations

from typing import Optional
from dataclasses import replace
from pathlib import Path
import tempfile

from .storage import storage_root
from .execution import resolve_execution_context, is_remote_machine
from .transport import remote_storage_root_from_config
from .file_transfer import pull_storage_directory
from .config import machine_config as resolve_machine_config
from .errors import DiagnosticError
from .record_files import _write_error
from .tracking_sync import import_tracking_directory

SYNC_DIRECTORIES = ("jobs", "slurm", "out")


def sync_machine(machine_name: Optional[str] = None) -> None:
    resolved_name, machine = resolve_machine_config(machine=machine_name)

    if not is_remote_machine(machine):
        print(f"Machine '{resolved_name}' is local; nothing to sync.")
        return

    context = resolve_execution_context(resolved_name, machine, root_resolver=remote_storage_root_from_config)
    local_root = storage_root()

    completed = {}
    import_errors = []
    for directory in SYNC_DIRECTORIES:
        try:
            if directory == "jobs":
                # Never expose raw cluster-local records to workstation status.
                with tempfile.TemporaryDirectory(prefix=".sync-", dir=local_root) as staging:
                    target = Path(staging) / "jobs"
                    output = pull_storage_directory(context, directory, target)
                    if output is not None:
                        counts, import_errors = import_tracking_directory(target, context, local_root)
                        print(f"Tracking: {counts['updated']} imported/updated, "
                              f"{counts['unchanged']} unchanged, {counts['skipped']} untracked/draft files skipped, "
                              f"{counts['not_attempted']} not attempted.")
            else:
                output = pull_storage_directory(context, directory, local_root / directory,
                                                mutable=directory == "out")
        except DiagnosticError as error:
            if error.diagnostic is not None:
                effects = {f'sync_{name}': completed.get(name, 'not_started') for name in SYNC_DIRECTORIES}
                effects[f'sync_{directory}'] = error.diagnostic.effects.get('file_transfer', 'not_started')
                error.diagnostic = replace(error.diagnostic, effects={**error.diagnostic.effects, **effects})
            raise
        except OSError as error:
            effects = {f'sync_{name}': completed.get(name, 'not_started') for name in SYNC_DIRECTORIES}
            effects[f'sync_{directory}'] = 'unknown'
            raise _write_error(error, local_root, 'stage_sync', effects) from error
        completed[directory] = 'succeeded' if output is not None else 'not_started'
        if output is None:
            print(f"Skipping missing remote directory '{directory}' on '{resolved_name}'.")
        elif output:
            print(output)

    if import_errors:
        first = import_errors[0]
        if first.diagnostic:
            diagnostic = replace(first.diagnostic, effects={**first.diagnostic.effects,
                **{f'sync_{name}': completed.get(name, 'not_started') for name in SYNC_DIRECTORIES},
                'tracking_import': 'partial'})
            for error in import_errors[1:4]:
                if error.diagnostic:
                    diagnostic = diagnostic.with_secondary(error.diagnostic)
            first.diagnostic = diagnostic
        print(f"Tracking sync incomplete: {len(import_errors)} problem(s); healthy imports and existing evidence retained.")
        raise first
    print(f"Synced tracking, slurm, and out from '{resolved_name}'.")
