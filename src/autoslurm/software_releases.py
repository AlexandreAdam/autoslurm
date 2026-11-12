"""Host-side release lifecycle; adapters own Git and Python process effects."""

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .git_projects import managed_path
from .record_files import atomic_json
from .software_sources import prepare_software_sources, SoftwarePreparationError
from .software_policy import release_identifier
from .software_manifest import normalize_software_manifest
from .python_environments import build_wheels, install_wheels, installation_hash, run_python, EnvironmentPreparationError


def _constraints(policy):
    if not policy.get('constraints'):
        return [], None
    data = Path(policy['constraints']).read_text()
    requirements = []
    for line in data.splitlines():
        line = line.split(' #', 1)[0].strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('-') or '://' in line or '@' in line:
            raise EnvironmentPreparationError('Machine constraints must contain package requirements, without includes, options or source URLs.')
        requirements.append(line)
    return requirements, hashlib.sha256(data.encode()).hexdigest()


def runtime_environment(policy, target=None, base_pythonpath=None):
    pythonpath = os.environ.get('PYTHONPATH', '') if base_pythonpath is None else base_pythonpath
    return {'PYTHONPATH': os.pathsep.join(part for part in (str(target) if target else '', pythonpath) if part),
            'PYTHONHOME': '', 'PYTHONNOUSERSITE': '1', 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONSAFEPATH': '1'}


def _inspect(policy, bootstrap, directory, *, artifacts=(), target=None, constraints=(), pythonpath=None):
    script = bootstrap + '\nimport json\nfrom autoslurm_worker.release_verification import inspect_runtime\n'
    script += 'print(json.dumps(inspect_runtime(' + repr(artifacts) + ', ' + repr(str(target) if target else None) + ', ' + repr(constraints) + ')))\n'
    result = json.loads(run_python(policy, ['-'], cwd=directory, input_text=script,
                                   environment=runtime_environment(policy, target, pythonpath)))
    if result['python'] != policy['python']:
        raise EnvironmentPreparationError('Selected interpreter reported a different Python identity.')
    return result


def verify_release(record, bootstrap):
    """Fresh observation of the exact installation/base; never edit a release."""
    if record.get('state') != 'ready':
        return {**record, 'verification': {'state': 'unavailable', 'errors': ['Release is not ready.']}}
    errors = []
    try:
        policy = record['request']['policy']
        target = Path(record['installation'])
        if installation_hash(target) != record['installation_hash']:
            errors.append('Installed application content has changed since preparation.')
        constraints, digest = _constraints(policy)
        if digest != record.get('constraints_hash'):
            errors.append('Machine dependency constraints have changed since preparation.')
        baseline = _inspect(policy, bootstrap, record['directory'], pythonpath=record['base_pythonpath'])
        if baseline != record['base_environment']:
            errors.append('The selected base Python environment has changed since preparation.')
        actual = _inspect(policy, bootstrap, record['directory'], artifacts=record['projects'], target=target,
                          constraints=constraints, pythonpath=record['base_pythonpath'])
        errors.extend(actual['errors'])
    except (Exception, KeyboardInterrupt):
        errors.append('The recorded installation or Python environment could not be verified.')
    return {**record, 'verification': {'state': 'verified' if not errors else 'invalid', 'errors': errors,
                                      'observed_at': datetime.now(timezone.utc).isoformat()}}


def operate_release(request, action, bootstrap):
    """Run/observe one durable identity. Existing identities never repeat effects."""
    if request.get('protocol') != 1 or action not in {'prepare', 'inspect', 'verify'}:
        raise ValueError('Unsupported software worker protocol/action.')
    if normalize_software_manifest(request['manifest']) != request['manifest']:
        raise ValueError('Software worker needs a normalized manifest.')
    release_id = release_identifier(request['release_id'])
    root = Path(request['software_root'])
    if not root.is_absolute():
        raise ValueError('software_root must be absolute.')
    path = managed_path(root, 'release_records', release_id + '.json')
    if path.exists():
        record = json.loads(path.read_text())
        if record.get('request') != request:
            raise ValueError('Preparation identity belongs to another request.')
        return verify_release(record, bootstrap) if action == 'verify' else record
    if action != 'prepare':
        return {'version': 1, 'release_id': release_id, 'state': 'missing', 'request': request}
    directory = managed_path(root, 'releases', release_id)
    record = {'version': 1, 'release_id': release_id, 'state': 'preparing_sources',
              'created_at': datetime.now(timezone.utc).isoformat(),
              'request': request, 'directory': str(directory), 'projects': []}
    # Publish identity before effects. A competing call sees in-progress evidence
    # and cannot execute a second preparation. Do not overwrite on collision.
    atomic_json(path, record, exclusive=True)

    def progress(state, project=None):
        record.update(state=state, current_project=project, updated_at=datetime.now(timezone.utc).isoformat())
        atomic_json(path, record)

    try:
        directory.mkdir(parents=True, exist_ok=False)
        policy = request['policy']
        constraints, digest = _constraints(policy)
        record['constraints_hash'] = digest
        record['base_pythonpath'] = os.environ.get('PYTHONPATH', '')
        record['base_environment'] = _inspect(policy, bootstrap, directory, pythonpath=record['base_pythonpath'])
        source = prepare_software_sources(request['manifest'], software_root=str(root))
        record['source_preparation_id'] = source['preparation_id']
        record['projects'] = source['projects']
        artifacts = build_wheels(source['projects'], directory, policy, progress)
        record['projects'] = artifacts
        progress('installing')
        target = install_wheels(artifacts, directory, policy)
        record['installation'] = str(target)
        progress('verifying')
        actual = _inspect(policy, bootstrap, directory, artifacts=artifacts, target=target,
                          constraints=constraints, pythonpath=record['base_pythonpath'])
        if actual['errors']:
            raise EnvironmentPreparationError('; '.join(actual['errors']))
        if _inspect(policy, bootstrap, directory, pythonpath=record['base_pythonpath']) != record['base_environment']:
            raise EnvironmentPreparationError('Base Python environment changed during preparation.')
        record['commands'] = actual['commands']
        record['installation_hash'] = installation_hash(target)
        record.pop('current_project', None)
        record['state'] = 'ready'
        record['updated_at'] = datetime.now(timezone.utc).isoformat()
        atomic_json(path, record)
    except (Exception, KeyboardInterrupt) as error:
        stage = 'publication' if record['state'] == 'ready' else record['state']
        if isinstance(error, SoftwarePreparationError):
            record['source_failure'] = error.evidence
        message = str(error) if isinstance(error, (SoftwarePreparationError, EnvironmentPreparationError)) else 'Software preparation failed; check runtime/build configuration and available storage.'
        record.update(state='failed', error={'stage': stage, 'message': message})
        record['updated_at'] = datetime.now(timezone.utc).isoformat()
        try:
            atomic_json(path, record)
        except (Exception, KeyboardInterrupt):
            record['tracking_error'] = 'Remote preparation evidence could not be saved.'
    return record
