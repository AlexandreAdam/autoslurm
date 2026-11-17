"""Validate metadata observations, preserving unavailable versus absent paths."""

import errno
import json
from pathlib import Path

from .errors import DiagnosticCause, DiagnosticError, _file_operation_failure
from .file_commands import run_file_command
from .path_probe import probe_path
from .transport import ssh_command


def path_facts(config, machine, path, **extra):
    facts = {'machine': machine, 'path': path, **extra}
    if 'ssh_alias' in config:
        facts['ssh_alias'] = config['ssh_alias']
    return facts


def _unique_mapping(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Repeated metadata key.')
        result[key] = value
    return result


def _validate_metadata(value, path):
    if (not isinstance(value, dict) or set(value) != {'version', 'path', 'state', 'kind', 'errno'}
            or type(value['version']) is not int or value['version'] != 1 or value['path'] != path):
        raise ValueError('Unexpected metadata identity or shape.')
    state, kind, number = value['state'], value['kind'], value['errno']
    if number is not None and (type(number) is not int or not 1 <= number <= 2**31 - 1):
        raise ValueError('Invalid metadata errno.')
    if state == 'exists' and kind in ('file', 'directory', 'other') and number is None:
        return value
    if kind is None and ((state == 'missing' and number in (errno.ENOENT, errno.ENOTDIR))
                         or (state == 'unavailable' and number not in (errno.ENOENT, errno.ENOTDIR))):
        return value
    raise ValueError('Invalid metadata state.')


def _remote_metadata(paths, config, machine, facts, effects):
    # Same metadata worker as local checks; paths are Python literals, never
    # interpolated shell input. No package installation/import on the host.
    script = Path(__file__).with_name('path_probe.py').read_text()
    query = 'probe_path(' + repr(paths[0]) + ')' if len(paths) == 1 else 'probe_paths(' + repr(paths) + ')'
    script += '\nprint(json.dumps(' + query + '))\n'
    output = run_file_command(ssh_command(config, machine, 'python3 -B -'),
        operation='path_observation', stage='probe_path', context={**facts, 'command': 'ssh', 'executable': 'python3'},
        effects=effects, effect='probe_command', input=script)
    try:
        value = json.loads(output, object_pairs_hook=_unique_mapping)
        if len(paths) == 1:
            values = [value]
        else:
            if (not isinstance(value, dict) or set(value) != {'version', 'paths'}
                    or type(value['version']) is not int or value['version'] != 1
                    or not isinstance(value['paths'], list) or len(value['paths']) != len(paths)):
                raise ValueError('Unexpected metadata batch shape.')
            values = value['paths']
        return [_validate_metadata(item, path) for item, path in zip(values, paths)]
    except (ValueError, RecursionError) as native:
        raise DiagnosticError(_file_operation_failure('protocol_invalid', 'path_observation', 'read_metadata',
            facts, effects, DiagnosticCause.from_exception(native, detail='Expected bounded metadata for the exact selected paths.'))) from native


def _observe_checks(checks, *, config, machine, remote, required):
    if not checks:
        return []
    effects = {'path_observation': 'unknown', 'probe_command': 'not_started'}
    facts = path_facts(config, machine, checks[0][0], **checks[0][2])
    snapshots = _remote_metadata([item[0] for item in checks], config, machine, facts, effects) if remote else None
    observations = []
    for index, (path, kind, extra) in enumerate(checks):
        facts = path_facts(config, machine, path, **extra)
        if remote:
            result = snapshots[index]
        else:
            try:
                result = probe_path(path, raise_errors=True)
            except OSError as native:
                missing = native.errno in {errno.ENOENT, errno.ENOTDIR}
                if missing and not required:
                    observations.append(False)
                    continue
                effects['path_observation'] = 'failed'
                raise DiagnosticError(_file_operation_failure('resource_missing' if missing else 'resource_inaccessible',
                    'path_observation', 'stat_path', facts, effects,
                    DiagnosticCause.from_exception(native, detail='Local required path is missing or its metadata could not be read.'))) from native
        if result['state'] == 'unavailable' or (required and result['state'] == 'missing'):
            effects['path_observation'] = 'failed'
            raise DiagnosticError(_file_operation_failure('resource_missing' if result['state'] == 'missing' else 'resource_inaccessible',
                'path_observation', 'stat_path', facts, effects,
                DiagnosticCause('RemotePathMetadata', 'Remote required path is missing or its metadata could not be read.', errno=result['errno'])))
        if result['state'] == 'exists' and kind is not None and result['kind'] != kind:
            effects['path_observation'] = 'succeeded'
            raise DiagnosticError(_file_operation_failure('resource_inaccessible', 'path_observation', 'check_path_kind',
                facts, effects, DiagnosticCause('PathKind', 'The observed path is not the required ' + kind + '.')))
        observations.append(result['state'] == 'exists')
    return observations


def observe_path(path, *, config, machine, remote, kind=None, context=None):
    """Bool only for an observed existence/absence; failed observations raise."""
    return _observe_checks([(path, kind, context or {})], config=config, machine=machine, remote=remote, required=False)[0]


def validate_paths(checks, *, config, machine, remote):
    """Validate required (path, kind, context) tuples, using one remote command."""
    _observe_checks(checks, config=config, machine=machine, remote=remote, required=True)
