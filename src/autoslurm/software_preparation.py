"""Workstation-facing software preparation and exact-identity recovery."""

import json
from pathlib import Path, PurePosixPath
import subprocess
import re
from uuid import uuid4
from datetime import datetime, timezone

from .config import load_config, normalize_machine_profile, is_remote_machine, recorded_transport, absolute_machine_path
from .record_files import atomic_json
from .save_load_jobs import load_bundle_from_path
from .software_manifest import normalize_software_manifest, bundle_software_manifest
from .software_policy import runtime_policy, release_identifier
from .software_sources import SoftwarePreparationError
from .software_worker import launcher_script
from .storage import storage_root
from .transport import ssh_command


__all__ = ['prepare_software', 'inspect_software_release']


def _local_project_manifest(directory, revision):
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib
    directory = Path(directory).resolve()
    project = tomllib.loads((directory / 'pyproject.toml').read_text())['project']
    def git(*arguments):
        result = subprocess.run(['git', '-C', str(directory), *arguments], capture_output=True, text=True, timeout=15)
        if result.returncode:
            raise ValueError('Local project needs a Git origin; preparation uses committed upstream code.')
        return result.stdout.strip()
    # Read the literal origin, before operator-owned insteadOf rewrites (which
    # may contain private paths or credential-bearing transport details).
    repository = git('config', '--get', 'remote.origin.url')
    root = Path(git('rev-parse', '--show-toplevel')).resolve()
    return normalize_software_manifest({'projects': [{'name': project['name'], 'repository': repository,
        'revision': revision, 'subdirectory': str(directory.relative_to(root))}]})


def _reference_path(release_id):
    return storage_root() / 'software_preparations' / (release_identifier(release_id) + '.json')


def _dispatch(request, action):
    transport = request['transport']
    script = launcher_script(request, action)
    if transport:
        command = ssh_command(transport, request['machine'], 'python3 -B -', options=[
            '-T', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
            '-o', 'ServerAliveInterval=10', '-o', 'ServerAliveCountMax=2'])
    else:
        # Same worker/interpreter path as SSH, with no assumption about the
        # locally installed AutoSlurm or build/dependency tools on the target.
        command = [request['policy']['python'], '-B', '-']
    response = subprocess.run(command, input=script, capture_output=True, text=True, timeout=1800)
    if response.returncode or len(response.stdout) > 4 * 1024 * 1024:
        raise RuntimeError('Software worker failed or its connection was lost; inspect the exact release before preparing again.')
    result = json.loads(response.stdout)
    if (not isinstance(result, dict) or result.get('version') != 1 or result.get('release_id') != request['release_id']
            or result.get('request') != request or result.get('state') not in {
                'missing', 'preparing_sources', 'building', 'installing', 'verifying', 'ready', 'failed'}):
        raise ValueError('Invalid software worker evidence.')
    if result['state'] == 'ready':
        expected = str(PurePosixPath(request['software_root']) / 'releases' / request['release_id'] / 'site-packages')
        projects = result.get('projects')
        if (result.get('installation') != expected or not isinstance(result.get('installation_hash'), str)
                or not re.fullmatch('[0-9a-f]{64}', result['installation_hash'])
                or not isinstance(projects, list) or len(projects) != len(request['manifest']['projects'])
                or not isinstance(result.get('commands'), list) or not isinstance(result.get('base_pythonpath'), str)
                or not isinstance(result.get('base_environment'), dict)):
            raise ValueError('Incomplete ready software evidence.')
        for project, requested in zip(projects, request['manifest']['projects']):
            if (not isinstance(project, dict) or project.get('name') != requested['name']
                    or not re.fullmatch('(?:[0-9a-f]{40}|[0-9a-f]{64})', project.get('commit', ''))
                    or not isinstance(project.get('distribution'), str) or not isinstance(project.get('version'), str)
                    or not isinstance(project.get('modules'), list)):
                raise ValueError('Incomplete installed project evidence.')
        if any(not isinstance(name, str) or not re.fullmatch('[A-Za-z0-9_][A-Za-z0-9_.-]*', name) for name in result['commands']):
            raise ValueError('Invalid installed application commands.')
    return result


def prepare_software(manifest=None, *, machine=None, bundle_path=None, local_project=None, revision=None, on_created=None):
    """Create a new, verified application release; never change the base environment.

    Omitted revisions resolve upstream afresh. Local edits are not transferred.
    SoftwarePreparationError.evidence retains the exact ID even after a lost
    connection. Inspect that ID rather than blindly retrying this operation.
    """
    if sum(value is not None for value in (manifest, bundle_path, local_project)) != 1:
        raise ValueError('Choose a software manifest, --bundle-file, or --local-project.')
    if revision is not None and local_project is None:
        raise ValueError('--revision is only used with --local-project; bundle requests carry their own revisions.')
    if local_project is not None:
        manifest = _local_project_manifest(local_project, revision)
    if bundle_path is not None:
        jobs, _, _ = load_bundle_from_path(bundle_path)
        manifest = bundle_software_manifest(jobs)
        if manifest is None:
            raise ValueError('Bundle has no software request. Add one or use --local-project.')
    manifest = normalize_software_manifest(manifest)
    config = load_config()
    name = machine or config['default_machine']
    if name not in config['machines']:
        raise ValueError(f'No configuration found for machine: {name}')
    profile = normalize_machine_profile(config['machines'][name])
    root = profile.get('software_root')
    if root is None:
        if is_remote_machine(profile):
            raise ValueError('Configure software_root before remote preparation.')
        root = str(storage_root() / 'software')
    request = {'protocol': 1, 'release_id': uuid4().hex, 'machine': name,
               'software_root': absolute_machine_path(root, 'software_root'),
               'transport': recorded_transport(profile), 'manifest': manifest,
               'policy': runtime_policy(profile, manifest['runtime'])}
    reference = {'version': 1, 'release_id': request['release_id'], 'state': 'requested', 'request': request,
                 'created_at': datetime.now(timezone.utc).isoformat()}
    path = _reference_path(request['release_id'])
    # Persist the identity before dispatch, so loss of the SSH response cannot
    # erase the only handle on work that may already have taken effect.
    atomic_json(path, reference, exclusive=True)
    if on_created is not None:
        on_created(request['release_id'])
    try:
        result = _dispatch(request, 'prepare')
    except (Exception, KeyboardInterrupt):
        reference.update(state='unknown', error={'message': 'Preparation outcome is unknown; inspect this release ID before retrying.'})
        try:
            atomic_json(path, reference)
        except (Exception, KeyboardInterrupt):
            reference['tracking_error'] = 'Local preparation evidence could not be saved.'
        raise SoftwarePreparationError(reference['error']['message'], reference) from None
    try:
        atomic_json(path, result)
    except (Exception, KeyboardInterrupt):
        result['tracking_error'] = 'Local result could not be saved; original request identity remains available.'
        raise SoftwarePreparationError(result['tracking_error'], result) from None
    if result['state'] != 'ready':
        raise SoftwarePreparationError(result.get('error', {}).get('message', 'Software is not ready; inspect the exact release.'), result)
    return result


def inspect_software_release(release_id, *, machine=None, verify=False):
    """Read the original root/alias; current profile edits cannot redirect recovery.

    Missing remote evidence does not prove a timed-out request cannot still run.
    This never dispatches preparation or retries an interrupted writer.
    """
    reference = json.loads(_reference_path(release_id).read_text())
    if (not isinstance(reference, dict) or reference.get('version') != 1
            or reference.get('release_id') != release_id or not isinstance(reference.get('request'), dict)
            or reference['request'].get('release_id') != release_id
            or reference['request'].get('protocol') != 1):
        raise ValueError('Invalid saved preparation reference; no profile fallback is permitted.')
    request = reference['request']
    if machine is not None and machine != request['machine']:
        raise ValueError('Release belongs to another machine.')
    try:
        result = _dispatch(request, 'verify' if verify else 'inspect')
    except (Exception, KeyboardInterrupt):
        return {**reference, 'observation': {'state': 'unavailable', 'message': 'Exact release could not be inspected; saved state may be stale.'}}
    return {**result, 'observation': {'state': 'observed', 'observed_at': datetime.now(timezone.utc).isoformat()}}
