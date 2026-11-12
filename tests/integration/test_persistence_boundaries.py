"""Behavior at local record and mocked transfer boundaries."""

from datetime import datetime
import json
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from autoslurm import save_bundle, schedule_job
from autoslurm.storage import config_file_path, jobs_dir
from autoslurm.utils import save_config, update_job_metadata


def test_failed_configuration_serialization_keeps_previous_record():
    config = {"machines": {"local": {}}, "default_machine": "local"}
    save_config(config)
    before = config_file_path().read_bytes()
    config["machines"]["local"]["bad"] = object()
    with pytest.raises(TypeError):
        save_config(config)
    assert config_file_path().read_bytes() == before


def test_failed_metadata_update_keeps_previous_bundle():
    path = save_bundle({"sample": {"script": "science"}}, "study")
    before = path.read_bytes()
    date = datetime.strptime(path.stem.rsplit("_", 1)[-1], "%Y%m%d%H%M%S")
    with pytest.raises(TypeError):
        update_job_metadata("study", date, "sample", {"bad": object()})
    assert path.read_bytes() == before


def test_failed_new_snapshot_is_not_visible():
    with pytest.raises(TypeError):
        save_bundle({"sample": {"script": "science", "bad": object()}}, "study")
    assert list(jobs_dir().glob("*.json")) == []


def test_repeated_same_second_scheduling_never_clobbers(monkeypatch):
    class FixedTime(datetime):
        @classmethod
        def now(cls):
            return cls(2026, 11, 12, 12, 0, 0)

    monkeypatch.setattr("autoslurm.save_load_jobs.datetime", FixedTime)
    paths = []
    for number in range(5):
        _, path = schedule_job({"name": "sample", "script": f"science-{number}"}, "study")
        paths.append(path)
    assert len(set(paths)) == 5
    assert [json.loads(p.read_text())["sample"]["script"] for p in paths] == [f"science-{n}" for n in range(5)]


def test_transfer_explicit_profile_is_not_replaced_by_discovery(monkeypatch):
    from autoslurm.save_load_jobs import transfer_slurms_to_remote

    monkeypatch.setattr("autoslurm.file_transfer.load_config", lambda: pytest.fail("Explicit profile must not load configuration"))
    commands = []
    monkeypatch.setattr("subprocess.run", lambda cmd, **kw: commands.append(cmd) or CompletedProcess(cmd, 0, "", ""))
    transfer_slurms_to_remote(["sample.sh"], machine_name="recorded", machine_config={"hostname": "saved-host", "path": "/saved-root"})
    assert commands[-1][-1] == "saved-host:/saved-root/slurm/"


def test_identity_file_with_spaces_is_one_ssh_and_scp_argument(monkeypatch):
    from autoslurm.utils import ssh_host_from_config, scp_host_and_keypath_from_config
    import shlex

    machine = {"username": "scientist", "hosturl": "cluster", "key_path": "/keys/science key"}
    assert shlex.split(ssh_host_from_config(machine)) == ["-i", "/keys/science key", "scientist@cluster"]
    host, key_options = scp_host_and_keypath_from_config(machine)
    assert host == "scientist@cluster"
    assert shlex.split(key_options) == ["-i", "/keys/science key"]


def test_sync_transport_failure_is_not_reported_as_missing(monkeypatch, capsys):
    from autoslurm.sync import sync_machine

    save_config({"machines": {"remote": {"hostname": "cluster", "path": "/prepared", "env_command": "true", "slurm_account": "test"}}, "default_machine": "remote"})
    monkeypatch.setattr("subprocess.run", lambda cmd, **kw: CompletedProcess(cmd, 255, "", "connection lost"))
    with pytest.raises(RuntimeError, match="connection lost"):
        sync_machine()
    assert "Synced" not in capsys.readouterr().out


@pytest.mark.parametrize("fault", ["flush", "replace"])
def test_failed_record_publication_keeps_old_bytes_and_cleans_temporary(monkeypatch, tmp_path, fault):
    from autoslurm.record_files import atomic_json

    path = tmp_path / "records" / "record.json"
    atomic_json(path, {"old": "evidence"})
    before = path.read_bytes()
    def fail(*args, **kwargs):
        raise OSError("disk failure")
    monkeypatch.setattr("autoslurm.record_files.os." + ("fsync" if fault == "flush" else "replace"), fail)
    with pytest.raises(OSError, match="disk failure"):
        atomic_json(path, {"new": "evidence"})
    assert path.read_bytes() == before
    assert sorted(path.parent.iterdir()) == [path]


def test_interrupted_serialization_keeps_old_record_and_cleans_temporary(monkeypatch, tmp_path):
    from autoslurm.record_files import atomic_json

    path = tmp_path / "records" / "record.json"
    atomic_json(path, {"old": "evidence"})
    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt()
    monkeypatch.setattr("autoslurm.record_files.json.dump", interrupt)
    with pytest.raises(KeyboardInterrupt):
        atomic_json(path, {"new": "evidence"})
    assert json.loads(path.read_text()) == {"old": "evidence"}
    assert sorted(path.parent.iterdir()) == [path]


def test_exclusive_publication_preserves_existing_destination(tmp_path):
    from autoslurm.record_files import atomic_json

    path = tmp_path / "records" / "record.json"
    atomic_json(path, {"old": "evidence"}, exclusive=True)
    with pytest.raises(FileExistsError):
        atomic_json(path, {"new": "evidence"}, exclusive=True)
    assert json.loads(path.read_text()) == {"old": "evidence"}
    assert sorted(path.parent.iterdir()) == [path]


def test_directory_sync_failure_retains_complete_published_record(monkeypatch, tmp_path):
    from autoslurm import record_files

    path = tmp_path / "records" / "record.json"
    calls = []
    def sync(fd):
        calls.append(fd)
        if len(calls) == 2:
            raise OSError("directory sync failed")
    monkeypatch.setattr(record_files.os, "fsync", sync)
    with pytest.raises(OSError, match="directory sync failed"):
        record_files.atomic_json(path, {"complete": True}, exclusive=True)
    assert json.loads(path.read_text()) == {"complete": True}
    assert sorted(path.parent.iterdir()) == [path]


def test_failed_multi_job_append_does_not_publish_half_a_batch():
    path = save_bundle({"original": {"script": "science"}}, "study")
    before = path.read_bytes()
    with pytest.raises(TypeError):
        save_bundle({"first": {"script": "science"}, "second": {"script": "science", "bad": object()}}, "study", append=True)
    assert path.read_bytes() == before
    assert list(jobs_dir().glob("*.json")) == [path]


def test_empty_append_has_an_exact_saved_path():
    path = save_bundle({}, "study", append=True)
    assert json.loads(path.read_text()) == {}
    assert save_bundle({}, "study", append=True) == path


def test_blocked_snapshot_directory_raises_without_collision_retry(monkeypatch, tmp_path):
    from autoslurm import save_load_jobs

    blocked = tmp_path / "not-a-directory"
    blocked.write_text("unrelated")
    monkeypatch.setattr(save_load_jobs, "jobs_dir", lambda: blocked)
    with pytest.raises(FileExistsError):
        save_bundle({"sample": {"script": "science"}}, "study")
    assert blocked.read_text() == "unrelated"


def test_snapshot_publication_race_preserves_competing_record(monkeypatch):
    from autoslurm import save_load_jobs
    from autoslurm.record_files import atomic_json

    competitor = []
    def racing_write(path, data, **kwargs):
        if not competitor:
            atomic_json(path, {"competitor": {"script": "other-science"}}, exclusive=True)
            competitor.append(path)
        return atomic_json(path, data, **kwargs)
    monkeypatch.setattr(save_load_jobs, "atomic_json", racing_write)
    saved = save_bundle({"sample": {"script": "science"}}, "study")
    assert saved != competitor[0]
    assert json.loads(competitor[0].read_text()) == {"competitor": {"script": "other-science"}}
    assert json.loads(saved.read_text())["sample"]["script"] == "science"


def test_local_persistence_selection_and_profile_reads_have_no_process_effects(monkeypatch):
    from autoslurm import load_bundle_from_path, select_bundle_snapshot, list_saved_bundles
    from autoslurm.configuration import load_config

    monkeypatch.setattr("subprocess.run", lambda *a, **k: pytest.fail("Local records must not start a process"))
    save_config({"machines": {"remote": {"hostname": "cluster"}}, "default_machine": "remote"})
    path = save_bundle({"sample": {"script": "science"}}, "study")
    selected = select_bundle_snapshot("study", bundle_path=path)
    assert selected["path"] == path
    assert load_bundle_from_path(path)[0][0]["name"] == "sample"
    assert list_saved_bundles()[0]["path"] == path
    assert load_config()["default_machine"] == "remote"


@pytest.mark.parametrize("failure_stage", ["mkdir", "scp"])
def test_transfer_failure_is_reported_once_without_retry(monkeypatch, failure_stage):
    from autoslurm.file_transfer import transfer_slurms_to_remote

    commands = []
    def run(command, **kwargs):
        commands.append(command)
        bad = command[0] == ("ssh" if failure_stage == "mkdir" else "scp")
        return CompletedProcess(command, 1 if bad else 0, "", "staging failed" if bad else "")
    monkeypatch.setattr("subprocess.run", run)
    with pytest.raises((ValueError, RuntimeError), match="staging failed"):
        transfer_slurms_to_remote(["a.sh", "b.sh"], machine_config={"hostname": "cluster", "path": "/prepared"})
    assert len(commands) == (1 if failure_stage == "mkdir" else 2)


def test_each_transfer_prepares_directories_and_batches_scripts(monkeypatch):
    from autoslurm.file_transfer import transfer_slurms_to_remote
    from autoslurm.execution import resolve_execution_context
    import shlex

    machine = {"username": "scientist", "hosturl": "cluster", "key_path": "/keys/science key", "path": "/prepared state"}
    context = resolve_execution_context("saved", machine)
    monkeypatch.setattr("autoslurm.file_transfer.load_config", lambda: pytest.fail("Saved context must not reload profiles"))
    commands = []
    monkeypatch.setattr("subprocess.run", lambda cmd, **kw: commands.append(cmd) or CompletedProcess(cmd, 0, "", ""))
    for _ in range(2):
        transfer_slurms_to_remote(["a.sh", "b.sh"], context=context)
    assert [c[0] for c in commands] == ["ssh", "scp", "ssh", "scp"]
    assert commands[0][1:3] == ["-i", "/keys/science key"]
    assert shlex.split(commands[0][-1]) == ["mkdir", "-p", "/prepared state/slurm", "/prepared state/out"]
    assert commands[1][1:3] == ["-i", "/keys/science key"]
    assert [Path(value).name for value in commands[1][3:5]] == ["a.sh", "b.sh"]
    assert commands[1][-1] == "scientist@cluster:/prepared state/slurm/"


def test_empty_transfer_has_no_profile_or_process_effect(monkeypatch):
    from autoslurm.file_transfer import transfer_slurms_to_remote

    monkeypatch.setattr("autoslurm.file_transfer.load_config", lambda: pytest.fail("No profile read for empty transfer"))
    monkeypatch.setattr("subprocess.run", lambda *a, **k: pytest.fail("No process for empty transfer"))
    transfer_slurms_to_remote([])


def test_sync_copy_failure_stops_without_success_or_retry(monkeypatch, capsys):
    from autoslurm.sync import sync_machine

    save_config({"machines": {"remote": {"hostname": "cluster", "path": "/prepared", "env_command": "true", "slurm_account": "test"}}, "default_machine": "remote"})
    commands = []
    def run(command, **kwargs):
        commands.append(command)
        return CompletedProcess(command, 23 if command[0] == "rsync" else 0, "", "partial copy")
    monkeypatch.setattr("subprocess.run", run)
    with pytest.raises(RuntimeError, match="partial copy"):
        sync_machine()
    assert [c[0] for c in commands] == ["ssh", "rsync"]
    assert "Synced" not in capsys.readouterr().out


def test_invalid_ssh_profile_still_cleans_session_directory(monkeypatch, tmp_path):
    from autoslurm.run_slurm import ssh_submission_session

    session = tmp_path / "session"
    session.mkdir()
    monkeypatch.setattr("autoslurm.run_slurm.tempfile.mkdtemp", lambda **kw: str(session))
    monkeypatch.setattr("subprocess.run", lambda *a, **k: pytest.fail("Invalid profile must fail before a process"))
    with pytest.raises(AttributeError, match="username"):
        with ssh_submission_session({"hosturl": "cluster"}, "invalid"):
            pytest.fail("Invalid profile must not start a session")
    assert not session.exists()
