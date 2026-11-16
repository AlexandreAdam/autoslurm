"""Machine module setup under clean Bash, with no real cluster or module system."""

from contextlib import contextmanager
from io import StringIO
import json
import os
from pathlib import Path
import subprocess

import pytest

from autoslurm import load_config, preview_bundle, save_bundle, save_config, submit_jobs
from autoslurm.apps import config, root
from autoslurm.config import activation_command_from_config, machine_config, normalize_machine_profile, set_machine_settings
from autoslurm.errors import ConfigurationError
from autoslurm.execution import resolve_execution_context
from autoslurm.job_to_slurm import write_slurm_content
from autoslurm import module_initialization as discovery
from autoslurm.storage import config_file_path, slurm_dir


def render(profile):
    output = StringIO()
    write_slurm_content(output, {'name': 'science', 'script': 'printf "science:%s\\n" "$ACTIVATED"', 'slurm': {}}, profile)
    return output.getvalue()


def clean_environment():
    return {key: value for key, value in os.environ.items()
            if key not in {'BASH_ENV', 'ENV', 'MODULE_LOADED', 'ACTIVATED'} and not key.startswith('BASH_FUNC_')}


@pytest.fixture
def machine(tmp_path):
    initializer = tmp_path / "module's init with spaces.sh"
    initializer.write_text('module() { export MODULE_LOADED="$2"; }\n')
    venv = tmp_path / 'venv with spaces'
    (venv / 'bin').mkdir(parents=True)
    (venv / 'bin/activate').write_text('test "$MODULE_LOADED" = wanted || return 1\nexport ACTIVATED=yes\n')
    return {'module_init': str(initializer), 'env_command': 'module load wanted', 'venv_path': str(venv)}


@pytest.mark.local_processes
@pytest.mark.parametrize('rooted', [False, True])
def test_clean_shell_initializes_modules_before_setup_and_activation(machine, tmp_path, rooted):
    if rooted:
        machine['results_root'] = str(tmp_path)
    script = render(machine)
    result = subprocess.run(['bash', '--noprofile', '--norc', '-c', script], env=clean_environment(), capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout == 'science:yes\n'
    # Shared root/config probes use the same ordered setup and preserve functions.
    result = subprocess.run(['bash', '-c', activation_command_from_config(machine) + ' && printf "%s" "$ACTIVATED"'],
                            env=clean_environment(), capture_output=True, text=True)
    assert result.returncode == 0 and result.stdout == 'yes'


@pytest.mark.local_processes
def test_existing_exported_module_skips_initializer(machine):
    Path(machine['module_init']).write_text('printf "initializer should not run" >&2\nreturn 1\n')
    environment = clean_environment()
    environment['BASH_FUNC_module%%'] = '() { export MODULE_LOADED="$2"; }'
    result = subprocess.run(['bash', '-c', render(machine)], env=environment, capture_output=True, text=True)
    assert result.returncode == 0 and result.stdout == 'science:yes\n' and not result.stderr


@pytest.mark.local_processes
@pytest.mark.parametrize('problem,field', [('missing', 'module_init'), ('source-failed', 'module_init'),
    ('not-a-file', 'module_init'), ('no-module', 'module_init'), ('setup', 'env_command'), ('venv', 'venv_path')])
@pytest.mark.parametrize('rooted', [False, True])
def test_each_setup_failure_stops_application(machine, tmp_path, problem, field, rooted):
    initializer = Path(machine['module_init'])
    if problem == 'missing':
        initializer.unlink()
    elif problem == 'not-a-file':
        initializer.unlink()
        initializer.mkdir()
    elif problem == 'source-failed':
        initializer.write_text('return 17\n')
    elif problem == 'no-module':
        initializer.write_text('true\n')
    elif problem == 'setup':
        machine['env_command'] = 'false'
    else:
        (Path(machine['venv_path']) / 'bin/activate').write_text('return 9\n')
    if rooted:
        machine['results_root'] = str(tmp_path)
    result = subprocess.run(['bash', '-c', render(machine)], env=clean_environment(), capture_output=True, text=True)
    assert result.returncode != 0 and 'science:' not in result.stdout
    assert field in result.stderr and 'application not started' in result.stderr


@pytest.mark.local_processes
def test_venv_only_profile_needs_no_module_initialization(machine):
    (Path(machine['venv_path']) / 'bin/activate').write_text('export ACTIVATED=standalone\n')
    script = render({'venv_path': machine['venv_path']})
    assert 'type module' not in script and '/etc/profile' not in script
    result = subprocess.run(['bash', '-c', script], env=clean_environment(), capture_output=True, text=True)
    assert result.returncode == 0 and result.stdout == 'science:standalone\n'


@pytest.mark.parametrize('value', [True, [], 42, 'relative/init.sh', '~/init.sh', '  ', '/init\n.sh', '/init\x00.sh', '/init\x7f.sh'])
def test_invalid_initializer_is_rejected_before_any_commands(value, monkeypatch):
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: pytest.fail('Validation must be pure'))
    with pytest.raises(ConfigurationError) as caught:
        normalize_machine_profile({'module_init': value}, machine='cluster')
    assert caught.value.diagnostic.context['field'] == 'module_init'


def test_initializer_alone_is_not_a_python_environment():
    save_config({'machines': {'mock': {'module_init': '/site/init.sh'}}, 'default_machine': 'mock'})
    with pytest.raises(ConfigurationError, match='venv_path'):
        machine_config()


def save_profiles():
    save_config({'machines': {'cluster': {'ssh_alias': 'research', 'venv_path': '/venv',
        'env_command': 'module load wanted', 'module_init': '/old/init.sh'}, 'local': {'venv_path': '/local-env'}},
        'default_machine': 'cluster', 'bundle_filter_mode': 'all'})


def test_set_clear_summary_and_reads_do_not_contact_machine(monkeypatch, capsys):
    save_profiles()
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: pytest.fail('Ordinary config must not discover machines'))
    before = load_config()
    root.main(['config', '--machine', 'cluster', '--module-init', '/site/init with spaces.sh'])
    assert load_config()['machines']['cluster']['module_init'] == '/site/init with spaces.sh'
    root.main(['config', '--summary'])
    assert '/site/init with spaces.sh' in capsys.readouterr().out
    root.main(['configuration', '--clear-module-init'])
    before['machines']['cluster'].pop('module_init')
    assert load_config()['machines'] == before['machines']
    assert 'module_init' not in json.loads(config_file_path().read_text())['machines']['cluster']


@pytest.mark.parametrize('args', [['--module-init', 'relative'], ['--module-init', '/x', '--clear-module-init'],
    ['--detect-module-init', '--view'], ['--detect-module-init', '--results-root', '/data'],
    ['--detect-module-init', '--machine', 'missing'], ['--detect-module-init', '--machine', '']])
def test_invalid_config_actions_preserve_file(args, monkeypatch):
    save_profiles()
    before = config_file_path().read_bytes()
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: pytest.fail('Invalid request made contact'))
    with pytest.raises(SystemExit):
        config.main(args)
    assert config_file_path().read_bytes() == before


@pytest.mark.parametrize('answer,expected', [('', '/old/init.sh'), ('-', None), ('/custom/init.sh', '/custom/init.sh')])
def test_interactive_editor_keeps_sets_and_clears_module_init(answer, expected, monkeypatch):
    answers = iter(['', '', answer, '', 'y', '', '', ''])
    monkeypatch.setattr('builtins.input', lambda prompt: next(answers))
    profile = {'ssh_alias': 'research', 'venv_path': '/venv', 'env_command': 'module load wanted', 'module_init': '/old/init.sh'}
    edited = config._prompt_machine_details(profile)
    assert edited.get('module_init') == expected
    assert edited['env_command'] == profile['env_command'] and edited['venv_path'] == '/venv'


@pytest.mark.local_processes
def test_detection_checks_readable_files_without_executing_setup(tmp_path, monkeypatch):
    marker = tmp_path / 'must not exist'
    candidate = tmp_path / 'initializer.sh'
    candidate.write_text(f'touch "{marker}"\nexit 19\n')
    monkeypatch.setattr(discovery, 'MODULE_INITIALIZERS', (str(tmp_path / 'missing'), str(candidate)))
    assert discovery.detect_module_initializer({'env_command': f'touch "{marker}"'}) == str(candidate)
    assert not marker.exists()


def test_remote_detection_saves_one_path_using_alias_without_activation(monkeypatch, capsys):
    save_profiles()
    commands = []
    candidate = discovery.MODULE_INITIALIZERS[1]
    def probe(command, **kwargs):
        commands.append(command)
        assert command[:2] == ['ssh', 'research'] and 'bash -c ' in command[2]
        assert 'source ' not in command[2] and 'module load' not in command[2] and '/venv' not in command[2]
        assert kwargs['timeout'] == 30
        return subprocess.CompletedProcess(command, 0, candidate + '\n', '')
    monkeypatch.setattr(subprocess, 'run', probe)
    config.main(['--machine', 'cluster', '--detect-module-init'])
    assert len(commands) == 1 and load_config()['machines']['cluster']['module_init'] == candidate
    assert load_config()['machines']['local'] == {'venv_path': '/local-env'}
    assert 'without executing' in capsys.readouterr().out


def test_interactive_detection_updates_the_selected_profile_and_menu_state(monkeypatch):
    save_profiles()
    choices = iter(['7', '1', '6'])
    monkeypatch.setattr('builtins.input', lambda prompt: next(choices))
    candidate = discovery.MODULE_INITIALIZERS[0]
    monkeypatch.setattr(subprocess, 'run', lambda command, **k: subprocess.CompletedProcess(command, 0, candidate + '\n', ''))
    config.main(['--interactive'])
    assert load_config()['machines']['cluster']['module_init'] == candidate


def test_programmatic_set_clear_conflict_preserves_existing_profile():
    save_profiles()
    before = config_file_path().read_bytes()
    with pytest.raises(ConfigurationError, match='not both'):
        set_machine_settings('cluster', module_init='/site/init.sh', clear_module_init=True)
    assert config_file_path().read_bytes() == before


@pytest.mark.parametrize('code,stdout,stderr,diagnostic', [(1, '', '', 'resource_missing'),
    (255, '', 'secret SSH detail', 'transport_failed'), (0, '/unexpected/path\n', '', 'protocol_invalid'),
    (0, 'banner\n/etc/profile.d/lmod.sh\n', '', 'protocol_invalid'), (2, '', 'failure', 'protocol_invalid')])
def test_failed_detection_does_not_change_configuration(code, stdout, stderr, diagnostic, monkeypatch, capsys):
    save_profiles()
    before = config_file_path().read_bytes()
    monkeypatch.setattr(subprocess, 'run', lambda command, **k: subprocess.CompletedProcess(command, code, stdout, stderr))
    with pytest.raises(SystemExit) as stopped:
        config.main(['--detect-module-init'])
    assert stopped.value.code == 1 and diagnostic in capsys.readouterr().err
    assert config_file_path().read_bytes() == before


@pytest.mark.parametrize('native', [FileNotFoundError('bash'), subprocess.TimeoutExpired(['ssh'], 30)])
def test_detection_launch_failures_keep_native_cause(native, monkeypatch):
    save_profiles()
    before = config_file_path().read_bytes()
    def fail(*a, **k):
        raise native
    monkeypatch.setattr(subprocess, 'run', fail)
    with pytest.raises(ConfigurationError) as caught:
        config.main(['--detect-module-init', '--debug'])
    assert caught.value.__cause__ is native
    assert caught.value.diagnostic.effects['config_write'] == 'not_started'
    assert config_file_path().read_bytes() == before


@pytest.mark.parametrize('remote', [False, True])
def test_preview_and_dispatch_share_setup_without_executing_it(machine, remote, monkeypatch):
    from autoslurm import submission_operation
    from tests.submission_helpers import accepted_receipt
    profile = {**machine, **({'ssh_alias': 'research', 'path': '/remote/state'} if remote else {})}
    context = resolve_execution_context('mock', profile)
    selected = save_bundle({'science': {'script': 'scientific-command', 'slurm': {}}}, 'study')
    monkeypatch.setattr('autoslurm.bundle_preparation.validate_slurm_content', lambda content: None)
    monkeypatch.setattr('autoslurm.job_runner.probe_submission_helper', lambda context: None)
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: pytest.fail('Unexpected setup execution'))
    seen = []
    @contextmanager
    def session(*a, **k):
        yield []
    def dispatched(payload, **kwargs):
        for name in payload['slurm_names'].values():
            seen.append((slurm_dir() / name).read_text())
        return accepted_receipt(payload, {'science': '101'})
    if remote:
        monkeypatch.setattr(submission_operation, 'transfer_slurms_to_remote', lambda *a, **k: None)
        monkeypatch.setattr(submission_operation, 'ssh_submission_session', session)
        monkeypatch.setattr(submission_operation, 'run_bulk_submit_driver_remotely', dispatched)
    else:
        def sbatch(command, **kwargs):
            assert command[0] == 'sbatch'
            seen.append(Path(command[-1]).read_text())
            return subprocess.CompletedProcess(command, 0, 'Submitted batch job 101', '')
        monkeypatch.setattr(subprocess, 'run', sbatch)
    save_config({'machines': {'mock': profile}, 'default_machine': 'mock'})
    preview = preview_bundle(selected, machine='mock')
    receipt = submit_jobs('study', bundle_path=selected, context=context)
    assert receipt['state'] == 'submitted' and len(seen) == 1
    assert seen[0] == preview['jobs']['science']['script']
    assert 'module_init' in seen[0] and seen[0].index('type module') < seen[0].index('module load wanted')
