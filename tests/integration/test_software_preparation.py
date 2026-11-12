"""Portable preparation, release recovery and installed application execution."""

import json
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.local_processes
def test_real_offline_git_build_install_and_release_selection(tmp_path):
    fixture = Path(__file__).parents[1] / 'fixtures/software_release_roundtrip.py'
    response = subprocess.run([sys.executable, str(fixture), str(tmp_path / 'machine with spaces')],
                              capture_output=True, text=True, timeout=180)
    assert response.returncode == 0, response.stdout + response.stderr
    result = json.loads(response.stdout.splitlines()[-1])
    assert result['first'] != result['second']
    assert result['commits'][0] != result['commits'][1]
