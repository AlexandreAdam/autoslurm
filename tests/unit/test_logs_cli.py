"""The logs command directly exposes shared execution evidence."""

import json
import re

import pytest

from autoslurm import inspect_logs
from autoslurm.apps import logs as cli, root
from autoslurm.storage import out_dir
from autoslurm import save_config
from tests.inspection_helpers import saved_run, mock_scheduler


def test_logs_without_args_shows_help_without_reading_cluster(capsys):
    cli.main([])
    assert 'usage: asl logs' in capsys.readouterr().out


def test_logs_default_reads_stdout_and_shows_failure_evidence(monkeypatch, capsys):
    path = saved_run()
    (out_dir() / 'sample-101.out').write_text('Traceback: scientific failure\n')
    mock_scheduler(monkeypatch, accounting='101|FAILED|1:0|NonZeroExitCode|101')
    root.main(['logs', '--bundle-file', str(path), '--job', 'sample'])
    text = capsys.readouterr().out
    assert 'scientific failure' in text and 'FAILED' in text
    assert 'exit=1:0' in text and 'NonZeroExitCode' in text
    assert 'stdout+stderr:' in text


def test_cli_json_and_python_share_log_stream_and_status_evidence(monkeypatch, capsys):
    path = saved_run()
    (out_dir() / 'sample-101.out').write_text('first\nlast\n')
    mock_scheduler(monkeypatch, accounting='101|COMPLETED|0:0|None|101')
    expected = inspect_logs(path, stream='stderr', tail=1)
    cli.main(['--bundle-file', str(path), '--stream', 'stderr', '--tail', '1', '--json'])
    actual = json.loads(capsys.readouterr().out)
    assert actual['logs'][0]['text'] == expected['logs'][0]['text'] == 'last'
    assert actual['logs'][0]['streams'] == ['stdout', 'stderr']
    assert actual['jobs'][0]['state'] == expected['jobs'][0]['state'] == 'COMPLETED'


def test_cached_cli_does_not_read_scheduler_or_source_logs(monkeypatch, capsys):
    path = saved_run()
    source = out_dir() / 'sample-101.out'
    source.write_text('old excerpt')
    mock_scheduler(monkeypatch)
    inspect_logs(path)
    source.write_text('new source text')
    monkeypatch.setattr('subprocess.run', lambda *a, **k: pytest.fail('Cached logs queried scheduler'))
    monkeypatch.setattr('autoslurm.log_files.read_log', lambda *a: pytest.fail('Cached logs read source'))
    cli.main(['--bundle-file', str(path), '--cached', '--json'])
    log = json.loads(capsys.readouterr().out)['logs'][0]
    assert log['text'] == 'old excerpt' and log['freshness'] == 'stale'


def test_truncation_and_missing_files_are_explicit(monkeypatch, capsys):
    path = saved_run()
    source = out_dir() / 'sample-101.out'
    source.write_text('first\nlast\n')
    mock_scheduler(monkeypatch)
    cli.main(['--bundle-file', str(path), '--tail', '1'])
    assert 'Excerpt truncated' in capsys.readouterr().out
    source.unlink()
    cli.main(['--bundle-file', str(path)])
    assert 'missing' in capsys.readouterr().out


@pytest.mark.parametrize('arguments', [['--max-bytes', '0'], ['--max-logs', '101'], ['--tail', '-1'], ['--task', '-1']])
def test_invalid_bounds_fail_before_scheduler_access(arguments, monkeypatch, capsys):
    path = saved_run()
    monkeypatch.setattr('subprocess.run', lambda *a, **k: pytest.fail('Invalid request queried scheduler'))
    with pytest.raises(SystemExit) as error:
        cli.main(['--bundle-file', str(path), *arguments])
    assert error.value.code == 1
    assert 'Traceback' not in capsys.readouterr().out


@pytest.fixture
def navigation_runs(monkeypatch):
    save_config({'machines': {'local': {}}, 'default_machine': 'local', 'bundle_filter_mode': 'all'})
    old = saved_run('study', '20250101000000', {'old': {'id': '100'}})
    new = saved_run('study', '20250102000000', {
        'plain': {'id': '102'}, 'array': {'id': '101', 'slurm': {'array': '0,2,4'}},
    })
    for name, text in [('old-100.out', 'old run'), ('plain-102.out', 'plain job'),
                       ('array-101_0.out', 'task zero'), ('array-101_2.out', 'task two'),
                       ('array-101_4.out', 'task four')]:
        (out_dir() / name).write_text(text)
    calls = mock_scheduler(monkeypatch, accounting='100|COMPLETED|0:0|None|100\n102|COMPLETED|0:0|None|102\n101_0|COMPLETED|0:0|None|101_0\n101_2|FAILED|1:0|NonZeroExitCode|101_2\n101_4|COMPLETED|0:0|None|101_4')
    return old, new, calls


@pytest.mark.parametrize('selector', [['1'], ['study'], ['--latest'], ['-l']])
def test_logs_bundle_navigation_matches_status_indices(navigation_runs, selector, capsys):
    from autoslurm.apps import status
    status.main(['1', '--json'])
    status_view = json.loads(capsys.readouterr().out)[0]
    cli.main([*selector, '--job', '2', '--json'])
    view = json.loads(capsys.readouterr().out)
    assert view['bundle_path'] == status_view['bundle_path'] == str(navigation_runs[1])
    assert view['logs'][0]['job_name'] == 'plain'
    assert view['logs'][0]['text'] == 'plain job'


@pytest.mark.parametrize('selection,task,text', [
    (['--job', '1', '--task', '2'], 2, 'task two'),
    (['--job', 'array', '--task', '4'], 4, 'task four'),
    (['--array', '--job', '2'], 2, 'task two'),
    (['--array', '2-4', '--job', '2'], 4, 'task four'),
    (['--array', '2-4', '--job', '3'], None, 'plain job'),
    (['--job', '1', '--array-task', '0'], 0, 'task zero'),
])
def test_logs_job_rows_and_array_rows_resolve_exact_task(navigation_runs, selection, task, text, capsys):
    cli.main(['1', *selection, '--json'])
    view = json.loads(capsys.readouterr().out)
    assert len(view['logs']) == 1
    assert view['logs'][0]['task_index'] == task
    assert view['logs'][0]['text'] == text


def test_array_filters_apply_before_file_limit(navigation_runs, capsys):
    cli.main(['1', '--job', 'array', '--array', '2-4', '--max-logs', '1', '--json'])
    logs = json.loads(capsys.readouterr().out)['logs']
    assert logs[0]['task_index'] == 2 and logs[0]['text'] == 'task two'
    assert logs[1] == {'state': 'omitted', 'count': 1, 'reason': 'Requested log-file bound reached.'}


def test_expanded_task_output_matches_status_row(navigation_runs, capsys):
    from autoslurm.apps import status
    status.main(['1', '--array'])
    status_text = capsys.readouterr().out
    selected_row = next(line for line in status_text.splitlines() if '101_2' in line)
    selected_row = re.sub(r'\x1b\[[0-9;]*m', '', selected_row)
    assert selected_row.split()[:3] == ['2', '101_2', 'array']
    cli.main(['1', '--array', '--job', '2'])
    text = capsys.readouterr().out
    assert 'array 101_2: FAILED' in text and 'task two' in text
    assert 'plain job' not in text and 'task zero' not in text


@pytest.mark.parametrize('selector', [['2', '1-2'], ['study', '--date', '2025-01-01'],
                                     ['study', '--year', '2025', '--month', '1', '--day', '1']])
def test_ranges_and_historical_selection_share_status_policy(navigation_runs, selector, capsys):
    cli.main([*selector, '--json'])
    result = json.loads(capsys.readouterr().out)
    if isinstance(result, list):
        assert [view['bundle_path'] for view in result] == [str(path) for path in navigation_runs[:2]]
        assert len(navigation_runs[2]) == 2  # One batched squeue/sacct pair.
    else:
        assert result['bundle_path'] == str(navigation_runs[0])
        assert result['logs'][0]['text'] == 'old run'


@pytest.mark.parametrize('args', [['1', '--latest'], ['0'], ['1', '--job', '9'],
    ['1', '--job', 'missing'], ['1-2', '--job', '1'], ['1', '--array', '4-2'],
    ['1', '--array', '--job', '2', '--task', '4'], ['1', '--array', '0', '--task', '2'],
    ['--task', '1'], ['--view', '1'], ['1', '--date', 'not-a-date']])
def test_invalid_navigation_stops_before_scheduler_access(navigation_runs, args, monkeypatch, capsys):
    monkeypatch.setattr('subprocess.run', lambda *a, **k: pytest.fail('Invalid navigation contacted scheduler'))
    with pytest.raises(SystemExit):
        cli.main(args)
    text = capsys.readouterr()
    assert 'Traceback' not in text.out + text.err


def test_cached_index_navigation_and_view_do_not_contact_cluster(navigation_runs, monkeypatch, capsys):
    cli.main(['1', '--job', '1', '--task', '2'])
    capsys.readouterr()
    monkeypatch.setattr('subprocess.run', lambda *a, **k: pytest.fail('Cached navigation ran commands'))
    monkeypatch.setattr('autoslurm.log_files.read_log', lambda *a: pytest.fail('Cached navigation read source logs'))
    cli.main(['1', '--array', '--job', '2', '--cached', '--json'])
    view = json.loads(capsys.readouterr().out)
    assert view['logs'][0]['text'] == 'task two' and view['logs'][0]['freshness'] == 'stale'
    cli.main(['--view', '--cached'])
    text = capsys.readouterr().out
    assert text.count('study') == 2


def test_empty_latest_selection_is_friendly(capsys):
    cli.main(['--latest'])
    assert 'No saved bundles found.' in capsys.readouterr().out
