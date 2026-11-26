"""Cancellation must target the same producing transport as inspection."""

import subprocess
import shlex

import pytest

from autoslurm.apps import cancel
from autoslurm.execution import EXECUTION_METADATA_KEY, resolve_execution_context
from autoslurm.utils import save_config
from tests.inspection_helpers import saved_run, remote_observation


def scheduler_and_cancel(monkeypatch):
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        queue = "7546964|PENDING|30:00|Dependency\n7546965|PENDING|30:00|Dependency"
        if command[0] == "squeue":
            return subprocess.CompletedProcess(command, 0, queue, "")
        if command[0] == "sacct":
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[0] == "scancel" or (command[0] == "ssh" and "scancel" in command[-1]):
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[0] == "ssh":
            return subprocess.CompletedProcess(command, 0, remote_observation(queue), "")
        pytest.fail(f"Unexpected command {command!r}")

    monkeypatch.setattr(subprocess, "run", run)
    return calls


def bundle(*, recorded=None, profile=None):
    machine = "rusty-local"
    save_config({"machines": {machine: profile or {"results_root": "/results"}},
                 "default_machine": machine})
    jobs = {}
    for name, identity in (("merge", "7546964"), ("fit", "7546965")):
        job = {"name": name, "id": identity, "machine": machine,
               "script": "echo science", "slurm": {}}
        if recorded is not None:
            context = resolve_execution_context(machine, recorded,
                                                root_resolver=lambda *_: "/recorded-state")
            job[EXECUTION_METADATA_KEY] = context.resolve_job(job)
        jobs[name] = job
    return saved_run(name="rehearsal", jobs=jobs)


@pytest.mark.parametrize("selection", ["index", "name", "file"])
@pytest.mark.parametrize("recorded", [None, {}], ids=["legacy-profile", "recorded-local"])
def test_named_local_profile_cancels_locally(monkeypatch, capsys, selection, recorded):
    path = bundle(recorded=recorded)
    before = path.read_bytes()
    calls = scheduler_and_cancel(monkeypatch)
    args = {"index": ["1"], "name": ["rehearsal"], "file": ["--bundle-file", str(path)]}[selection]
    cancel.main([*args, "--yes"])
    mutations = [call for call in calls if call[0] == "scancel"]
    assert len(mutations) == 1 and set(mutations[0][1:]) == {"7546964", "7546965"}
    assert not any(call[0] == "ssh" for call in calls)
    assert path.read_bytes() == before
    assert "Cancelled 2" in capsys.readouterr().out


@pytest.mark.parametrize("recorded,profile,alias", [
    ({}, {"ssh_alias": "wrong-host"}, None),
    ({"ssh_alias": "producing-host"}, {}, "producing-host"),
    ({"ssh_alias": "producing-host"}, {"ssh_alias": "wrong-host"}, "producing-host"),
    (None, {"ssh_alias": "current-host"}, "current-host"),
])
def test_cancellation_uses_producing_transport(monkeypatch, recorded, profile, alias):
    path = bundle(recorded=recorded, profile=profile)
    calls = scheduler_and_cancel(monkeypatch)
    if recorded is not None:
        monkeypatch.setattr(cancel, "load_config", lambda: pytest.fail("Recorded cancellation loaded current config"))
    cancel.main(["--bundle-file", str(path), "--yes"])
    mutations = [call for call in calls if call[0] == "scancel" or "scancel" in call[-1]]
    assert len(mutations) == 1
    command = mutations[0]
    if alias is None:
        assert command[0] == "scancel" and set(command[1:]) == {"7546964", "7546965"}
    else:
        assert command[0] == "ssh" and command[-2] == alias
        assert set(shlex.split(shlex.split(command[-1])[-1])) == {"scancel", "7546964", "7546965"}


def test_preview_does_not_cancel(monkeypatch, capsys):
    path = bundle(recorded={})
    calls = scheduler_and_cancel(monkeypatch)
    cancel.main(["--bundle-file", str(path)])
    assert calls and not any("scancel" in " ".join(call) for call in calls)
    assert "Preview only" in capsys.readouterr().out


@pytest.mark.parametrize("bad", [
    {"machine_name": "missing", "job_id_raw": "2"},
    {"machine_name": "rusty-local", "job_id_raw": "2", EXECUTION_METADATA_KEY:
        {"is_remote": True, "transport": {}}},
])
def test_invalid_target_stops_before_any_cancellation(monkeypatch, bad):
    path = bundle(recorded={})
    monkeypatch.setattr(cancel, "bundle_job_rows_from_jobs", lambda *a, **k:
        (None, [{"machine_name": None, "job_id_raw": "1"}, bad]))
    monkeypatch.setattr(cancel, "bundle_jobs_context_from_rows", lambda *a: "preview")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("Invalid target dispatched cancellation"))
    with pytest.raises(ValueError, match="no local fallback"):
        cancel.main(["--bundle-file", str(path), "--yes"])


def test_same_profile_name_does_not_merge_different_recorded_destinations(monkeypatch):
    path = bundle(recorded={"ssh_alias": "first-host"})
    from autoslurm.save_load_jobs import load_bundle_from_path
    jobs, _, date = load_bundle_from_path(path)
    next(job for job in jobs if job["name"] == "fit")[EXECUTION_METADATA_KEY]["transport"] = {"ssh_alias": "second-host"}
    monkeypatch.setattr(cancel, "load_bundle_from_path", lambda *_: (jobs, {}, date))
    calls = scheduler_and_cancel(monkeypatch)
    cancel.main(["--bundle-file", str(path), "--yes"])
    mutations = [call for call in calls if "scancel" in call[-1]]
    assert sorted((call[-2], call[-1]) for call in mutations) == [
        ("first-host", "bash -lc 'scancel 7546964'"),
        ("second-host", "bash -lc 'scancel 7546965'"),
    ]
