"""Update one existing project locally or through the shared SSH adapter."""

import json
from pathlib import Path, PurePosixPath
import re
import subprocess

from .config import load_config, is_remote_machine, absolute_machine_path
from .software_update_probe import relative_project_path, update_checkout
from .storage import storage_root
from .transport import ssh_command


__all__ = ['update_software', 'SoftwareUpdateError']


class SoftwareUpdateError(RuntimeError):
    """Failed/uncertain pull, carrying the available before/after evidence."""

    def __init__(self, message, evidence):
        self.evidence = evidence
        super().__init__(message)


def _validate_result(result, root, project, python):
    if (not isinstance(result, dict) or result.get('version') != 1 or result.get('software_root') != root
            or result.get('project') != project or result.get('state') not in {'updated', 'up_to_date', 'failed', 'unknown'}
            or not isinstance(result.get('observed_at'), str)):
        raise ValueError('Invalid software update response.')
    for key in ('before_commit', 'after_commit'):
        value = result.get(key)
        if value is not None and (not isinstance(value, str) or not re.fullmatch('[0-9a-f]{40}|[0-9a-f]{64}', value)):
            raise ValueError('Invalid software update commit evidence.')
    if result['state'] in {'updated', 'up_to_date'}:
        if (not result.get('before_commit') or not result.get('after_commit') or not isinstance(result.get('branch'), str)
                or not isinstance(result.get('upstream'), str)
                or (result['state'] == 'updated') != (result['before_commit'] != result['after_commit'])):
            raise ValueError('Incomplete successful software update evidence.')
        installation = result.get('installation')
        if (result.get('stage') != 'complete' or not isinstance(installation, dict)
                or installation.get('state') != 'installed' or installation.get('editable') is not True
                or installation.get('python') != python or installation.get('path') != str(PurePosixPath(root) / project)
                or type(installation.get('returncode')) is not int or installation['returncode'] != 0):
            raise ValueError('Incomplete editable installation evidence.')


def update_software(*, project, machine=None):
    """Pull one existing checkout and refresh its editable installation.

    project is relative to the selected machine's software_root. The current
    branch must be clean and track an upstream. Use the selected venv's Python;
    machine dependencies stay unchanged. No clones/environments/tracking files
    are created. A lost SSH response is unknown, with no retry.
    """
    project = relative_project_path(project)
    config = load_config()
    name = machine or config['default_machine']
    if name not in config['machines']:
        raise ValueError(f'No configuration found for machine: {name}')
    profile = config['machines'][name]
    remote = is_remote_machine(profile)
    root = profile.get('software_root')
    if root is None:
        if remote:
            raise ValueError('Configure software_root before updating remote projects.')
        root = str(storage_root() / 'software')
    root = absolute_machine_path(root, 'software_root')
    venv = absolute_machine_path(profile.get('venv_path'), 'venv_path')
    if remote:
        probe = Path(__file__).with_name('software_update_probe.py').read_text()
        script = probe + '\nprint(json.dumps(update_checkout(' + ', '.join(map(repr, (root, project, venv))) + ')))\n'
        command = ssh_command(profile, name, 'python3 -B -', options=[
            '-T', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
            '-o', 'ServerAliveInterval=10', '-o', 'ServerAliveCountMax=2'])
        try:
            response = subprocess.run(command, input=script, capture_output=True, text=True, timeout=300)
            if response.returncode or len(response.stdout) > 65536:
                raise ValueError('Remote update response unavailable.')
            result = json.loads(response.stdout)
            _validate_result(result, root, project, venv.rstrip('/') + '/bin/python')
        except (OSError, ValueError, subprocess.TimeoutExpired, KeyboardInterrupt):
            result = {'version': 1, 'state': 'unknown', 'software_root': root, 'project': project,
                      'stage': 'transport', 'before_commit': None, 'after_commit': None,
                      'installation': {'state': 'unknown', 'python': venv.rstrip('/') + '/bin/python',
                                       'editable': True, 'path': str(PurePosixPath(root) / project), 'returncode': None},
                      'error': 'Update/install outcome is unknown; inspect the checkout and configured environment before trying again.'}
    else:
        result = update_checkout(root, project, venv)
    result = {**result, 'machine': name}
    if result['state'] not in {'updated', 'up_to_date'}:
        raise SoftwareUpdateError(result.get('error', 'Software update did not complete.'), result)
    return result
