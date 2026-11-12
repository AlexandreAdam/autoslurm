"""Explicit release selection and pure job/runtime binding rules."""

from dataclasses import replace
from pathlib import PurePosixPath
import shlex

from .config import recorded_transport
from .software_manifest import normalize_software_manifest


_RESERVED = {'PATH', 'PYTHONPATH', 'PYTHONHOME', 'VIRTUAL_ENV', 'PYTHONNOUSERSITE',
             'PYTHONDONTWRITEBYTECODE', 'PYTHONSAFEPATH'}


def select_software_release(context, release_id):
    from .software_preparation import inspect_software_release
    record = inspect_software_release(release_id, machine=context.machine_name, verify=True)
    if (record.get('state') != 'ready' or record.get('observation', {}).get('state') != 'observed'
            or record.get('verification', {}).get('state') != 'verified'):
        reasons = record.get('verification', {}).get('errors', [])
        raise ValueError('Selected software release is not freshly verified: ' + '; '.join(reasons or ['inspect its exact status.']))
    request = record['request']
    if (request['machine'] != context.machine_name or request['transport'] != recorded_transport(context.config)
            or request['software_root'] != context.software_root):
        raise ValueError('Software release does not match the selected machine, transport and software_root.')
    return replace(context, software_release=record)


def validate_release_manifest(manifest, record):
    if manifest is None:
        return
    manifest = normalize_software_manifest(manifest)
    requested = record['request']['manifest']
    if manifest['runtime'] != requested['runtime'] or len(manifest['projects']) != len(requested['projects']):
        raise ValueError('Bundle software request does not match the selected release.')
    commits = {item['name']: item['commit'] for item in record['projects']}
    for expected, prepared in zip(manifest['projects'], requested['projects']):
        if any(expected[key] != prepared[key] for key in ('name', 'repository', 'subdirectory')):
            raise ValueError('Bundle software project does not match the selected release.')
        revision = expected['revision']
        if revision is not None and revision not in {prepared['revision'], commits.get(expected['name'])}:
            raise ValueError('Bundle software revision does not match the selected release.')


def validate_managed_job(job, record):
    if _RESERVED & (set(job.get('environment') or {}) | set(job.get('runtime_environment') or {})):
        raise ValueError('Managed job environment cannot override the selected Python/application runtime.')
    parts = shlex.split(job['script'])
    modules = {module for item in record['projects'] for module in item['modules']}
    if len(parts) == 1 and parts[0] in record['commands']:
        return str(PurePosixPath(record['installation']) / 'bin' / parts[0])
    if len(parts) == 3 and parts[0] in {'python', 'python3'} and parts[1] == '-m':
        if parts[2].split('.')[0] in modules and all(piece.isidentifier() for piece in parts[2].split('.')):
            return shlex.quote(record['request']['policy']['python']) + ' -P -m ' + shlex.quote(parts[2])
    raise ValueError('Managed jobs must use an installed application entry point or python -m application.module.')


def runtime_shell(record):
    python = record['request']['policy']['python']
    target = record['installation']
    pythonpath = ':'.join(part for part in (target, record['base_pythonpath']) if part)
    return ('unset PYTHONHOME\n'
            'export PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 PYTHONSAFEPATH=1\n'
            f'export VIRTUAL_ENV={shlex.quote(record["base_environment"]["prefix"])}\n'
            f'export PYTHONPATH={shlex.quote(pythonpath)}\n'
            f'export PATH={shlex.quote(target + "/bin:" + str(PurePosixPath(python).parent))}:"$PATH"\n')


def release_evidence(record):
    return {key: record[key] for key in ('release_id', 'installation', 'installation_hash', 'projects', 'request',
                                        'base_environment', 'base_pythonpath', 'commands', 'verification') if key in record}


def validate_managed_paths(execution, record):
    root = PurePosixPath(record['request']['software_root'])
    protected = [root / name for name in ('sources', 'releases', 'repositories', 'release_records', 'source_preparations')]
    paths = [execution['working_directory'], execution['log_pattern'], *execution['resolved_paths'].values()]
    if any(PurePosixPath(path).is_relative_to(prefix) for path in paths if path for prefix in protected):
        raise ValueError('Job data, working directory and logs must stay outside managed software storage.')
