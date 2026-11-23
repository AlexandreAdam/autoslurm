"""Bounded connection observations from this controller, without activation."""
from datetime import datetime, timezone
import subprocess

from .config import load_config, is_remote_machine
from .errors import DiagnosticCause, InvalidRequestError, ConfigurationError, _connection_failure
from .transport import ssh_command

__all__ = ['check_connections']


def check_connections(machine=None, *, all_machines=False):
    """Probe selected configured profiles once; failures are per-machine evidence.

    No scheduler, environment setup or login flow is run. SSH config may create
    its ordinary connection state. Unavailable does not mean login is required.
    """
    if type(all_machines) is not bool or (machine is not None and (not isinstance(machine, str) or not machine.strip())) or (machine is not None and all_machines):
        raise InvalidRequestError('Select a machine or all_machines=True.', field='machine', stage='connection_check')
    config = load_config()
    names = list(config['machines']) if all_machines else [machine or config.get('default_machine')]
    if len(names) > 32:
        raise InvalidRequestError('Check at most 32 configured machines at once.', field='machines', stage='connection_check')
    # Validate selection before starting any command.
    if any(name not in config['machines'] for name in names):
        raise ConfigurationError(_connection_failure('configuration_invalid', machine, None, stage='select_machine'))
    profiles = [(name, config['machines'][name]) for name in names]
    observations = []
    for name, profile in profiles:
        observed = {'machine': name, 'ssh_alias': profile.get('ssh_alias'),
                    'observed_at': datetime.now(timezone.utc).isoformat(),
                    'state': 'local', 'diagnostic': None}
        if not is_remote_machine(profile):
            observations.append(observed)
            continue
        command = ssh_command(profile, name, 'true', options=['-T'])
        cause = None
        code = None
        try:
            result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL, timeout=12)
            if type(result.returncode) is not int:
                code = 'protocol_invalid'
                cause = DiagnosticCause('ConnectionResponse', 'No valid SSH exit code was returned.')
            elif result.returncode:
                code = 'transport_failed' if result.returncode == 255 else 'command_failed'
                cause = DiagnosticCause('SSHCommand', 'The noninteractive no-op probe failed.', returncode=result.returncode)
        except (OSError, subprocess.TimeoutExpired) as error:
            code = 'command_timeout' if isinstance(error, subprocess.TimeoutExpired) else 'command_unavailable'
            cause = DiagnosticCause.from_exception(error, detail='The SSH connection probe could not complete.')
        observed['state'] = 'unavailable' if code else 'ready'
        if code:
            observed['diagnostic'] = _connection_failure(code, name, profile.get('ssh_alias'), cause=cause).to_dict()
        observations.append(observed)
    return {'state': 'partial' if any(row['state'] == 'unavailable' for row in observations) else 'observed',
            'machines': observations}
