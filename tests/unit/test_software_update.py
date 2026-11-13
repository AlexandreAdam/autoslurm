"""One checkout and one selected environment; pull then refresh editable."""

import json
import os
from pathlib import Path
from subprocess import CompletedProcess, TimeoutExpired

import pytest

from autoslurm import save_config, storage, update_software, SoftwareUpdateError
from autoslurm.apps import software
from autoslurm.software_update_probe import update_checkout


FIRST, SECOND = 'a' * 40, 'b' * 40


@pytest.fixture
def checkout(tmp_path):
    root = tmp_path / 'software with spaces'
    path = root / 'science'
    (path / '.git').mkdir(parents=True)
    save_config({'default_machine': 'fixture', 'machines': {'fixture': {
        'software_root': str(root), 'venv_path': str(root.parent / 'environment')}}})
    return root, path


class Git:
    def __init__(self, path):
        self.path, self.head, self.calls = path, FIRST, []
        self.dirty = ''
        self.branch = 'main'
        self.upstream = 'origin/main'
        self.top = str(path)
        self.exit = 0
        self.stderr = ''
        self.timeout = False
        self.advance = True
        self.install_exit = 0
        self.install_timeout = False
        self.install_stdout = ''
        self.install_stderr = 'build backend could not build the editable wheel'
        self.prefix = str(path.parent.parent / 'environment')

    def __call__(self, command, **options):
        self.calls.append(command)
        if command[0] != 'git':
            assert command[0] == str(self.path.parent.parent / 'environment/bin/python')
            if '-c' in command:
                return CompletedProcess(command, 0, json.dumps({'prefix': self.prefix}), '')
            assert command[-2:] == ['--editable', str(self.path)]
            assert '--no-deps' in command and '--no-cache-dir' in command
            assert '--no-build-isolation' not in command and '--no-index' not in command
            assert options['cwd'] == str(self.path)
            assert options['env']['PIP_CONFIG_FILE'] == os.devnull
            assert 'PIP_TARGET' not in options['env']
            if self.install_timeout:
                raise TimeoutExpired(command, 120)
            return CompletedProcess(command, self.install_exit, self.install_stdout, self.install_stderr)
        assert command[:3] == ['git', '-C', str(self.path)]
        assert options['env']['GIT_TERMINAL_PROMPT'] == '0'
        args = command[3:]
        if 'pull' in args:
            assert '--ff-only' in args and '--no-recurse-submodules' in args
            assert 'rebase.autoStash=false' in args and 'merge.autoStash=false' in args
            if self.timeout:
                raise TimeoutExpired(command, 120)
            if self.exit == 0 and self.advance:
                self.head = SECOND
            return CompletedProcess(command, self.exit, '', self.stderr)
        if args == ['rev-parse', '--show-toplevel']:
            value, code = self.top, 0
        elif args == ['rev-parse', '--verify', 'HEAD^{commit}']:
            value, code = self.head, 0
        elif args[0] == 'symbolic-ref':
            value, code = self.branch or '', 0 if self.branch else 1
        elif args[-1] == '@{upstream}':
            value, code = self.upstream or '', 0 if self.upstream else 128
        elif args[0] == 'status':
            value, code = self.dirty, 0
        else:
            pytest.fail(f'Unexpected Git operation: {args}')
        return CompletedProcess(command, code, value + '\n', '')


def test_update_pulls_once_in_place_and_saves_no_extra_files(checkout, monkeypatch):
    root, path = checkout
    git = Git(path)
    monkeypatch.setattr('subprocess.run', git)
    before = set(root.rglob('*')) | set(storage.storage_root().rglob('*'))
    result = update_software(machine='fixture', project='science')
    assert result['state'] == 'updated'
    assert (result['before_commit'], result['after_commit']) == (FIRST, SECOND)
    assert result['branch'] == 'main' and result['upstream'] == 'origin/main'
    assert sum('pull' in call for call in git.calls) == 1
    assert not any(set(call) & {'clone', 'checkout', 'worktree', 'reset', 'stash'} for call in git.calls)
    assert sum('install' in call for call in git.calls) == 1
    assert result['installation']['state'] == 'installed'
    assert before == set(root.rglob('*')) | set(storage.storage_root().rglob('*'))


def test_already_current_reports_up_to_date_without_new_records(checkout, monkeypatch):
    root, path = checkout
    git = Git(path)
    git.advance = False
    monkeypatch.setattr('subprocess.run', git)
    result = update_software(project='science')
    assert result['state'] == 'up_to_date' and result['installation']['state'] == 'installed'
    assert sum('install' in call for call in git.calls) == 1
    assert list(root.iterdir()) == [path]


@pytest.mark.parametrize('dirty', [' M science.py', '?? scratch.py'])
def test_dirty_checkout_is_preserved_without_pull(checkout, monkeypatch, dirty):
    root, path = checkout
    git = Git(path)
    git.dirty = dirty
    monkeypatch.setattr('subprocess.run', git)
    with pytest.raises(SoftwareUpdateError, match='local changes') as caught:
        update_software(project='science')
    assert caught.value.evidence['stage'] == 'preflight'
    assert not any('pull' in command for command in git.calls)
    assert git.head == FIRST


@pytest.mark.parametrize('field,match', [('branch', 'detached'), ('upstream', 'no configured upstream')])
def test_branch_setup_is_not_changed_implicitly(checkout, monkeypatch, field, match):
    root, path = checkout
    git = Git(path)
    setattr(git, field, None)
    monkeypatch.setattr('subprocess.run', git)
    with pytest.raises(SoftwareUpdateError, match=match):
        update_software(project='science')
    assert not any('pull' in command for command in git.calls)


@pytest.mark.parametrize('stderr,message', [('fatal: Not possible to fast-forward', 'cannot fast-forward'),
    ('Permission denied. https://secret@host.invalid/repo.git', 'authentication'), ('private token secret', 'exit 128')])
def test_pull_failure_reports_bounded_evidence_without_reset_or_secret_output(checkout, monkeypatch, stderr, message):
    root, path = checkout
    git = Git(path)
    git.exit, git.stderr = 128, stderr
    monkeypatch.setattr('subprocess.run', git)
    with pytest.raises(SoftwareUpdateError, match=message) as caught:
        update_software(project='science')
    record = caught.value.evidence
    assert record['state'] == 'failed' and record['after_commit'] == FIRST
    assert 'secret' not in json.dumps(record)
    assert sum('pull' in command for command in git.calls) == 1


def test_pull_timeout_stays_unknown_and_is_not_retried(checkout, monkeypatch):
    root, path = checkout
    git = Git(path)
    git.timeout = True
    monkeypatch.setattr('subprocess.run', git)
    with pytest.raises(SoftwareUpdateError) as caught:
        update_software(project='science')
    assert caught.value.evidence['state'] == 'unknown'
    assert caught.value.evidence['before_commit'] == FIRST
    assert caught.value.evidence['after_commit'] is None
    assert sum('pull' in command for command in git.calls) == 1


def test_missing_checkout_is_not_cloned_or_created(tmp_path, monkeypatch):
    monkeypatch.setattr('subprocess.run', lambda *a, **k: pytest.fail('Missing checkout must not run Git'))
    root = tmp_path / 'missing'
    result = update_checkout(str(root), 'science')
    assert result['state'] == 'failed' and 'missing' in result['error']
    assert not root.exists()


def test_project_cannot_resolve_outside_selected_software_root(checkout, tmp_path, monkeypatch):
    root, path = checkout
    outside = tmp_path / 'other'
    outside.mkdir()
    (root / 'redirected').symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr('subprocess.run', lambda *a, **k: pytest.fail('Outside project must not run Git'))
    assert 'outside software_root' in update_checkout(str(root), 'redirected')['error']


def test_subdirectory_cannot_accidentally_pull_an_enclosing_repository(checkout, monkeypatch):
    root, path = checkout
    git = Git(path)
    git.top = str(root)
    monkeypatch.setattr('subprocess.run', git)
    with pytest.raises(SoftwareUpdateError, match='checkout root'):
        update_software(project='science')
    assert not any('pull' in command for command in git.calls)


@pytest.mark.parametrize('project', ['', '/absolute', '../other', 'a/../b', 'x\\y', 'x\ncommand'])
def test_invalid_relative_selector_is_rejected_before_profile_discovery(monkeypatch, project):
    monkeypatch.setattr('autoslurm.software_update.load_config', lambda: pytest.fail('Invalid selector must fail first'))
    with pytest.raises(ValueError, match='relative'):
        update_software(project=project)


def remote_profile(root):
    save_config({'default_machine': 'remote', 'machines': {'remote': {
        'ssh_alias': 'research', 'software_root': str(root), 'venv_path': str(root.parent / 'environment')}}})


def response(root):
    return {'version': 1, 'software_root': str(root), 'project': 'science', 'path': str(root / 'science'),
            'state': 'updated', 'branch': 'main', 'upstream': 'origin/main',
            'before_commit': FIRST, 'after_commit': SECOND, 'observed_at': 'now', 'stage': 'complete',
            'installation': {'state': 'installed', 'editable': True, 'returncode': 0,
                             'python': str(root.parent / 'environment/bin/python'), 'path': str(root / 'science')}}


def test_remote_update_is_one_ssh_stdin_probe_without_remote_autoslurm(checkout, monkeypatch):
    root, _ = checkout
    remote_profile(root)
    calls = []
    def ssh(command, **options):
        calls.append(command)
        assert command[-2:] == ['research', 'python3 -B -']
        assert 'from autoslurm' not in options['input']
        assert 'def update_checkout' in options['input']
        assert 'mkdir' not in options['input'] and 'write_text' not in options['input']
        return CompletedProcess(command, 0, json.dumps(response(root)), '')
    monkeypatch.setattr('subprocess.run', ssh)
    assert update_software(project='science')['machine'] == 'remote'
    assert len(calls) == 1


@pytest.mark.parametrize('failure', ['connection', 'timeout', 'malformed', 'wrong-project', 'incomplete-success'])
def test_lost_or_invalid_remote_response_is_unknown_without_retry_or_fallback(checkout, monkeypatch, failure):
    root, _ = checkout
    remote_profile(root)
    calls = []
    def ssh(command, **options):
        calls.append(command)
        record = response(root)
        if failure == 'timeout':
            raise TimeoutExpired(command, 300)
        if failure == 'wrong-project':
            record['project'] = 'other'
        if failure == 'incomplete-success':
            record['after_commit'] = None
        return CompletedProcess(command, 255 if failure == 'connection' else 0,
                                'bad' if failure == 'malformed' else json.dumps(record), '')
    monkeypatch.setattr('subprocess.run', ssh)
    with pytest.raises(SoftwareUpdateError) as caught:
        update_software(project='science')
    assert caught.value.evidence['state'] == 'unknown'
    assert len(calls) == 1


@pytest.mark.parametrize('argv', [[], ['update'], ['status']])
def test_empty_software_commands_print_help_without_contact(monkeypatch, capsys, argv):
    monkeypatch.setattr('autoslurm.software_update.load_config', lambda: pytest.fail('Help must not load profiles'))
    software.main(argv)
    assert 'usage:' in capsys.readouterr().out


def test_cli_json_reports_commit_change(checkout, monkeypatch, capsys):
    root, _ = checkout
    monkeypatch.setattr(software, 'update_software', lambda **kw: {**response(root), 'machine': 'fixture'})
    software.main(['update', '--project', 'science', '--json'])
    assert json.loads(capsys.readouterr().out)['after_commit'] == SECOND


def test_cli_unknown_prints_inspection_command_without_traceback(monkeypatch, capsys):
    def failed(**kw):
        raise SoftwareUpdateError('Update outcome is unknown', {'state': 'unknown', 'machine': 'fixture'})
    monkeypatch.setattr(software, 'update_software', failed)
    with pytest.raises(SystemExit) as caught:
        software.main(['update', '--project', 'science'])
    output = capsys.readouterr().out
    assert caught.value.code == 1 and 'status --machine fixture --project science' in output
    assert 'Traceback' not in output


def test_unreadable_commit_after_pull_does_not_report_the_old_commit_as_current(checkout, monkeypatch):
    root, path = checkout
    git = Git(path)
    def unreadable(command, **kwargs):
        result = git(command, **kwargs)
        if command[-1] == 'HEAD^{commit}' and git.head == SECOND:
            return CompletedProcess(command, 128, '', 'unreadable')
        return result
    monkeypatch.setattr('subprocess.run', unreadable)
    with pytest.raises(SoftwareUpdateError) as caught:
        update_software(project='science')
    assert caught.value.evidence['state'] == 'unknown'
    assert caught.value.evidence['after_commit'] is None


@pytest.mark.parametrize('unchanged', [False, True])
def test_install_failure_retains_successful_pull_evidence(checkout, monkeypatch, unchanged):
    root, path = checkout
    git = Git(path)
    git.advance, git.install_exit = not unchanged, 1
    monkeypatch.setattr('subprocess.run', git)
    monkeypatch.setenv('PIP_TARGET', '/unwanted/install')
    with pytest.raises(SoftwareUpdateError, match='Editable installation failed') as caught:
        update_software(project='science')
    result = caught.value.evidence
    assert result['stage'] == 'install' and result['state'] == 'failed'
    assert result['after_commit'] == (FIRST if unchanged else SECOND)
    assert result['installation']['state'] == 'failed'
    assert result['installation']['returncode'] == 1
    assert git.install_stderr == result['installation']['output_tail']
    assert git.install_stderr in str(caught.value)
    assert sum('pull' in call for call in git.calls) == 1
    assert sum('install' in call for call in git.calls) == 1


def test_install_timeout_retains_pulled_commit_and_does_not_retry(checkout, monkeypatch):
    _, path = checkout
    git = Git(path)
    git.install_timeout = True
    monkeypatch.setattr('subprocess.run', git)
    with pytest.raises(SoftwareUpdateError) as caught:
        update_software(project='science')
    result = caught.value.evidence
    assert result['state'] == 'unknown' and result['stage'] == 'install'
    assert result['after_commit'] == SECOND and result['installation']['state'] == 'unknown'
    assert sum('install' in call for call in git.calls) == 1


def test_pip_failure_carries_last_twenty_lines_and_omits_credential_urls(checkout, monkeypatch):
    _, path = checkout
    git = Git(path)
    git.install_exit = 1
    git.install_stdout = '\n'.join(f'build line {index}' for index in range(30))
    git.install_stderr = 'Downloading https://name:secret@example.invalid/backend\nsetuptools_scm.integration has no attribute infer_version'
    monkeypatch.setattr('subprocess.run', git)
    with pytest.raises(SoftwareUpdateError) as caught:
        update_software(project='science')
    evidence = caught.value.evidence
    tail = evidence['installation']['output_tail']
    assert tail.splitlines() == [f'build line {index}' for index in range(12, 30)] + [git.install_stderr.splitlines()[-1]]
    assert 'infer_version' in str(caught.value)
    assert 'secret' not in json.dumps(evidence) and 'secret' not in str(caught.value)
    assert evidence['stage'] == 'install' and evidence['after_commit'] == SECOND


def test_pip_failure_tail_is_byte_bounded(checkout, monkeypatch):
    _, path = checkout
    git = Git(path)
    git.install_exit = 1
    git.install_stderr = 'x' * 100000 + '\nlast build error'
    monkeypatch.setattr('subprocess.run', git)
    with pytest.raises(SoftwareUpdateError) as caught:
        update_software(project='science')
    tail = caught.value.evidence['installation']['output_tail']
    assert len(tail.encode('utf-8')) <= 4096 and tail.endswith('last build error')
    assert len(json.dumps(caught.value.evidence)) < 65536


@pytest.mark.parametrize('as_json', [False, True])
def test_cli_exposes_pip_build_failure_tail(checkout, monkeypatch, capsys, as_json):
    _, path = checkout
    git = Git(path)
    git.install_exit = 1
    git.install_stderr = 'BackendUnavailable: cannot import build backend'
    monkeypatch.setattr('subprocess.run', git)
    with pytest.raises(SystemExit) as caught:
        software.main(['update', '--project', 'science'] + (['--json'] if as_json else []))
    output = capsys.readouterr().out
    assert caught.value.code == 1 and 'BackendUnavailable' in output
    if as_json:
        assert json.loads(output)['installation']['output_tail'] == git.install_stderr


@pytest.mark.parametrize('failure', ['wrong-prefix', 'malformed', 'timeout', 'missing-python'])
def test_wrong_or_unavailable_environment_is_rejected_before_pulling(checkout, monkeypatch, failure):
    _, path = checkout
    git = Git(path)
    git.prefix = '/system/python'
    def run(command, **kwargs):
        if '-c' in command:
            if failure == 'malformed':
                return CompletedProcess(command, 0, 'not JSON', '')
            if failure == 'timeout':
                raise TimeoutExpired(command, 15)
            if failure == 'missing-python':
                raise FileNotFoundError('selected Python unavailable')
        return git(command, **kwargs)
    monkeypatch.setattr('subprocess.run', run)
    with pytest.raises(SoftwareUpdateError) as caught:
        update_software(project='science')
    assert caught.value.evidence['stage'] == 'preflight'
    assert caught.value.evidence['installation']['state'] == 'not_started'
    assert not any('pull' in cmd or 'install' in cmd for cmd in git.calls)


def test_missing_environment_configuration_does_not_contact_machine(checkout, monkeypatch):
    root, _ = checkout
    save_config({'default_machine': 'remote', 'machines': {'remote': {
        'ssh_alias': 'research', 'software_root': str(root)}}})
    monkeypatch.setattr('subprocess.run', lambda *a, **kw: pytest.fail('Missing venv must fail before SSH'))
    with pytest.raises(ValueError, match='venv_path'):
        update_software(project='science')


@pytest.mark.parametrize('field,value', [('state', 'not_started'), ('python', '/wrong/bin/python'),
                                      ('editable', False), ('returncode', 1)])
def test_remote_success_requires_selected_editable_installation(checkout, monkeypatch, field, value):
    root, _ = checkout
    remote_profile(root)
    result = response(root)
    result['installation'][field] = value
    calls = []
    monkeypatch.setattr('subprocess.run', lambda cmd, **kw: calls.append(cmd) or CompletedProcess(cmd, 0, json.dumps(result), ''))
    with pytest.raises(SoftwareUpdateError) as caught:
        update_software(project='science')
    assert caught.value.evidence['state'] == 'unknown' and len(calls) == 1


def test_cli_text_reports_installation_after_unchanged_pull(checkout, monkeypatch, capsys):
    root, _ = checkout
    result = response(root)
    result.update(state='up_to_date', after_commit=FIRST, machine='fixture')
    monkeypatch.setattr(software, 'update_software', lambda **kw: result)
    software.main(['update', '--project', 'science'])
    text = capsys.readouterr().out
    assert 'Already up to date' in text and 'Editable install refreshed' in text


def test_remote_install_failure_keeps_commit_and_prints_failed_stage(checkout, monkeypatch, capsys):
    root, _ = checkout
    remote_profile(root)
    result = response(root)
    result.update(state='failed', stage='install', error='Editable installation failed')
    result['installation'].update(state='failed', returncode=1)
    calls = []
    monkeypatch.setattr('subprocess.run', lambda cmd, **kw: calls.append(cmd) or CompletedProcess(cmd, 0, json.dumps(result), ''))
    with pytest.raises(SystemExit) as caught:
        software.main(['update', '--project', 'science'])
    text = capsys.readouterr().out
    assert caught.value.code == 1 and SECOND in text and 'Editable install: failed' in text
    assert len(calls) == 1
