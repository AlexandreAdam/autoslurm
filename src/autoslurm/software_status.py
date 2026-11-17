"""Read-only local/SSH software inspection with partial observation diagnostics."""

import json
from pathlib import Path
import subprocess

from .config import load_config, is_remote_machine, absolute_machine_path
from .software_probe import inspect_software_root
from .software_requirements import compare_environment, validate_expectations
from .software_status_evidence import validate_observation, add_compatibility_diagnostics
from .storage import storage_root
from .transport import ssh_command
from .software_update_probe import relative_project_path
from .errors import DiagnosticCause, DiagnosticError, InvalidRequestError, ConfigurationError, _software_status_failure


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Repeated observation key.')
        result[key] = value
    return result


def inspect_software(*, machine=None, project=None, limit=20, expectations=None):
    """Observe declared Git/package metadata; unavailable never means clean/ready."""
    if project is not None:
        try:
            project = relative_project_path(project)
        except ValueError as native:
            raise InvalidRequestError('project must be relative to software_root without traversal.',
                                      field='project', stage='select_software') from native
    if type(limit) is not int or not 1 <= limit <= 100:
        raise InvalidRequestError('limit must be between 1 and 100.', field='limit', stage='select_software')
    if machine is not None and (not isinstance(machine, str) or not machine.strip()):
        raise InvalidRequestError('machine must name one configured profile.', field='machine', stage='select_software')
    if expectations is not None:
        expectations = validate_expectations(expectations)
    config = load_config()
    name = machine if machine is not None else config.get('default_machine')
    facts = {'machine': name, 'project': project, 'resource': 'software_root'}
    if name not in config.get('machines', {}):
        raise ConfigurationError(_software_status_failure('configuration_invalid', 'select_machine', facts))
    profile = config['machines'][name]
    if 'ssh_alias' in profile:
        facts['ssh_alias'] = profile['ssh_alias']
    remote = is_remote_machine(profile)
    root = profile.get('software_root')
    if root is None:
        if remote:
            raise ConfigurationError(_software_status_failure('configuration_invalid', 'select_software_root',
                {**facts, 'field': 'software_root'}))
        root = str(storage_root() / 'software')
    root = absolute_machine_path(root, 'software_root')
    facts['path'] = root
    environment_script, python_path, names = None, None, None
    if expectations is not None:
        names = sorted(set(expectations['dependencies']) | ({expectations['package']} if expectations['package'] else set()))
        environment_script = Path(__file__).with_name('environment_probe.py').read_text() + '\nprint(json.dumps(inspect_environment(' + repr(names) + ')))\n'
        if profile.get('venv_path'):
            python_path = absolute_machine_path(profile['venv_path'], 'venv_path') + '/bin/python'
    if remote:
        probe = Path(__file__).with_name('software_probe.py').read_text()
        script = probe + '\nprint(json.dumps(inspect_software_root(' + ', '.join(map(repr, (root, project, limit, python_path, environment_script))) + ')))\n'
        command = ssh_command(profile, name, 'python3 -B -', options=[
            '-T', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
            '-o', 'ServerAliveInterval=10', '-o', 'ServerAliveCountMax=2'])
        try:
            response = subprocess.run(command, input=script, capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired, UnicodeError) as native:
            problem = ('command_timeout' if isinstance(native, subprocess.TimeoutExpired) else
                       'protocol_invalid' if isinstance(native, UnicodeError) else
                       'command_unavailable' if isinstance(native, (FileNotFoundError, PermissionError)) else 'transport_failed')
            raise DiagnosticError(_software_status_failure(problem, 'probe_software', {**facts, 'executable': 'python3'},
                DiagnosticCause.from_exception(native, detail='SSH software inspection did not complete; raw output is omitted.'))) from native
        code = response.returncode
        if type(code) is not int or not -(2**63) <= code < 2**63:
            raise DiagnosticError(_software_status_failure('protocol_invalid', 'probe_software', facts))
        if code:
            problem = 'transport_failed' if code == 255 else 'operation_interrupted' if code < 0 else 'command_failed'
            raise DiagnosticError(_software_status_failure(problem, 'probe_software', facts,
                DiagnosticCause('SoftwareProbeCommand', 'Remote software inspection failed; raw output is omitted.', returncode=code)))
        try:
            if not isinstance(response.stdout, str) or len(response.stdout.encode('utf-8')) > 1024 * 1024:
                raise ValueError('Invalid software observation size.')
            result = json.loads(response.stdout, object_pairs_hook=_unique_object)
        except (ValueError, UnicodeError, RecursionError) as native:
            raise DiagnosticError(_software_status_failure('protocol_invalid', 'read_software', facts,
                DiagnosticCause.from_exception(native, detail='Software inspection returned invalid evidence.'))) from native
    else:
        result = inspect_software_root(root, project, limit, python_path, environment_script)
    try:
        result = validate_observation(result, root, project, limit, facts, names, python_path)
    except (ValueError, UnicodeError, RecursionError) as native:
        raise DiagnosticError(_software_status_failure('protocol_invalid', 'read_software', facts,
            DiagnosticCause.from_exception(native, detail='Software inspection returned invalid evidence.'))) from native
    if expectations is not None:
        result['expectations'] = expectations
        result['compatibility'] = add_compatibility_diagnostics(
            compare_environment(expectations, result.get('environment', {'state': 'unavailable'})), facts)
    return {**result, 'machine': name, 'ssh_alias': profile.get('ssh_alias')}
