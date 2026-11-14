"""Snapshot discovery preserves uncertainty and cannot redirect failed selections."""

import errno
from datetime import datetime, timezone
import json
import os
from pathlib import Path

import pytest

from autoslurm import (SelectionError, all_bundle_snapshots, bundle_snapshot_state,
                      bundle_snapshots, execute_acp, get_bundle_filter_mode, list_bundles,
                      list_runs, list_saved_bundles, nearest_bundle_filename, save_bundle,
                      select_bundle_snapshot, set_bundle_filter_mode)
from autoslurm import bundle_selection as selection
from autoslurm.apps import clean, filter as filter_cli, inspect, logs, root, status, submit
from autoslurm.config import save_config
from autoslurm.errors import ConfigurationError, DiagnosticError, selection_failure
from autoslurm.storage import config_file_path, jobs_dir, set_storage_root


def write(name, payload):
    path = jobs_dir() / name
    path.write_text(json.dumps(payload))
    return path


def profile(mode='all'):
    save_config({'machines': {'mock': {'env_command': 'true'}},
                 'default_machine': 'mock', 'bundle_filter_mode': mode})


@pytest.mark.parametrize('arguments,field', [
    ({}, 'selector'), ({'latest': True, 'name': 'study'}, 'selector'),
    ({'latest': True, 'index': 1}, 'selector'),
    ({'bundle_path': 'specific.json', 'index': 1}, 'selector'),
    ({'index': True}, 'index'), ({'index': '1'}, 'index'), ({'index': 0}, 'index'),
    ({'index': -1}, 'index'), ({'latest': 1}, 'latest/prefer_draft'),
    ({'name': []}, 'name'), ({'name': ''}, 'name'),
    ({'bundle_path': ''}, 'bundle_path'), ({'bundle_path': []}, 'bundle_path'),
    ({'name': 'study', 'desired_date': 'today'}, 'desired_date'),
    ({'name': 'study', 'desired_date': datetime.now(timezone.utc)}, 'desired_date'),
])
def test_invalid_selectors_fail_before_any_discovery_or_write(arguments, field, monkeypatch):
    monkeypatch.setattr(selection, '_snapshot_files', lambda: pytest.fail('Invalid selector discovered files'))
    with pytest.raises(SelectionError) as stopped:
        select_bundle_snapshot(**arguments)
    error = stopped.value
    assert isinstance(error, ValueError) and isinstance(error, DiagnosticError)
    facts = error.diagnostic.to_dict()
    assert facts['code'] == 'invalid_argument' and facts['operation'] == 'selection'
    assert facts['context']['field'] == field and facts['effects'] == {} and facts['next_action']
    assert not list(jobs_dir().glob('*.json'))


def test_absent_storage_is_an_empty_observation_and_selection_does_not_create_it(tmp_path):
    missing = tmp_path / 'no-state'
    set_storage_root(missing)
    assert get_bundle_filter_mode() == 'active'
    assert all_bundle_snapshots() == [] and list_saved_bundles() == [] and list_bundles('study') == []
    with pytest.raises(SelectionError) as stopped:
        nearest_bundle_filename('study')
    assert stopped.value.diagnostic.code == 'resource_missing'
    assert not missing.exists()


def test_missing_exact_path_has_native_cause_and_no_alternative_selection():
    healthy = write('study_20261114000000.json', {'fit': {'script': 'science'}})
    missing = jobs_dir() / 'study_20261115000000.json'
    before = healthy.read_bytes()
    with pytest.raises(SelectionError) as stopped:
        select_bundle_snapshot(bundle_path=missing)
    assert stopped.value.diagnostic.code == 'resource_missing'
    assert stopped.value.diagnostic.context['bundle_path'] == str(missing)
    assert isinstance(stopped.value.__cause__, FileNotFoundError)
    assert healthy.read_bytes() == before


def test_discovery_denial_is_not_an_empty_directory_or_a_missing_target(monkeypatch):
    path = jobs_dir()
    original = PermissionError(errno.EACCES, 'Access denied', str(path))
    monkeypatch.setattr(selection.os, 'scandir', lambda *a: (_ for _ in ()).throw(original))
    with pytest.raises(SelectionError) as stopped:
        select_bundle_snapshot('study', prefer_draft=False)
    assert stopped.value.__cause__ is original
    assert stopped.value.diagnostic.code == 'resource_inaccessible'
    assert stopped.value.diagnostic.cause.errno == errno.EACCES
    assert stopped.value.diagnostic.context['path'] == str(path)


@pytest.mark.parametrize('raw', [b'{"secret":"retained-secret",', b'\xff', b'[]'])
def test_corrupt_entries_retain_unknown_counts_and_healthy_neighbours(raw):
    good = write('good_20261114000000.json', {})
    bad = jobs_dir() / 'bad_20261115000000.json'
    bad.write_bytes(raw)
    rows = {entry['bundle']: entry for entry in list_saved_bundles()}
    assert rows['good']['jobs'] == [] and rows['good']['job_count'] == 0
    assert rows['good']['diagnostic'] is None
    failure = rows['bad']
    assert failure['state'] == 'broken' and failure['jobs'] is None
    assert failure['job_count'] is None and failure['submitted_count'] is None
    assert failure['diagnostic']['code'] == 'record_invalid'
    assert 'retained-secret' not in json.dumps(failure['diagnostic'])
    assert bad.read_bytes() == raw and good.exists()


def test_unreadable_entry_is_not_broken_or_empty_and_keeps_safe_errno(monkeypatch):
    good = write('good_20261114000000.json', {'fit': {'script': 'science'}})
    bad = write('bad_20261115000000.json', {'fit': {'script': 'science', 'id': '123'}})
    original = os.open
    failure = PermissionError(errno.EACCES, 'Access denied', str(bad))
    def denied(path, *args, **kwargs):
        if Path(path) == bad: raise failure
        return original(path, *args, **kwargs)
    monkeypatch.setattr(selection.os, 'open', denied)
    rows = {entry['bundle']: entry for entry in all_bundle_snapshots()}
    assert rows['good']['state'] == 'ready_to_go'
    assert rows['bad']['state'] == 'unavailable'
    assert rows['bad']['jobs'] is None and rows['bad']['submitted_count'] is None
    assert rows['bad']['diagnostic']['cause']['errno'] == errno.EACCES
    with pytest.raises(SelectionError) as stopped:
        bundle_snapshot_state(bad, strict=True)
    assert stopped.value.__cause__ is failure and good.exists() and bad.exists()


def test_disappearing_entry_is_missing_without_removing_healthy_rows(monkeypatch):
    good = write('good_20261114000000.json', {'fit': {}})
    vanished = jobs_dir() / 'gone_20261115000000.json'
    monkeypatch.setattr(selection, '_snapshot_files', lambda: [good, vanished])
    rows = {entry['bundle']: entry for entry in all_bundle_snapshots()}
    assert rows['good']['job_count'] == 1
    assert rows['gone']['state'] == 'missing' and rows['gone']['jobs'] is None
    assert rows['gone']['diagnostic']['code'] == 'resource_missing'


@pytest.mark.parametrize('kind', ['directory', 'dangling', 'fifo'])
def test_nonregular_entries_never_become_absent_or_blocking_reads(kind):
    path = jobs_dir() / 'special_20261114000000.json'
    if kind == 'directory': path.mkdir()
    elif kind == 'dangling': path.symlink_to(jobs_dir() / 'absent.json')
    else: os.mkfifo(path)
    row = all_bundle_snapshots()[0]
    assert row['state'] == 'unavailable' and row['jobs'] is None
    assert row['diagnostic']['code'] == 'resource_inaccessible'
    with pytest.raises(SelectionError) as stopped:
        select_bundle_snapshot(bundle_path=path)
    assert stopped.value.diagnostic.code == 'resource_inaccessible'


def test_graph_failure_keeps_known_count_id_count_and_cycle_cause():
    path = write('study_20261114000000.json', {
        'A': {'script': 'science', 'id': '123', 'dependencies': ['B']},
        'B': {'script': 'science', 'dependencies': ['A']}})
    row = bundle_snapshot_state(path)
    assert row['state'] == 'broken' and row['job_count'] == 2 and row['submitted_count'] == 1
    assert row['jobs'] == ['A', 'B'] and row['diagnostic']['context']['field'] == 'dependencies'
    assert row['diagnostic']['cause']['kind'] == 'CycleError'
    with pytest.raises(SelectionError) as stopped:
        bundle_snapshot_state(path, strict=True)
    assert stopped.value.__cause__.__cause__.__class__.__name__ == 'CycleError'


@pytest.mark.parametrize('latest', [False, True])
def test_draft_preference_cannot_bypass_a_newer_broken_snapshot(latest):
    profile('active')
    write('study_20261113000000.json', {'fit': {'script': 'science'}})
    write('other_20261112000000.json', {'fit': {'script': 'science'}})
    newest = jobs_dir() / 'study_20261114000000.json'
    newest.write_text('{')
    selected = select_bundle_snapshot(latest=True) if latest else select_bundle_snapshot('study')
    assert selected['path'] == newest and selected['diagnostic']['code'] == 'record_invalid'
    assert bundle_snapshots()[0]['path'] == newest


def test_active_filter_keeps_latest_error_beside_submitted_history():
    profile('active')
    old = write('study_20261113000000.json', {'fit': {'script': 'science', 'id': '123'}})
    latest = jobs_dir() / 'study_20261114000000.json'
    latest.write_text('{')
    rows = bundle_snapshots()
    assert [row['path'] for row in rows] == [latest, old]
    assert rows[0]['state'] == 'broken' and rows[1]['state'] == 'active'
    assert select_bundle_snapshot(index=1)['path'] == latest
    assert select_bundle_snapshot(index=2)['path'] == old


def test_equal_timestamps_keep_index_order_independent_of_directory_order(monkeypatch):
    a = write('a_20261114000000.json', {'fit': {}})
    z = write('z_20261114000000.json', {'fit': {}})
    monkeypatch.setattr(selection, '_snapshot_files', lambda: [a, z])
    first = select_bundle_snapshot(index=1)['path']
    monkeypatch.setattr(selection, '_snapshot_files', lambda: [z, a])
    assert select_bundle_snapshot(index=1)['path'] == first == z


@pytest.mark.parametrize('mode', ['unknown', None, [], 1])
def test_invalid_stored_filter_is_not_silently_active(mode):
    config_file_path().write_text(json.dumps({'machines': {'mock': {}}, 'bundle_filter_mode': mode}))
    before = config_file_path().read_bytes()
    with pytest.raises(ConfigurationError) as stopped:
        get_bundle_filter_mode()
    assert stopped.value.diagnostic.context['field'] == 'bundle_filter_mode'
    assert stopped.value.diagnostic.context['path'] == str(config_file_path())
    assert config_file_path().read_bytes() == before


@pytest.mark.parametrize('problem', ['corrupt', 'denied'])
def test_config_failure_cannot_change_filter_or_records(problem, monkeypatch):
    profile('all')
    before = config_file_path().read_bytes()
    if problem == 'corrupt':
        config_file_path().write_text('{')
        before = b'{'
    else:
        def denied(*args, **kwargs): raise PermissionError(errno.EACCES, 'denied')
        monkeypatch.setattr('autoslurm.config.open', denied, raising=False)
    for call in (get_bundle_filter_mode, lambda: set_bundle_filter_mode('active')):
        with pytest.raises(ConfigurationError): call()
    assert config_file_path().read_bytes() == before


@pytest.mark.parametrize('kind', ['append', 'new'])
def test_storage_failure_never_triggers_new_snapshot_fallback(kind, monkeypatch):
    def denied(*a): raise PermissionError(errno.EACCES, 'denied')
    monkeypatch.setattr(selection.os, 'scandir', denied)
    with pytest.raises(SelectionError) as stopped:
        save_bundle({'fit': {'script': 'science'}}, 'study', append=kind == 'append')
    assert stopped.value.diagnostic.code == 'resource_inaccessible'
    assert not os.listdir(jobs_dir())


def test_unknown_counts_are_excluded_from_automatic_cleanup(capsys):
    bad = jobs_dir() / 'study_20261113000000.json'
    bad.write_text('{')
    newer = jobs_dir() / 'study_20261114000000.json'
    newer.write_text('{')
    clean.main(['--scope', 'unsubmitted', '--yes'])
    assert 'No matching' in capsys.readouterr().out and bad.exists() and newer.exists()
    clean.main(['--scope', 'inactive', '--yes'])
    assert bad.exists() and newer.exists()


def test_public_agent_discovery_keeps_the_same_per_entry_diagnostic():
    bad = jobs_dir() / 'study_20261114000000.json'
    bad.write_text('{')
    direct = list_saved_bundles(bundle_name='study')[0]['diagnostic']
    assert list_runs('study')[0]['diagnostic'] == direct
    assert list_bundles('study')[0]['jobs'] is None
    response = execute_acp({'action': 'list_experiments', 'bundle': 'study'})
    assert response['status'] == 'success'
    assert response['result'][0]['diagnostic'] == direct and response['result'][0]['state'] == 'broken'


@pytest.mark.parametrize('invoke', [lambda args: submit.main(args), lambda args: root.main(['submit', *args])])
def test_submit_never_connects_or_falls_back_after_newest_record_error(invoke, monkeypatch, capsys):
    write('study_20261113000000.json', {'fit': {'script': 'science'}})
    bad = jobs_dir() / 'study_20261114000000.json'
    bad.write_text('{"secret":"retained-secret",')
    before = bad.read_bytes()
    monkeypatch.setattr(submit, 'machine_config', lambda *a, **kw: pytest.fail('Do not select/connect after invalid record'))
    monkeypatch.setattr(submit, 'submit_jobs', lambda *a, **kw: pytest.fail('Never submit an older draft'))
    with pytest.raises(SystemExit) as stopped:
        invoke(['study'])
    assert stopped.value.code == 1
    output = capsys.readouterr()
    assert output.out == '' and 'record_invalid' in output.err and str(bad) in output.err
    assert 'retained-secret' not in output.err and bad.read_bytes() == before
    with pytest.raises(SelectionError) as debug:
        invoke(['study', '--debug'])
    assert isinstance(debug.value.__cause__, json.JSONDecodeError)


@pytest.mark.parametrize('invoke,args', [(status.main, []), (inspect.main, ['--latest']), (logs.main, ['--latest']),
                                        (lambda args: root.main(['stat', *args]), []),
                                        (lambda args: root.main(['context', *args]), ['--latest'])])
def test_shared_cli_config_failure_has_text_json_and_original_debug(invoke, args, capsys):
    config_file_path().write_text('{')
    with pytest.raises(SystemExit) as stopped:
        invoke([*args, '--cached'])
    assert stopped.value.code == 1 and 'record_invalid' in capsys.readouterr().err
    with pytest.raises(SystemExit) as stopped:
        invoke([*args, '--cached', '--json'])
    assert stopped.value.code == 1
    output = capsys.readouterr()
    assert output.err == '' and json.loads(output.out)['diagnostic']['code'] == 'record_invalid'
    with pytest.raises(ConfigurationError) as debug:
        invoke([*args, '--cached', '--debug'])
    assert isinstance(debug.value.__cause__, json.JSONDecodeError)


def test_filter_cli_and_acp_keep_expected_configuration_diagnosis(capsys):
    config_file_path().write_text('{')
    with pytest.raises(SystemExit) as stopped:
        filter_cli.main([])
    assert stopped.value.code == 1 and 'record_invalid' in capsys.readouterr().err
    with pytest.raises(ConfigurationError): filter_cli.main(['--debug'])
    result = execute_acp({'action': 'inspect_experiments', 'bundle': 'study'})
    # No matching file is a selection failure, independently of invalid config.
    assert result['status'] == 'error' and result['diagnostic']['code'] == 'resource_missing'


@pytest.mark.parametrize('bug', [ValueError('bug'), TypeError('bug'), KeyError('bug')])
def test_unexpected_bugs_propagate_from_graph_analysis_and_cli(bug, monkeypatch):
    write('study_20261114000000.json', {'fit': {}})
    def fail(*a, **kw): raise bug
    monkeypatch.setattr(selection, 'dependency_graph', fail)
    with pytest.raises(type(bug)) as stopped: all_bundle_snapshots()
    assert stopped.value is bug
    with pytest.raises(type(bug)) as stopped: submit.main(['study'])
    assert stopped.value is bug
    monkeypatch.setattr(selection, 'load_config', fail)
    with pytest.raises(type(bug)) as stopped: get_bundle_filter_mode()
    assert stopped.value is bug


def test_selection_constructor_is_pure_and_unknown_problem_stays_a_bug():
    diagnostic = selection_failure(stage='select_snapshot', problem='missing', context={'bundle': 'study'})
    assert diagnostic.code == 'resource_missing' and diagnostic.effects == {}
    with pytest.raises(ValueError): selection_failure(stage='select_snapshot', problem='guess')


def test_filename_only_selection_retains_corrupt_exact_identity(monkeypatch):
    older = write('study_20261113000000.json', {'fit': {}})
    latest = jobs_dir() / 'study_20261114000000.json'
    latest.write_text('{')
    monkeypatch.setattr(selection, '_read_snapshot', lambda *a: pytest.fail('Filename selection read payload'))
    assert nearest_bundle_filename('study')[0] == latest.name
    assert select_bundle_snapshot(bundle_path=latest)['path'] == latest
    assert older.exists()


def test_unversioned_external_file_uses_mtime_without_rewriting(tmp_path):
    path = tmp_path / 'external.json'
    path.write_text('{}')
    before = path.read_bytes()
    selected = select_bundle_snapshot('study', bundle_path=path)
    assert selected['date'] == datetime.fromtimestamp(path.stat().st_mtime)
    assert bundle_snapshot_state(path, strict=True)['job_count'] == 0
    assert path.read_bytes() == before


def test_index_out_of_range_never_selects_neighbour():
    path = write('study_20261114000000.json', {'fit': {}})
    with pytest.raises(SelectionError) as stopped: select_bundle_snapshot(index=2)
    assert stopped.value.diagnostic.context['field'] == 'index' and path.exists()


@pytest.mark.parametrize('value', ['other', None, 1])
def test_invalid_filter_update_preserves_exact_config(value):
    profile('all')
    before = config_file_path().read_bytes()
    with pytest.raises(ConfigurationError) as stopped: set_bundle_filter_mode(value)
    assert stopped.value.diagnostic.context['field'] == 'bundle_filter_mode'
    assert config_file_path().read_bytes() == before


def test_dangling_jobs_directory_does_not_look_like_missing_storage():
    directory = jobs_dir()
    directory.rmdir()
    directory.symlink_to(directory.parent / 'absent')
    with pytest.raises(SelectionError) as stopped: all_bundle_snapshots()
    assert stopped.value.diagnostic.code == 'resource_inaccessible' and directory.is_symlink()
