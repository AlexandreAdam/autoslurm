"""Temporary local remotes exercise the actual Git pull and SSH stdin payload."""

import json
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.local_processes
def test_real_git_updates_one_existing_checkout_and_preserves_local_work(tmp_path):
    fixture = Path(__file__).parents[1] / 'fixtures/software_update_roundtrip.py'
    result = subprocess.run([sys.executable, str(fixture), str(tmp_path / 'machine')],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    evidence = json.loads(result.stdout)
    assert evidence['checkouts'] == 1 and evidence['before'] != evidence['after']
