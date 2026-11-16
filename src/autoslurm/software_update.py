"""Update one existing project locally or through the shared SSH adapter."""

import json
from pathlib import Path, PurePosixPath
import re
import subprocess
from datetime import datetime, timezone

from .config import load_config, is_remote_machine, absolute_machine_path
from .software_update_probe import relative_project_path, _run_update_checkout
from .storage import storage_root
from .transport import ssh_command
from .errors import (DiagnosticError, DiagnosticCause, ConfigurationError, InvalidRequestError,
                     configuration_failure, _software_update_failure)


__all__ = ['update_software', 'SoftwareUpdateError']


class SoftwareUpdateError(DiagnosticError):
    """Failed/uncertain pull, carrying the available before/after evidence."""

    def __init__(self, message, evidence, *, diagnostic=None):
        self.evidence = evidence
        super().__init__(message, diagnostic=diagnostic)


def _validate_result(result, root, project, python):
    if (not isinstance(result, dict) or result.get('version') != 1 or result.get('software_root') != root
            or result.get('project') != project or not isinstance(result.get('state'), str)
            or result['state'] not in {'updated', 'up_to_date', 'failed', 'unknown'}
            or not isinstance(result.get('observed_at'), str)
            or result.get('path') != str(PurePosixPath(root) / project)
            or not isinstance(result.get('installation'), dict)
            or ('output_tail' in result['installation'] and not isinstance(result['installation']['output_tail'], str))
            or (result['state'] in {'failed', 'unknown'} and not isinstance(result.get('error'), str))):
        raise ValueError('Invalid software update response.')
    for key in ('before_commit', 'after_commit'):
        value = result.get(key)
        if value is not None and (not isinstance(value, str) or not re.fullmatch('[0-9a-f]{40}|[0-9a-f]{64}', value)):
            raise ValueError('Invalid software update commit evidence.')
    installation = result['installation']
    if (not isinstance(installation.get('state'), str) or installation['state'] not in {'not_started', 'unknown', 'failed', 'installed'}
            or installation.get('editable') is not True or installation.get('path') != str(PurePosixPath(root) / project)
            or (installation.get('python') is not None and installation['python'] != python)
            or (installation.get('returncode') is not None and type(installation['returncode']) is not int)):
        raise ValueError('Invalid software update installation evidence.')
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
    if any(key in result for key in ('effects', 'failure', 'check')):
        effects = result.get('effects')
        if (not isinstance(effects, dict) or set(effects) != {'git_pull', 'editable_install'}
                or any(not isinstance(value, str) or value not in {'not_started', 'succeeded', 'failed', 'partial', 'unknown'}
                       for value in effects.values())):
            raise ValueError('Invalid software update effects.')
        stages = {'preflight', 'pull', 'install', 'complete'}
        checks = {'checkout_root', 'git_checkout', 'git_commit_before', 'git_branch', 'git_upstream',
                  'git_status', 'environment_python', 'git_pull', 'git_commit_after', 'editable_install'}
        if (not isinstance(result.get('stage'), str) or result['stage'] not in stages
                or not isinstance(result.get('check'), str) or result['check'] not in checks):
            raise ValueError('Invalid software update check.')
        phase_checks = {'preflight': checks - {'git_pull', 'git_commit_after', 'editable_install'},
                        'pull': {'git_pull', 'git_commit_after'}, 'install': {'editable_install'},
                        'complete': {'editable_install'}}
        if result['check'] not in phase_checks[result['stage']]:
            raise ValueError('Software update check disagrees with its phase.')
        if (result.get('path') != str(PurePosixPath(root) / project)
                or not isinstance(result.get('installation'), dict)
                or result['installation'].get('python') != python):
            raise ValueError('Software update changed selected paths.')
        if result['state'] in {'updated', 'up_to_date'}:
            if effects != {'git_pull': 'succeeded', 'editable_install': 'succeeded'} or 'failure' in result:
                raise ValueError('Successful update has contradictory effects.')
        else:
            failure = result.get('failure')
            if (not isinstance(failure, dict) or not isinstance(failure.get('problem'), str)
                    or failure['problem'] not in {'invalid_argument', 'resource_missing', 'resource_inaccessible',
                        'command_unavailable', 'command_failed', 'command_timeout', 'operation_interrupted',
                        'protocol_invalid', 'compatibility_mismatch'}
                    or not isinstance(failure.get('cause_kind'), str)
                    or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]{0,63}', failure['cause_kind'])):
                raise ValueError('Invalid software update failure facts.')
            for key in ('errno', 'returncode'):
                value = failure.get(key)
                if value is not None and (type(value) is not int or not -(2**63) <= value < 2**63):
                    raise ValueError('Invalid software update process facts.')
            if (result['stage'] == 'preflight' and any(value != 'not_started' for value in effects.values())
                    or result['stage'] == 'pull' and effects['editable_install'] != 'not_started'
                    or result['stage'] == 'install' and effects['git_pull'] != 'succeeded'
                    or result['stage'] == 'complete'):
                raise ValueError('Software update phase disagrees with its effects.')
            if result['stage'] in {'preflight', 'pull'} and installation['state'] != 'not_started':
                raise ValueError('Installation preceded the required preflight/pull.')
            if result['state'] == 'failed' and 'unknown' in effects.values():
                raise ValueError('Failed update hides unknown effects.')
            if result['stage'] == 'install':
                states = {'not_started': 'not_started', 'partial': 'failed', 'unknown': 'unknown'}
                if states.get(effects['editable_install']) != installation['state']:
                    raise ValueError('Installation state disagrees with its effects.')
            if failure['problem'] in {'command_timeout', 'operation_interrupted'}:
                step = {'git_pull': 'git_pull', 'editable_install': 'editable_install'}.get(result['check'])
                if step and effects[step] != 'unknown':
                    raise ValueError('Interrupted mutating command has contradictory effects.')


def _unobserved_result(root, project, python, *, check, problem, cause, effects, state='unknown'):
    return {'version': 1, 'state': state, 'software_root': root, 'project': project,
        'path': str(PurePosixPath(root) / project), 'stage': 'transport', 'check': check,
        'before_commit': None, 'after_commit': None, 'effects': effects,
        'observed_at': datetime.now(timezone.utc).isoformat(),
        'installation': {'state': 'not_started' if effects['editable_install'] == 'not_started' else 'unknown',
            'python': python, 'editable': True, 'path': str(PurePosixPath(root) / project), 'returncode': None},
        'failure': {'problem': problem, 'cause_kind': type(cause).__name__,
                    'errno': getattr(cause, 'errno', None), 'returncode': getattr(cause, 'returncode', None)}}


def _update_diagnostic(result, profile, machine):
    """Normalize the same validated plain probe facts for local and SSH updates."""
    check = result.get('check', 'legacy_update')
    failure = result.get('failure', {})
    context = {'machine': machine, 'project': result['project'], 'path': result['path'],
               'source': 'update_software', 'resource': 'software_checkout'}
    if isinstance(profile.get('ssh_alias'), str):
        context['ssh_alias'] = profile['ssh_alias']
    if check in {'environment_python', 'editable_install'}:
        context.update(executable=result['installation']['python'], field='venv_path', resource='virtual_environment')
        if check == 'environment_python':
            context['path'] = result['installation']['python']
    elif check.startswith('git_'):
        context['executable'] = 'git'
    elif check.startswith('ssh_update'):
        context['executable'] = 'ssh'
    elif check == 'probe_source':
        context.update(path=str(Path(__file__).with_name('software_update_probe.py')), resource='probe_source')
    problem = failure.get('problem', 'outcome_unknown')
    detail = result.get('installation', {}).get('output_tail') if check == 'editable_install' else None
    cause = DiagnosticCause(failure.get('cause_kind', 'LegacyUpdateFailure'),
        detail or 'The selected update check failed; raw Git/SSH output and record contents are omitted.',
        failure.get('errno'), failure.get('returncode'))
    summary = result.get('error') or ('Update/install outcome is unknown; inspect the checkout and configured environment before trying again.'
        if result['state'] == 'unknown' else None)
    if summary and check == 'editable_install':
        summary = summary.split('\nPip output (tail):', 1)[0]
    return _software_update_failure(problem=problem, check=check, context=context,
        effects=result.get('effects', {'git_pull': 'unknown', 'editable_install': 'unknown'}),
        cause=cause, summary=summary)


def _update_target(machine):
    """Select one existing profile and normalize its roots without any process."""
    config = load_config()
    name = config['default_machine'] if machine is None else machine
    if not isinstance(name, str) or name not in config['machines']:
        raise ConfigurationError(configuration_failure(stage='select_profile',
            summary='No configuration found for the selected machine.', context={'field': 'machine'},
            effects={'git_pull': 'not_started', 'editable_install': 'not_started'}))
    profile = config['machines'][name]
    remote = is_remote_machine(profile)
    root = profile.get('software_root')
    if root is None:
        if remote:
            raise ConfigurationError(configuration_failure(stage='update_software',
                summary='Configure software_root before updating remote projects.', context={'machine': name, 'field': 'software_root'},
                effects={'git_pull': 'not_started', 'editable_install': 'not_started'}))
        root = str(storage_root() / 'software')
    for field, value in (('software_root', root), ('venv_path', profile.get('venv_path'))):
        try:
            normalized = absolute_machine_path(value, field)
        except ValueError as error:
            raise ConfigurationError(configuration_failure(stage='update_software', summary=str(error),
                context={'machine': name, 'field': field},
                effects={'git_pull': 'not_started', 'editable_install': 'not_started'})) from error
        if field == 'software_root': root = normalized
        else: venv = normalized
    return name, profile, root, venv


def _remote_update(root, project, venv, profile, name):
    """Dispatch once and retain either validated probe facts or uncertainty."""
    native_cause = None
    python = venv.rstrip('/') + '/bin/python'
    try:
        probe = Path(__file__).with_name('software_update_probe.py').read_text(encoding='utf-8')
    except (OSError, UnicodeError) as error:
        result = _unobserved_result(root, project, python, check='probe_source', problem='resource_inaccessible',
            cause=error, effects={'git_pull': 'not_started', 'editable_install': 'not_started'}, state='failed')
        return result, error
    script = probe + '\nprint(json.dumps(update_checkout(' + ', '.join(map(repr, (root, project, venv))) + ')))\n'
    command = ssh_command(profile, name, 'python3 -B -', options=[
        '-T', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
        '-o', 'ServerAliveInterval=10', '-o', 'ServerAliveCountMax=2'])
    try:
        response = subprocess.run(command, input=script, capture_output=True, text=True, timeout=300)
        if response.returncode:
            raise subprocess.CalledProcessError(response.returncode, command, output=response.stdout, stderr=response.stderr)
        if not isinstance(response.stdout, str) or len(response.stdout.encode('utf-8')) > 65536:
            raise ValueError('Remote update response unavailable.')
        result = json.loads(response.stdout)
        _validate_result(result, root, project, python)
    except (OSError, ValueError, subprocess.TimeoutExpired, subprocess.CalledProcessError, KeyboardInterrupt) as error:
        native_cause = error
        effects = {'git_pull': 'unknown', 'editable_install': 'unknown'}
        check, problem = 'ssh_update_response', 'protocol_invalid'
        state = 'unknown'
        if isinstance(error, (FileNotFoundError, PermissionError)):
            check, problem, state = 'ssh_update_launch', 'command_unavailable', 'failed'
            effects = {'git_pull': 'not_started', 'editable_install': 'not_started'}
        elif isinstance(error, (subprocess.CalledProcessError, OSError)): problem = 'transport_failed'
        elif isinstance(error, subprocess.TimeoutExpired): problem = 'command_timeout'
        elif isinstance(error, KeyboardInterrupt): problem = 'operation_interrupted'
        result = _unobserved_result(root, project, python, check=check, problem=problem, cause=error, effects=effects, state=state)
    return result, native_cause


def update_software(*, project, machine=None):
    """Pull one existing checkout and refresh its editable installation.

    project is relative to the selected machine's software_root. The current
    branch must be clean and track an upstream. Use the selected venv's Python;
    machine dependencies stay unchanged. No clones/environments/tracking files
    are created. A lost SSH response is unknown, with no retry.
    """
    try:
        project = relative_project_path(project)
    except ValueError as error:
        raise InvalidRequestError(str(error), field='project', stage='update_software',
            effects={'git_pull': 'not_started', 'editable_install': 'not_started'}) from error
    name, profile, root, venv = _update_target(machine)
    if is_remote_machine(profile):
        result, native_cause = _remote_update(root, project, venv, profile, name)
    else:
        result, native_cause = _run_update_checkout(root, project, venv)
        _validate_result(result, root, project, venv.rstrip('/') + '/bin/python')
    result = {**result, 'machine': name}
    if result['state'] not in {'updated', 'up_to_date'}:
        diagnostic = _update_diagnostic(result, profile, name)
        installation = result.get('installation')
        if isinstance(installation, dict) and isinstance(installation.get('output_tail'), str):
            installation['output_tail'] = DiagnosticCause('PipOutput', installation['output_tail']).detail
        message = diagnostic.summary
        if isinstance(installation, dict) and installation.get('output_tail'):
            message += '\nPip output (tail):\n' + installation['output_tail']
        result.update(error=message, diagnostic=diagnostic.to_dict())
        raise SoftwareUpdateError(message, result, diagnostic=diagnostic) from native_cause
    return result
