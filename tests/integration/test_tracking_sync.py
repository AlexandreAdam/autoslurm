"""Two installation views, differing profile names, no real SSH or scheduler."""

import contextlib
import copy
import io
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from autoslurm import (save_bundle, submit_jobs, save_config, inspect_bundle,
                      load_submission, refresh_submission, fetch_run)
from autoslurm.apps import cancel
from autoslurm.errors import DiagnosticError
from autoslurm.execution import EXECUTION_METADATA_KEY
from autoslurm.storage import storage_root, set_storage_root
from autoslurm.submission import SUBMISSION_METADATA_KEY
from autoslurm.sync import sync_machine
from tests.inspection_helpers import remote_observation
from tests.integration.test_execution_tracking import installations


@pytest.fixture
def native(tmp_path, monkeypatch):
    laptop = storage_root()
    cluster = tmp_path / "native cluster"
    set_storage_root(cluster)
    save_config({"machines": {"rusty-local": {"env_command": "true"}}, "default_machine": "rusty-local"})
    calls = []
    mode = {"broken_receipt": False, "cancel": False}
    data = {"queue": "101_1|RUNNING|10:00|None\n102|PENDING|15:00|Dependency",
            "accounting": "101_0|COMPLETED|0:0|None"}

    def run(command, **kwargs):
        calls.append(command)
        result = lambda stdout="", code=0: subprocess.CompletedProcess(command, code, stdout, "")
        if command[0] == "bash":
            return result()
        if command[0] == "sbatch":
            identity = "101" if Path(command[-1]).name.startswith("stars_") else "102"
            return result(identity if "--parsable" in command else "Submitted batch job " + identity)
        if command[0] == "squeue":
            assert storage_root() == cluster, "Laptop attempted local Slurm"
            return result(data["queue"])
        if command[0] == "sacct":
            assert storage_root() == cluster, "Laptop attempted local Slurm"
            return result(data["accounting"])
        if command[0] == "rsync":
            source = Path(command[-2].split(":", 1)[1])
            target = Path(command[-1])
            target.mkdir(parents=True, exist_ok=True)
            for path in source.iterdir():
                destination = target / path.name
                if path.is_file() and (not destination.exists() or "--ignore-existing" not in command):
                    shutil.copyfile(path, destination)
            return result()
        assert command[0] == "ssh" and command[5] == "rusty-workstation", command
        if command[-1] == "python3 -B -":
            script = kwargs["input"]
            if mode["broken_receipt"] and "query_log_paths" in script and "/submissions/" in script:
                return result(code=255)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exec(script, {})
            return result(output.getvalue())
        if "__AUTOSLURM_QUERY_" in command[-1]:
            return result(remote_observation(data["queue"], data["accounting"]))
        if "scancel" in command[-1]:
            mode["cancel"] = True
            return result()
        pytest.fail(f"Unexpected command {command!r}")

    monkeypatch.setattr(subprocess, "run", run)
    planned = save_bundle({
        "stars": {"name": "stars", "script": "science stars", "slurm": {"array": "0-1"}},
        "merge": {"name": "merge", "script": "science merge", "dependencies": ["stars"]},
    }, "science")
    receipt = submit_jobs("science", machine="rusty-local", bundle_path=planned)
    (cluster / "out").mkdir(exist_ok=True)
    (cluster / "out/stars-101_1.out").write_text("scientific log evidence\n")
    source = Path(receipt["bundle_path"])
    source_receipt = Path(receipt["receipt_path"])
    original = (source.read_bytes(), source_receipt.read_bytes())
    set_storage_root(laptop)
    save_config({"machines": {"rusty": {"ssh_alias": "rusty-workstation", "path": str(cluster), "env_command": "true"}},
                 "default_machine": "rusty"})
    calls.clear()
    yield {"laptop": laptop, "cluster": cluster, "receipt": receipt, "source": source,
           "source_receipt": source_receipt, "calls": calls, "data": data, "mode": mode}
    if not mode.get("source_edited"):
        assert (source.read_bytes(), source_receipt.read_bytes()) == original, "Sync changed the source"
    set_storage_root(laptop)


def imported(native):
    return native["laptop"] / "submissions" / (native["receipt"]["submission_id"] + ".json")


def test_cluster_origin_import_status_logs_cancel_fetch_and_repeat(native, capsys):
    sync_machine("rusty")
    selected = imported(native)
    receipt = load_submission(selected)
    assert receipt["machine"] == "rusty" and receipt["execution"]["is_remote"]
    assert receipt["execution"]["transport"] == {"ssh_alias": "rusty-workstation"}
    assert receipt["sync_origin"]["machine"] == "rusty-local"
    assert receipt["sync_origin"]["bundle_path"] == str(native["source"])
    laptop_view = inspect_bundle(receipt_path=selected)
    set_storage_root(native["cluster"])
    cluster_view = inspect_bundle(native["source"])
    set_storage_root(native["laptop"])
    def evidence(view):
        return [(job["name"], job["id"], job["state"], job["counts"]) for job in view["jobs"]]
    assert evidence(laptop_view) == evidence(cluster_view)
    assert not laptop_view["errors"]
    refreshed = refresh_submission(selected)
    assert refreshed["receipt_path"] == str(selected) and refreshed["sync_origin"] == receipt["sync_origin"]
    fetched = fetch_run(receipt_path=selected, job_name="stars", task_index=1)
    assert any("scientific log evidence" in log.get("text", "") for log in fetched["logs"])
    cancel.main(["--bundle-file", refreshed["bundle_path"], "--yes"])
    assert native["mode"]["cancel"]
    paths = list((native["laptop"] / "jobs").glob("*.json"))
    before = {path: path.read_bytes() for path in paths}
    sync_machine("rusty")
    backups = list((native["laptop"] / "sync_backups").rglob("*.json"))
    sync_machine("rusty")
    assert {path: path.read_bytes() for path in paths} == before
    assert list((native["laptop"] / "jobs").glob("*.json")) == paths
    assert list((native["laptop"] / "sync_backups").rglob("*.json")) == backups
    assert not list(native["laptop"].glob(".sync-*"))


def test_repairs_raw_copy_and_preserves_original_backup(native):
    copied = native["laptop"] / "jobs" / native["source"].name
    copied.write_bytes(native["source"].read_bytes())
    original = json.loads(copied.read_text())
    sync_machine("rusty")
    rebased = json.loads(copied.read_text())
    assert rebased["stars"]["machine"] == "rusty"
    assert rebased["stars"][EXECUTION_METADATA_KEY]["is_remote"] is True
    assert rebased["stars"][SUBMISSION_METADATA_KEY]["receipt_path"] == str(imported(native))
    assert [rebased[name]["id"] for name in rebased] == [original[name]["id"] for name in original]
    assert len(list((native["laptop"] / "jobs").glob("*.json"))) == 1
    assert any(json.loads(path.read_text()) == original for path in (native["laptop"] / "sync_backups").rglob("*.json"))


def test_known_id_conflict_preserves_every_existing_record(native):
    copied = native["laptop"] / "jobs" / native["source"].name
    bundle = json.loads(native["source"].read_text())
    bundle["stars"]["id"] = "999"
    copied.write_text(json.dumps(bundle))
    before = copied.read_bytes()
    with pytest.raises(DiagnosticError, match="known scheduler ID"):
        sync_machine("rusty")
    assert copied.read_bytes() == before and not imported(native).exists()


@pytest.mark.parametrize("problem", ["missing", "corrupt", "transport"])
def test_bad_receipt_preserves_raw_copy(native, problem):
    copied = native["laptop"] / "jobs" / native["source"].name
    copied.write_bytes(native["source"].read_bytes())
    before = copied.read_bytes()
    if problem == "missing":
        native["source_receipt"].unlink()
        native["mode"]["source_edited"] = True
    elif problem == "corrupt":
        native["source_receipt"].write_text("{")
        native["mode"]["source_edited"] = True
    else:
        native["mode"]["broken_receipt"] = True
    with pytest.raises(DiagnosticError):
        sync_machine("rusty")
    assert copied.read_bytes() == before and not imported(native).exists()


def test_repeat_pins_transport_and_rejects_profile_redirection(native):
    sync_machine("rusty")
    before = imported(native).read_bytes()
    from autoslurm.execution import resolve_execution_context
    from autoslurm.tracking_sync import import_tracking_directory
    context = resolve_execution_context("rusty", {"ssh_alias": "different-host", "path": str(native["cluster"])},
                                        root_resolver=lambda *_: str(native["cluster"]))
    # Receipt read remains explicitly mocked; validation must still reject a redirect.
    monkey = pytest.MonkeyPatch()
    monkey.setattr("autoslurm.tracking_sync.read_execution_receipt", lambda _: native["source_receipt"].read_text())
    try:
        _, errors = import_tracking_directory(native["cluster"] / "jobs", context, native["laptop"])
    finally:
        monkey.undo()
    assert errors and "transport" in str(errors[0]) and imported(native).read_bytes() == before


def test_laptop_origin_updates_original_view_without_duplicate(installations, monkeypatch):
    laptop, cluster, planned, _, calls, _, _ = installations
    receipt = submit_jobs("study", machine="cluster", bundle_path=planned)
    original_run = Path(receipt["bundle_path"])
    remote_path = Path(receipt["execution_bundle_path"])
    raw_copy = laptop / "jobs" / remote_path.name
    if raw_copy == original_run:
        raw_copy = laptop / "jobs" / "study_20250101000000.json"
    raw_copy.write_bytes(remote_path.read_bytes())
    real_fake = subprocess.run
    def run(command, **kwargs):
        if command[0] != "rsync":
            return real_fake(command, **kwargs)
        source = Path(command[-2].split(":", 1)[1])
        target = Path(command[-1])
        target.mkdir(exist_ok=True, parents=True)
        for path in source.iterdir():
            if path.is_file():
                shutil.copyfile(path, target / path.name)
        return subprocess.CompletedProcess(command, 0, "", "")
    monkeypatch.setattr(subprocess, "run", run)
    sync_machine("cluster")
    current = load_submission(receipt["receipt_path"])
    assert current["bundle_path"] == str(original_run) and "sync_origin" not in current
    assert not raw_copy.exists()
    selected = [path for path in (laptop / "jobs").glob("*.json")
                if any(job.get(SUBMISSION_METADATA_KEY, {}).get("submission_id") == receipt["submission_id"]
                       for job in json.loads(path.read_text()).values())]
    assert selected == [original_run]
    assert json.loads(original_run.read_text())["shards"][EXECUTION_METADATA_KEY]["is_remote"]
    assert list((laptop / "sync_backups").rglob("*.json"))
    assert refresh_submission(receipt["receipt_path"])["submission_id"] == receipt["submission_id"]


def edit_source(native, *, receipt=None, bundle=None):
    native["mode"]["source_edited"] = True
    if receipt is not None:
        native["source_receipt"].write_text(json.dumps(receipt))
    if bundle is not None:
        native["source"].write_text(json.dumps(bundle))


def test_partial_receipt_recovers_new_id_without_new_attempt_or_regression(native):
    receipt = copy.deepcopy(native["receipt"])
    receipt.update(state="uncertain", execution_finished=False)
    receipt["jobs"]["merge"].update(state="uncertain", id=None)
    bundle = json.loads(native["source"].read_text())
    bundle["merge"].pop("id", None)
    edit_source(native, receipt=receipt, bundle=bundle)
    sync_machine("rusty")
    local = load_submission(imported(native))
    path = Path(local["bundle_path"])
    assert local["state"] == "uncertain" and json.loads(path.read_text())["stars"]["id"] == "101"
    receipt.update(state="submitted", execution_finished=True)
    receipt["jobs"]["merge"].update(state="accepted", id="102")
    edit_source(native, receipt=receipt)
    sync_machine("rusty")
    assert json.loads(path.read_text())["merge"]["id"] == "102"
    assert load_submission(imported(native))["state"] == "submitted"
    before = (path.read_bytes(), imported(native).read_bytes())
    receipt.update(state="uncertain", execution_finished=False)
    receipt["jobs"]["merge"].update(state="uncertain", id=None)
    edit_source(native, receipt=receipt)
    with pytest.raises(DiagnosticError, match="known scheduler ID"):
        sync_machine("rusty")
    assert (path.read_bytes(), imported(native).read_bytes()) == before
    assert len(list((native["laptop"] / "jobs").glob("*.json"))) == 1


@pytest.mark.parametrize("field", ["script", "script_args", "slurm"])
def test_different_definition_is_not_overwritten(native, field):
    copied = native["laptop"] / "jobs" / native["source"].name
    bundle = json.loads(native["source"].read_text())
    bundle["stars"][field] = "different command" if field == "script" else {"different": "value"}
    copied.write_text(json.dumps(bundle))
    before = copied.read_bytes()
    with pytest.raises(DiagnosticError, match="different job definitions"):
        sync_machine("rusty")
    assert copied.read_bytes() == before and not imported(native).exists()


def test_one_missing_receipt_keeps_healthy_neighbour(native):
    bundle = json.loads(native["source"].read_text())
    identity = "b" * 32
    for job in bundle.values():
        job[SUBMISSION_METADATA_KEY].update(submission_id=identity,
            receipt_path=str(native["cluster"] / "submissions" / (identity + ".json")))
    (native["cluster"] / "jobs/another_20250101000000.json").write_text(json.dumps(bundle))
    with pytest.raises(DiagnosticError):
        sync_machine("rusty")
    assert imported(native).exists()
    assert not (native["laptop"] / "submissions" / (identity + ".json")).exists()
    assert not inspect_bundle(receipt_path=imported(native))["errors"]


@pytest.mark.parametrize("existing", [False, True])
def test_interrupted_snapshot_publish_preserves_receipt_and_recovers_on_explicit_sync(native, monkeypatch, existing):
    import autoslurm.tracking_sync as module
    target = native["laptop"] / "jobs" / native["source"].name
    if existing:
        target.write_bytes(native["source"].read_bytes())
    real = module.atomic_json
    def write(path, *args, **kwargs):
        if Path(path) == target:
            raise OSError("injected publication failure")
        return real(path, *args, **kwargs)
    # Simulate a native writer failure through the actual atomic adapter boundary.
    from autoslurm.record_files import _write_error
    def diagnosed(path, *args, **kwargs):
        try:
            return write(path, *args, **kwargs)
        except OSError as error:
            raise _write_error(error, path, "publish_record", {"record_publication": "not_started"}) from error
    monkeypatch.setattr(module, "atomic_json", diagnosed)
    with pytest.raises(DiagnosticError):
        sync_machine("rusty")
    assert load_submission(imported(native))["jobs"]["stars"]["id"] == "101"
    assert existing == target.exists()
    monkeypatch.setattr(module, "atomic_json", real)
    sync_machine("rusty")
    assert json.loads(target.read_text())["stars"][EXECUTION_METADATA_KEY]["is_remote"]
    assert not any(command[0] == "sbatch" for command in native["calls"])


def test_raw_receipt_copy_is_also_repaired_with_backup(native):
    copied = native["laptop"] / "jobs" / native["source"].name
    copied.write_bytes(native["source"].read_bytes())
    imported(native).parent.mkdir(exist_ok=True)
    imported(native).write_bytes(native["source_receipt"].read_bytes())
    original = json.loads(imported(native).read_text())
    sync_machine("rusty")
    receipt = load_submission(imported(native))
    assert receipt["machine"] == "rusty" and receipt["execution"]["is_remote"]
    assert any(json.loads(path.read_text()) == original for path in (native["laptop"] / "sync_backups").rglob("*.json"))


def test_changed_local_record_during_backup_is_retained(native, monkeypatch):
    import autoslurm.tracking_sync as module
    target = native["laptop"] / "jobs" / native["source"].name
    target.write_bytes(native["source"].read_bytes())
    changed = json.loads(target.read_text())
    changed["stars"]["script_args"] = {"changed": True}
    real = module._backup
    def backup(path, *args):
        real(path, *args)
        if path == target:
            target.write_text(json.dumps(changed))
    monkeypatch.setattr(module, "_backup", backup)
    with pytest.raises(DiagnosticError, match="changed while"):
        sync_machine("rusty")
    assert json.loads(target.read_text()) == changed


def test_orphaned_raw_copy_is_reported_not_guessed(native):
    target = native["laptop"] / "jobs" / native["source"].name
    target.write_bytes(native["source"].read_bytes())
    before = target.read_bytes()
    native["source"].unlink()
    native["mode"]["source_edited"] = True
    with pytest.raises(DiagnosticError, match="no verified source snapshot"):
        sync_machine("rusty")
    assert target.read_bytes() == before and not imported(native).exists()


@pytest.mark.parametrize("field", ["receipt_path", "submission_id"])
def test_source_link_cannot_read_arbitrary_remote_file(native, field):
    bundle = json.loads(native["source"].read_text())
    for job in bundle.values():
        job[SUBMISSION_METADATA_KEY][field] = "/etc/other" if field == "receipt_path" else "bad-identity"
    edit_source(native, bundle=bundle)
    with pytest.raises(DiagnosticError):
        sync_machine("rusty")
    assert not imported(native).exists()


def test_sync_twice_does_not_confuse_same_label_with_different_attempt(native):
    sync_machine("rusty")
    source = json.loads(native["source"].read_text())
    other_identity = "c" * 32
    other_path = native["cluster"] / "jobs/science_20250101000000.json"
    other_receipt_path = native["cluster"] / "submissions" / (other_identity + ".json")
    receipt = copy.deepcopy(native["receipt"])
    receipt.update(submission_id=other_identity, bundle_path=str(other_path), receipt_path=str(other_receipt_path),
                   execution_receipt_path=str(other_receipt_path))
    for job in source.values():
        job[SUBMISSION_METADATA_KEY].update(submission_id=other_identity, receipt_path=str(other_receipt_path))
    other_path.write_text(json.dumps(source))
    other_receipt_path.write_text(json.dumps(receipt))
    sync_machine("rusty")
    assert len(list((native["laptop"] / "jobs").glob("*.json"))) == 2
    assert imported(native).exists() and (native["laptop"] / "submissions" / (other_identity + ".json")).exists()
