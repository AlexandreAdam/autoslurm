import json
import subprocess

import pytest

from autoslurm import check_connections, save_config, execute_acp
from autoslurm.apps import root
from autoslurm.errors import ConfigurationError, InvalidRequestError
from autoslurm.transport import ssh_command


def profiles():
    save_config({'machines': {'rusty': {'ssh_alias': 'rusty'}, 'popeye': {'ssh_alias': 'popeye'}, 'local': {}},
                 'default_machine': 'rusty'})


@pytest.mark.parametrize('fault,code', [(255, 'transport_failed'), (2, 'command_failed'),
    (FileNotFoundError(2, 'sensitive detail'), 'command_unavailable'),
    (subprocess.TimeoutExpired('ssh',12), 'command_timeout'), (True, 'protocol_invalid')])
def test_connection_failure_is_per_machine_and_bounded(monkeypatch, fault, code):
    profiles(); calls=[]
    def run(command, **kwargs):
        calls.append(command)
        assert kwargs['timeout'] == 12 and kwargs['stdin'] == subprocess.DEVNULL
        assert 'BatchMode=yes' in command and 'ConnectTimeout=10' in command
        assert command[-1] == 'true'
        if command[-2] == 'rusty':
            if isinstance(fault, Exception): raise fault
            return subprocess.CompletedProcess(command,fault)
        return subprocess.CompletedProcess(command,0)
    monkeypatch.setattr(subprocess,'run',run)
    result=check_connections(all_machines=True)
    assert [v['state'] for v in result['machines']] == ['unavailable','ready','local']
    diagnostic=result['machines'][0]['diagnostic']
    assert diagnostic['code']==code and diagnostic['context']['ssh_alias']=='rusty'
    assert 'sensitive detail' not in json.dumps(result)
    assert len(calls)==2 and result['state']=='partial'


def test_key_auth_ready_does_not_require_master_or_environment(monkeypatch):
    profiles(); calls=[]
    def run(command, **kwargs):
        calls.append(command)
        assert '-O' not in command and '-MNf' not in command
        return subprocess.CompletedProcess(command,0)
    monkeypatch.setattr(subprocess,'run',run)
    assert check_connections()['machines'][0]['state']=='ready'
    assert len(calls)==1


@pytest.mark.parametrize('kwargs',[{'machine':''},{'machine':4},{'all_machines':1},{'machine':'rusty','all_machines':True}])
def test_invalid_connection_request_stops_before_commands(kwargs):
    with pytest.raises(InvalidRequestError): check_connections(**kwargs)


def test_missing_machine_has_typed_error():
    profiles()
    with pytest.raises(ConfigurationError): check_connections('absent')


@pytest.mark.parametrize('native',[TypeError('bug'),KeyboardInterrupt()])
def test_connection_does_not_flatten_bugs_or_interrupts(monkeypatch,native):
    profiles()
    def run(*args,**kwargs): raise native
    monkeypatch.setattr(subprocess,'run',run)
    with pytest.raises(type(native)): check_connections()


def test_connection_cli_json_and_acp_share_evidence(monkeypatch,capsys):
    profiles()
    monkeypatch.setattr(subprocess,'run',lambda command,**kwargs:subprocess.CompletedProcess(command,0))
    root.main(['connection','check','--all','--json'])
    assert len(json.loads(capsys.readouterr().out)['machines'])==3
    assert execute_acp({'action':'check_connections','machine':'rusty'})['result']['machines'][0]['state']=='ready'
    root.main(['connection'])
    assert 'check' in capsys.readouterr().out


def test_policy_keeps_alias_and_owned_options():
    command=ssh_command({'ssh_alias':'rusty'}, remote_command='true', options=['-o','ControlPath=/tmp/socket'])
    assert command==['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','-o','ControlPath=/tmp/socket','rusty','true']
