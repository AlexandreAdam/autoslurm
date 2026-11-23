"""Managed-file transfers; persistence never performs transport or retries."""

from datetime import datetime
import errno
from pathlib import Path
from typing import Optional
import shlex

from .config import load_config
from .definitions import DATE_FORMAT
from .execution import resolve_execution_context
from .storage import jobs_dir, slurm_dir
from .transport import scp_host_and_keypath_from_config, remote_storage_root_from_config, ssh_command, noninteractive_ssh_options
from .errors import (ConfigurationError, DiagnosticError, DiagnosticCause, InvalidRequestError,
                     _file_operation_failure)
from .file_commands import run_file_command
from .path_observations import observe_path, path_facts
from .path_probe import probe_path

__all__ = ["transfer_slurm_to_remote", "transfer_slurms_to_remote", "transfer_bundle_to_remote"]


def _selected_profile(machine_name, machine_config):
    if machine_config is None and machine_name is not None:
        machine_config = load_config().get('machines', {}).get(machine_name)
    if machine_config is None:
        message = ('Either machine_name or machine_config must be specified' if machine_name is None
                   else f'No configuration found for machine: {machine_name}')
        diagnostic = _file_operation_failure('configuration_invalid', 'file_transfer', 'select_machine',
            {'machine': machine_name}, {'file_transfer': 'not_started'})
        raise ConfigurationError(message, diagnostic=diagnostic)
    return machine_config


def _transfer_context(machine_name, machine_config, context):
    selected = context if context is not None else resolve_execution_context(
        machine_name, machine_config, root_resolver=remote_storage_root_from_config)
    if not selected.is_remote:
        raise InvalidRequestError('File transfer requires a remote machine profile.',
                                  field='machine', stage='select_machine', context={'machine': selected.machine_name})
    return selected


def _filename(value, field):
    if (not isinstance(value, str) or not value.strip() or value in {'.', '..'}
            or any(c in value for c in '/\\') or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise InvalidRequestError('Managed transfer names must be single filenames without separators or controls.',
                                  field=field, stage='validate_source')
    return value


def _push_files(paths, directory, machine_name, machine_config, context, *, batch=False):
    effects = {'source_validation': 'not_started', 'destination_preparation': 'not_started',
               'file_transfer': 'not_started'}
    if context is None:
        machine_config = _selected_profile(machine_name, machine_config)
    config = context.config if context is not None else machine_config
    machine = context.machine_name if context is not None else machine_name
    for source in paths:
        facts = path_facts(config, machine, str(source), source=str(source), resource=directory)
        try:
            observed = probe_path(str(source), raise_errors=True)
        except OSError as native:
            effects['source_validation'] = 'failed'
            code = 'resource_missing' if native.errno in {errno.ENOENT, errno.ENOTDIR} else 'resource_inaccessible'
            raise DiagnosticError(_file_operation_failure(code, 'file_transfer', 'validate_source', facts, effects,
                DiagnosticCause.from_exception(native, detail='Local transfer source metadata could not be read.'))) from native
        if observed['kind'] != 'file':
            effects['source_validation'] = 'failed'
            raise DiagnosticError(_file_operation_failure('resource_inaccessible', 'file_transfer', 'validate_source',
                facts, effects, DiagnosticCause('PathKind', 'Local transfer sources must be regular files.')))
    effects['source_validation'] = 'succeeded'
    selected = _transfer_context(machine_name, machine_config, context)
    remote_directory = selected.storage_root.rstrip('/') + '/' + directory
    target = remote_directory + '/' if batch else remote_directory + '/' + paths[0].name
    facts = path_facts(selected.config, selected.machine_name, target, source=str(paths[0].parent),
                       resource=f'{len(paths)} {directory} files', storage_root=selected.storage_root)
    host, key = scp_host_and_keypath_from_config(selected.config, selected.machine_name)
    # Validate all addressing before the first remote mutation.
    directories = [remote_directory]
    if batch and directory == 'slurm':
        directories.append(selected.storage_root.rstrip('/') + '/out')
    command = ssh_command(selected.config, selected.machine_name,
                          'mkdir -p ' + ' '.join(shlex.quote(path) for path in directories))
    run_file_command(command, operation='file_transfer', stage='prepare_remote_directories',
        context={**facts, 'command': 'ssh'}, effects=effects, effect='destination_preparation')
    command = ['scp', *noninteractive_ssh_options(), *shlex.split(key), *map(str, paths), f'{host}:{target}']
    run_file_command(command, operation='file_transfer', stage='copy_files', context={**facts, 'command': 'scp'},
                     effects=effects, effect='file_transfer', timeout=300)


def transfer_slurm_to_remote(slurm_name, machine_name: Optional[str] = None,
                             machine_config: Optional[dict] = None, *, context=None) -> None:
    """Transfer one existing script; expected failures carry stage/effect facts."""
    _filename(slurm_name, 'slurm_name')
    _push_files([slurm_dir() / slurm_name], 'slurm', machine_name, machine_config, context)
    print(f'Saved SLURM script {slurm_name} remotely')


def transfer_slurms_to_remote(slurm_names: list[str], machine_name: Optional[str] = None,
                              machine_config: Optional[dict] = None, *, context=None) -> None:
    """Transfer an existing script batch with one SCP call; never replay a failure."""
    if not isinstance(slurm_names, (list, tuple)):
        raise InvalidRequestError('slurm_names must be a list of filenames.', field='slurm_names', stage='validate_source')
    if not slurm_names:
        return
    paths = [slurm_dir() / _filename(name, 'slurm_names') for name in slurm_names]
    _push_files(paths, 'slurm', machine_name, machine_config, context, batch=True)


def transfer_bundle_to_remote(bundle_name: str, date: datetime, machine_name: Optional[str] = None,
                              machine_config: Optional[dict] = None, *, context=None) -> None:
    """Transfer the exact existing bundle JSON to the selected machine jobs directory."""
    _filename(bundle_name, 'bundle_name')
    if not isinstance(date, datetime):
        raise InvalidRequestError('Bundle date must be a datetime.', field='date', stage='validate_source')
    source = jobs_dir() / f'{bundle_name}_{date.strftime(DATE_FORMAT)}.json'
    _push_files([source], 'jobs', machine_name, machine_config, context)


def pull_storage_directory(context, directory: str, local_target: Path, *, mutable=False):
    """Mirror one managed subtree; only observed absence returns None."""
    if directory not in ('jobs', 'slurm', 'out'):
        raise InvalidRequestError('Select a managed jobs, slurm or out directory.', field='directory', stage='select_source')
    source = context.storage_root.rstrip('/') + '/' + directory
    facts = path_facts(context.config, context.machine_name, str(local_target), source=source, resource=directory)
    effects = {'source_observation': 'not_started', 'destination_preparation': 'not_started', 'file_transfer': 'not_started'}
    # Build transport before local mutation; a failed probe cannot create a target.
    host, key = scp_host_and_keypath_from_config(context.config, context.machine_name)
    if not observe_path(source, config=context.config, machine=context.machine_name, remote=True, kind='directory'):
        return None
    effects['source_observation'] = 'succeeded'
    try:
        local_target.mkdir(parents=True, exist_ok=True)
    except OSError as native:
        effects['destination_preparation'] = 'unknown'
        raise DiagnosticError(_file_operation_failure('storage_failed', 'file_transfer', 'prepare_local_directory',
            facts, effects, DiagnosticCause.from_exception(native, detail='Local sync directory preparation failed.'))) from native
    effects['destination_preparation'] = 'succeeded'
    command = ['rsync', '-a', '--checksum' if mutable else '--ignore-existing',
               '-e', shlex.join(['ssh', *noninteractive_ssh_options(), *shlex.split(key)]), f'{host}:{source}/', f'{local_target}/']
    return run_file_command(command, operation='file_transfer', stage='copy_files',
        context={**facts, 'command': 'rsync'}, effects=effects, effect='file_transfer', timeout=300).strip()
