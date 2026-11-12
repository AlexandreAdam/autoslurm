"""The logs command directly exposes shared execution evidence."""

import json

import pytest

from autoslurm import inspect_logs
from autoslurm.apps import logs as cli, root
from autoslurm.storage import out_dir
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
