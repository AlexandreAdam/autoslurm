"""Actual Git/venv metadata fixtures exercise the same standalone SSH payload."""

import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest


@pytest.mark.local_processes
def test_standalone_probe_compares_a_selected_virtual_environment_without_installation(tmp_path):
    fixture = tmp_path / "fixture.py"
    fixture.write_text(textwrap.dedent('''
        import json
        import os
        from pathlib import Path
        import subprocess
        import sys
        import venv
        from autoslurm import inspect_software, software_expectations, save_config

        root = Path(sys.argv[1])
        projects = root / "projects"
        checkout = projects / "science"
        runtime = root / "runtime"
        real_run = subprocess.run
        def git(*args):
            return real_run(["git", *map(str, args)], capture_output=True, text=True, check=True).stdout.strip()
        git("init", "-b", "main", checkout)
        git("-C", checkout, "config", "user.name", "Fixture")
        git("-C", checkout, "config", "user.email", "fixture@example.invalid")
        git("-C", checkout, "config", "commit.gpgsign", "false")
        (checkout / "science.py").write_text("raise RuntimeError('must not import science')")
        git("-C", checkout, "add", "science.py")
        git("-C", checkout, "commit", "-m", "fixture")
        commit = git("-C", checkout, "rev-parse", "HEAD")
        index_mtime = (checkout / ".git" / "index").stat().st_mtime_ns
        venv.EnvBuilder(with_pip=False).create(runtime)
        python = runtime / "bin" / "python"
        site = Path(real_run([str(python), "-B", "-c", "import sysconfig;print(sysconfig.get_paths()['purelib'])"], check=True, capture_output=True, text=True).stdout.strip())
        numpy = site / "numpy-2.0.dist-info"
        numpy.mkdir()
        (numpy / "METADATA").write_text("Metadata-Version: 2.1\\nName: numpy\\nVersion: 2.0\\n")
        application = site / "science_demo-1.2.dist-info"
        application.mkdir()
        (application / "METADATA").write_text("Metadata-Version: 2.1\\nName: science-demo\\nVersion: 1.2\\n")
        (application / "direct_url.json").write_text(json.dumps({"url": "https://code.example/science.git", "vcs_info": {"vcs": "git", "commit_id": commit}}))
        requirements = root / "requirements.txt"
        requirements.write_text("numpy>=1.24,<2\\npytest==100\\n")
        expected = software_expectations(requirements=requirements, package="science-demo", expected_version="1.2", expected_commit=commit)
        save_config({"machines": {"mock": {"software_root": str(projects), "venv_path": str(runtime), "ssh_alias": "fake-ssh"}}, "default_machine": "mock"})
        ssh_calls = []
        def ssh(command, **options):
            assert command[0] == "ssh", command
            ssh_calls.append(command)
            # A local stand-in for the remote system Python. It receives the
            # exact SSH stdin payload, with no package installed in that venv.
            return real_run([sys.executable, "-B", "-"], **options)
        subprocess.run = ssh
        report = inspect_software(machine="mock", project="science", expectations=expected)
        assert report["projects"][0]["dirty"] is False
        assert report["compatibility"]["state"] == "potential_problem"
        assert report["environment"]["prefix"] == str(runtime)
        assert any(row["name"] == "numpy" and row["state"] == "mismatch" for row in report["compatibility"]["checks"])
        assert not any(row["name"] == "pytest" for row in report["compatibility"]["checks"])
        assert (checkout / ".git" / "index").stat().st_mtime_ns == index_mtime
        (numpy / "METADATA").write_text("Metadata-Version: 2.1\\nName: numpy\\nVersion: 1.26.4\\n")
        compatible = inspect_software(expectations=expected)
        assert compatible["compatibility"]["state"] == "compatible"
        subproject = checkout / "python"
        subproject.mkdir()
        (application / "direct_url.json").write_text(json.dumps({"url": subproject.as_uri(), "dir_info": {"editable": True}}))
        editable = inspect_software(expectations=expected)
        assert editable["environment"]["packages"]["science-demo"]["source_commit"] == commit
        assert editable["compatibility"]["state"] == "compatible"
        (application / "direct_url.json").write_text(json.dumps({"url": "https://code.example/science.git", "vcs_info": {"commit_id": "a" * 40}}))
        assert inspect_software(expectations=expected)["compatibility"]["state"] == "potential_problem"
        save_config({"machines": {"mock": {"software_root": str(projects), "venv_path": str(root / "missing-env"), "ssh_alias": "fake-ssh"}}, "default_machine": "mock"})
        missing = inspect_software(expectations=expected)
        assert missing["environment"]["state"] == "unavailable"
        assert missing["compatibility"]["state"] == "unknown"
        assert len(ssh_calls) == 5
        print("read-only source and environment inspection verified")
    '''))
    environment = {**os.environ, "AUTOSLURM_STORAGE_ROOT": str(tmp_path / "state"),
                   "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    response = subprocess.run([sys.executable, str(fixture), str(tmp_path)],
                              capture_output=True, text=True, env=environment, timeout=40)
    assert response.returncode == 0, response.stderr
    assert "source and environment inspection verified" in response.stdout
