"""File metadata/transfer failures retain effects, not false absence or retries."""

import contextlib
from datetime import datetime
import errno
import io
import json
from pathlib import Path
import subprocess

import pytest

from autoslurm import (path_exists, save_config, submit_jobs, SubmissionError,
                      transfer_slurm_to_remote, transfer_slurms_to_remote, transfer_bundle_to_remote)
from autoslurm import path_probe
from autoslurm.apps import root
from autoslurm.errors import DiagnosticError, InvalidRequestError
from autoslurm.execution import resolve_execution_context
from autoslurm.file_transfer import pull_storage_directory
from autoslurm.storage import slurm_dir, jobs_dir
from autoslurm.sync import sync_machine
from tests.integration.test_execution_tracking import installations


PROFILE = {'ssh_alias': 'research-cluster', 'path': '/selected/state', 'results_root': '/selected/results', 'env_command': 'true'}


def metadata(path, state='exists', kind='directory', number=None):
    return json.dumps({'version': 1, 'path': str(path), 'state': state, 'kind': kind, 'errno': number})


@pytest.fixture
def selected():
    return resolve_execution_context('cluster', PROFILE)


@pytest.fixture
def sources():
    for name in ('a.sh', 'b.sh'):
        (slurm_dir() / name).write_text('science')


def test_local_metadata_handles_files_directories_links_and_absence(tmp_path, monkeypatch):
    ctx = resolve_execution_context('local', {'results_root': str(tmp_path)})
    (tmp_path / 'file').write_text('do not read contents')
    (tmp_path / 'dir').mkdir()
    (tmp_path / 'link').symlink_to(tmp_path / 'file')
    (tmp_path / 'broken').symlink_to(tmp_path / 'absent')
    monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: pytest.fail('Local stat needs no process'))
    for name in ('file', 'dir', 'link'):
        assert path_exists(name, context=ctx)
    for name in ('absent', 'file/child', 'broken'):
        assert not path_exists(name, context=ctx)


@pytest.mark.parametrize('number', [errno.EACCES, errno.EIO, errno.ELOOP])
def test_local_metadata_failure_retains_native_cause(tmp_path, monkeypatch, number):
    ctx = resolve_execution_context('local', {'results_root': str(tmp_path)})
    native = OSError(number, 'retained-secret')
    original = path_probe.os.stat
    def stat(path, *args, **kwargs):
        if str(path) == str(tmp_path / 'data'):
            raise native
        return original(path, *args, **kwargs)
    monkeypatch.setattr(path_probe.os, 'stat', stat)
    with pytest.raises(DiagnosticError) as stopped:
        path_exists('data', context=ctx)
    error = stopped.value
    assert error.__cause__ is native
    assert error.diagnostic.code == 'resource_inaccessible'
    assert error.diagnostic.context['logical_path'] == 'data'
    assert error.diagnostic.effects['path_observation'] == 'failed'
    assert 'retained-secret' not in json.dumps(error.diagnostic.to_dict())


@pytest.mark.parametrize('state,kind,number,expected', [
    ('exists', 'file', None, True), ('exists', 'other', None, True),
    ('missing', None, errno.ENOENT, False), ('missing', None, errno.ENOTDIR, False)])
def test_remote_metadata_has_explicit_absence(selected, monkeypatch, state, kind, number, expected):
    calls = []
    def run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, metadata('/selected/results/data', state, kind, number), '')
    monkeypatch.setattr(subprocess, 'run', run)
    assert path_exists('data', context=selected) is expected
    assert calls[0][0] == ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', 'research-cluster', 'python3 -B -']
    assert calls[0][1]['timeout'] == 30 and len(calls) == 1


@pytest.mark.parametrize('number', [errno.EACCES, errno.EIO, errno.ELOOP, None])
def test_remote_denied_or_failed_stat_is_not_absence(selected, monkeypatch, number):
    monkeypatch.setattr(subprocess, 'run', lambda cmd, **kw: subprocess.CompletedProcess(
        cmd, 0, metadata('/selected/results/data', 'unavailable', None, number), ''))
    with pytest.raises(DiagnosticError) as stopped:
        path_exists('data', context=selected)
    assert stopped.value.diagnostic.code == 'resource_inaccessible'
    assert stopped.value.diagnostic.cause.errno == number


@pytest.mark.parametrize('response', [
    '', '{}', '[]', 'null', 'startup banner\n{}',
    metadata('/wrong/path'),
    metadata('/selected/results/data', 'missing', None, errno.EACCES),
    metadata('/selected/results/data', 'exists', 'file', True),
    metadata('/selected/results/data').replace('"version": 1', '"version": true'),
    metadata('/selected/results/data')[:-1] + ', "version": 1}',
    '[' * 1500 + ']' * 1500,
    'x' * 65537, '\ud800', None])
def test_invalid_probe_responses_never_mean_missing(selected, monkeypatch, response):
    monkeypatch.setattr(subprocess, 'run', lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, response, 'retained-secret'))
    with pytest.raises(DiagnosticError) as stopped:
        path_exists('data', context=selected)
    assert stopped.value.diagnostic.code == 'protocol_invalid'
    assert 'retained-secret' not in json.dumps(stopped.value.diagnostic.to_dict())


def test_same_worker_runs_locally_and_remotely_without_reading_contents(tmp_path, monkeypatch):
    path = tmp_path / "a 'quoted' $(touch unwanted) file"
    path.write_text('science')
    ctx = resolve_execution_context('cluster', {**PROFILE, 'results_root': str(tmp_path)})
    def run(command, **kwargs):
        assert command == ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', 'research-cluster', 'python3 -B -']
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exec(kwargs['input'], {})
        return subprocess.CompletedProcess(command, 0, output.getvalue(), '')
    monkeypatch.setattr(subprocess, 'run', run)
    monkeypatch.setattr('builtins.open', lambda *a, **kw: pytest.fail('Metadata must not open scientific files'))
    assert path_exists(path.name, context=ctx)


def fault_value(name):
    return {'missing': FileNotFoundError(errno.ENOENT, 'retained-secret'),
            'denied': PermissionError(errno.EACCES, 'retained-secret'),
            'io': OSError(errno.EIO, 'retained-secret'),
            'timeout': subprocess.TimeoutExpired(['retained-secret'], 30),
            'encoding': UnicodeDecodeError('utf-8', b'\xff', 0, 1, 'retained-secret')}.get(name)


@pytest.mark.parametrize('stage', ['probe', 'mkdir', 'scp', 'rsync'])
@pytest.mark.parametrize('fault,code', [('missing', 'command_unavailable'), ('denied', 'command_unavailable'),
    ('io', 'transport_failed'), ('timeout', 'command_timeout'), ('encoding', 'protocol_invalid'),
    ('ssh255', 'transport_failed'), ('exit1', 'command_failed'), ('signal', 'operation_interrupted'),
    ('badcode', 'protocol_invalid')])
def test_command_fault_matrix_retains_stage_effects_without_retry(selected, sources, tmp_path, monkeypatch, stage, fault, code):
    calls = []
    native = fault_value(fault)
    def run(command, **kwargs):
        calls.append(command)
        current = 'probe' if command[-1] == 'python3 -B -' else 'mkdir' if command[0] == 'ssh' else command[0]
        if current == stage:
            if native is not None:
                raise native
            rc = {'ssh255': 255, 'exit1': 1, 'signal': -15, 'badcode': True}[fault]
            return subprocess.CompletedProcess(command, rc, 'retained-secret', 'retained-secret')
        text = metadata('/selected/state/out') if current == 'probe' else ''
        assert kwargs['timeout'] == (300 if current in ('scp', 'rsync') else 30)
        return subprocess.CompletedProcess(command, 0, text, '')
    monkeypatch.setattr(subprocess, 'run', run)
    with pytest.raises(DiagnosticError) as stopped:
        if stage == 'probe':
            path_exists('data', context=selected)
        elif stage == 'rsync':
            pull_storage_directory(selected, 'out', tmp_path / 'target', mutable=True)
        else:
            transfer_slurms_to_remote(['a.sh', 'b.sh'], context=selected)
    diagnostic = stopped.value.diagnostic
    assert diagnostic.code == code and diagnostic.context['ssh_alias'] == 'research-cluster'
    assert len(calls) == (2 if stage in ('scp', 'rsync') else 1)
    assert 'retained-secret' not in json.dumps(diagnostic.to_dict())
    if native:
        assert stopped.value.__cause__ is native
    if stage in ('scp', 'rsync'):
        assert diagnostic.effects['file_transfer'] == ('not_started' if fault in ('missing', 'denied') else 'unknown')
        assert diagnostic.effects['destination_preparation'] == 'succeeded'
    if stage == 'mkdir':
        assert diagnostic.effects['file_transfer'] == 'not_started'


@pytest.mark.parametrize('name', ['../escape', '/absolute', 'a/b', 'a\\b', '', 'bad\nname'])
def test_invalid_transfer_names_have_no_effect(monkeypatch, name):
    monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: pytest.fail('Invalid name reached transport'))
    with pytest.raises(InvalidRequestError):
        transfer_slurms_to_remote([name], machine_config=PROFILE)


@pytest.mark.parametrize('kind', ['absent', 'directory', 'denied'])
def test_invalid_local_sources_stop_before_discovery_or_remote_mutation(tmp_path, monkeypatch, kind):
    source = slurm_dir() / 'a.sh'
    if kind == 'directory':
        source.mkdir()
    native = PermissionError(errno.EACCES, 'retained-secret')
    if kind == 'denied':
        def denied(*a, **kw):
            raise native
        monkeypatch.setattr('autoslurm.file_transfer.probe_path', denied)
    monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: pytest.fail('Invalid source reached transport'))
    with pytest.raises(DiagnosticError) as stopped:
        transfer_slurms_to_remote(['a.sh'], machine_config={'ssh_alias': 'research-cluster'})
    assert stopped.value.diagnostic.stage == 'validate_source'
    assert stopped.value.diagnostic.effects['destination_preparation'] == 'not_started'
    if kind in ('absent', 'denied'):
        assert isinstance(stopped.value.__cause__, OSError)


def test_missing_or_wrong_kind_sync_source_does_not_create_target(selected, tmp_path, monkeypatch):
    target = tmp_path / 'never' / 'created'
    mode = 'missing'
    def run(command, **kwargs):
        assert command[0] == 'ssh'
        text = metadata('/selected/state/out', 'missing', None, errno.ENOENT) if mode == 'missing' else metadata('/selected/state/out', 'exists', 'file')
        return subprocess.CompletedProcess(command, 0, text, '')
    monkeypatch.setattr(subprocess, 'run', run)
    assert pull_storage_directory(selected, 'out', target) is None
    assert not target.exists()
    mode = 'file'
    with pytest.raises(DiagnosticError) as stopped:
        pull_storage_directory(selected, 'out', target)
    assert stopped.value.diagnostic.stage == 'check_path_kind'
    assert not target.exists()


def test_sync_failure_keeps_completed_subtrees_and_partial_files(tmp_path, monkeypatch, capsys):
    save_config({'machines': {'cluster': PROFILE}, 'default_machine': 'cluster'})
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        if command[0] == 'ssh':
            source = '/selected/state/jobs' if len(calls) == 1 else '/selected/state/slurm'
            return subprocess.CompletedProcess(command, 0, metadata(source), '')
        if '/slurm/' in command[-2]:
            (Path(command[-1]) / 'partial.sh').write_text('partially copied')
            return subprocess.CompletedProcess(command, 23, '', 'retained-secret')
        return subprocess.CompletedProcess(command, 0, '', '')
    monkeypatch.setattr(subprocess, 'run', run)
    with pytest.raises(DiagnosticError) as stopped:
        sync_machine()
    effects = stopped.value.diagnostic.effects
    assert effects['sync_jobs'] == 'succeeded' and effects['sync_slurm'] == 'unknown' and effects['sync_out'] == 'not_started'
    assert (slurm_dir() / 'partial.sh').exists()
    assert len(calls) == 4 and 'Synced' not in capsys.readouterr().out


def test_remote_staging_failure_retains_rejected_receipt_without_dispatch(installations, monkeypatch):
    _, _, selected, _, calls, _, _ = installations
    original = subprocess.run
    def run(command, **kwargs):
        if command[0] == 'scp':
            calls.append(command)
            return subprocess.CompletedProcess(command, 255, '', 'retained-secret')
        return original(command, **kwargs)
    monkeypatch.setattr(subprocess, 'run', run)
    with pytest.raises(SubmissionError) as stopped:
        submit_jobs('study', bundle_path=selected)
    error = stopped.value
    assert error.receipt['state'] == 'rejected'
    assert all(job.get('id') is None for job in error.receipt['jobs'].values())
    assert error.diagnostic.stage == 'copy_files' and error.diagnostic.effects['file_transfer'] == 'unknown'
    assert not any(cmd[0] == 'sbatch' or '-MNf' in cmd for cmd in calls)
    assert len([cmd for cmd in calls if cmd[0] == 'scp']) == 1


@pytest.mark.parametrize('debug', [False, True])
def test_sync_cli_renders_once_or_preserves_native_chain(monkeypatch, capsys, debug):
    save_config({'machines': {'cluster': PROFILE}, 'default_machine': 'cluster'})
    native = FileNotFoundError(errno.ENOENT, 'retained-secret')
    def run(*a, **kw):
        raise native
    monkeypatch.setattr(subprocess, 'run', run)
    with pytest.raises(DiagnosticError if debug else SystemExit) as stopped:
        root.main(['sync', *(['--debug'] if debug else [])])
    if debug:
        assert stopped.value.__cause__ is native
    else:
        assert stopped.value.code == 1
        text = capsys.readouterr().err
        assert text.count('[command_unavailable]') == 1 and 'Next:' in text and 'retained-secret' not in text


def test_single_and_bundle_transfers_share_adapters(selected, sources, monkeypatch):
    date = datetime(2026, 11, 17)
    (jobs_dir() / 'study_20261117000000.json').write_text('{}')
    commands = []
    monkeypatch.setattr(subprocess, 'run', lambda cmd, **kw: commands.append(cmd) or subprocess.CompletedProcess(cmd, 0, '', ''))
    transfer_slurm_to_remote('a.sh', context=selected)
    transfer_bundle_to_remote('study', date, context=selected)
    assert [c[0] for c in commands] == ['ssh', 'scp', 'ssh', 'scp']
    assert commands[1][-1] == 'research-cluster:/selected/state/slurm/a.sh'
    assert commands[3][-1] == 'research-cluster:/selected/state/jobs/study_20261117000000.json'


def test_local_sync_destination_failure_preserves_cause_and_no_copy(selected, tmp_path, monkeypatch):
    target = tmp_path / 'file-instead-of-directory'
    target.write_text('keep this')
    calls = []
    monkeypatch.setattr(subprocess, 'run', lambda cmd, **kw: calls.append(cmd) or subprocess.CompletedProcess(
        cmd, 0, metadata('/selected/state/out'), ''))
    with pytest.raises(DiagnosticError) as stopped:
        pull_storage_directory(selected, 'out', target)
    assert isinstance(stopped.value.__cause__, FileExistsError)
    assert stopped.value.diagnostic.stage == 'prepare_local_directory'
    assert stopped.value.diagnostic.effects['file_transfer'] == 'not_started'
    assert len(calls) == 1 and target.read_text() == 'keep this'


@pytest.mark.parametrize('native', [TypeError('programming bug'), KeyboardInterrupt('interrupted')])
def test_copy_does_not_disguise_unexpected_errors_or_interrupts(selected, sources, monkeypatch, native):
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        if command[0] == 'scp':
            raise native
        return subprocess.CompletedProcess(command, 0, '', '')
    monkeypatch.setattr(subprocess, 'run', run)
    with pytest.raises(type(native)) as stopped:
        transfer_slurms_to_remote(['a.sh'], context=selected)
    assert stopped.value is native and len(calls) == 2


@pytest.mark.parametrize('output', [None, 'x' * 65537, '\ud800'])
def test_unusable_copy_output_retains_successful_command_effect(selected, sources, monkeypatch, output):
    def run(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, output if command[0] == 'scp' else '', '')
    monkeypatch.setattr(subprocess, 'run', run)
    with pytest.raises(DiagnosticError) as stopped:
        transfer_slurms_to_remote(['a.sh'], context=selected)
    assert stopped.value.diagnostic.code == 'protocol_invalid'
    assert stopped.value.diagnostic.effects['file_transfer'] == 'succeeded'


def test_remote_transfer_rejects_local_profile_without_commands(sources, monkeypatch):
    monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: pytest.fail('No local or alternate fallback'))
    with pytest.raises(InvalidRequestError):
        transfer_slurms_to_remote(['a.sh'], machine_config={'results_root': '/local/results'})


def test_sync_never_retrieves_application_subtrees(selected, tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: pytest.fail('Invalid subtree reached transport'))
    with pytest.raises(InvalidRequestError):
        pull_storage_directory(selected, '../results', tmp_path / 'destination')


@pytest.mark.parametrize('mode,expected', [('healthy', None), ('missing', 'resource_missing'),
    ('denied', 'resource_inaccessible'), ('wrong-kind', 'resource_inaccessible'),
    ('omitted', 'protocol_invalid'), ('extra', 'protocol_invalid'),
    ('swapped', 'protocol_invalid'), ('version-bool', 'protocol_invalid'),
    ('bad-shape', 'protocol_invalid'), ('ssh255', 'transport_failed')])
def test_required_paths_share_one_strict_batched_observation(selected, monkeypatch, mode, expected):
    import ast
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        query = ast.parse(kwargs['input']).body[-1].value.args[0].args[0]
        assert query.func.id == 'probe_paths'
        paths = ast.literal_eval(query.args[0])
        values = []
        for path in paths:
            file = path.endswith('/input.dat')
            state = 'missing' if file and mode == 'missing' else 'unavailable' if file and mode == 'denied' else 'exists'
            values.append(json.loads(metadata(path, state, 'file' if file or mode == 'wrong-kind' else 'directory',
                                             None)))
            if state != 'exists':
                values[-1].update(kind=None, errno=errno.ENOENT if state == 'missing' else errno.EACCES)
        response = {'version': 1, 'paths': values}
        if mode == 'omitted':
            response['paths'] = values[:-1]
        if mode == 'extra':
            response['paths'] = values + values[:1]
        if mode == 'swapped':
            response['paths'] = list(reversed(values))
        if mode == 'version-bool':
            response['version'] = True
        if mode == 'bad-shape':
            response = []
        return subprocess.CompletedProcess(command, 255 if mode == 'ssh255' else 0, json.dumps(response), 'retained-secret')
    monkeypatch.setattr(subprocess, 'run', run)
    job = {'working_directory': '.', 'script_args': {'source': 'input.dat'}, 'input_args': ['source']}
    if expected is None:
        selected.validate_jobs([job, job])
    else:
        with pytest.raises(DiagnosticError) as stopped:
            selected.validate_jobs([job, job])
        assert stopped.value.diagnostic.code == expected
        assert 'retained-secret' not in json.dumps(stopped.value.diagnostic.to_dict())
        if mode in ('missing', 'denied'):
            assert stopped.value.diagnostic.context['path'] == '/selected/results/input.dat'
    assert calls == [['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', 'research-cluster', 'python3 -B -']]


def test_required_local_missing_retains_native_cause_and_empty_checks_do_nothing(tmp_path, monkeypatch):
    ctx = resolve_execution_context('local', {'results_root': str(tmp_path)})
    monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: pytest.fail('Local metadata needs no process'))
    with pytest.raises(DiagnosticError) as stopped:
        ctx.validate_jobs([{'input_args': ['source'], 'script_args': {'source': 'absent'}}])
    assert stopped.value.diagnostic.code == 'resource_missing'
    assert isinstance(stopped.value.__cause__, FileNotFoundError)
    assert stopped.value.diagnostic.context['resolved_path'] == str(tmp_path / 'absent')
    ctx.validate_resolved_jobs([])


@pytest.mark.parametrize('operation', ['preview', 'submit'])
def test_preflight_transport_failure_stops_public_workflow_before_any_staging(monkeypatch, operation):
    from autoslurm import save_bundle, preview_bundle
    from autoslurm.storage import storage_root
    save_config({'machines': {'cluster': PROFILE}, 'default_machine': 'cluster'})
    selected = save_bundle({'fit': {'script': 'scientific-command', 'input_args': ['source'],
                                   'script_args': {'source': 'input.dat'}}}, 'study')
    calls = []
    monkeypatch.setattr(subprocess, 'run', lambda cmd, **kw: calls.append(cmd) or subprocess.CompletedProcess(
        cmd, 255, '', 'retained-secret'))
    with pytest.raises(DiagnosticError) as stopped:
        if operation == 'submit':
            submit_jobs('study', bundle_path=selected)
        else:
            preview_bundle(selected)
    assert stopped.value.diagnostic.code == 'transport_failed'
    assert not isinstance(stopped.value, SubmissionError)
    assert stopped.value.diagnostic.context['bundle_path'] == str(selected)
    assert calls == [['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', 'research-cluster', 'python3 -B -']]
    assert not list(slurm_dir().glob('*')) and not list((storage_root() / 'submissions').glob('*'))
