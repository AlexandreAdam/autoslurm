"""Intentional client surface and historical import paths."""

import autoslurm


def test_public_exports_are_explicit_and_include_client_operations():
    namespace = {}
    exec("from autoslurm import *", namespace)
    actual = set(namespace) - {"__builtins__"}
    assert actual == set(autoslurm.__all__)
    assert {"save_bundle", "schedule_job", "preview_bundle", "submit_jobs", "SubmissionError",
            "load_submission", "refresh_submission", "list_submissions", "list_runs",
            "inspect_bundle", "inspect_bundles", "recorded_execution", "resolve_results_path",
            "path_exists", "execute_acp", "action_definitions"} <= actual
    assert not {"Callable", "dataclass", "defaultdict", "annotations", "atomic_json", "ssh_command"} & actual
    assert not any(hasattr(autoslurm, name) for name in ("Callable", "dataclass", "defaultdict"))


def test_historical_import_paths_alias_the_single_owner():
    from autoslurm import configuration, transport, utils, file_transfer, save_load_jobs, bundle_selection
    from autoslurm import submission, record_files

    assert utils.load_config is configuration.load_config is autoslurm.load_config
    assert utils.save_config is configuration.save_config is autoslurm.save_config
    assert utils.machine_config is configuration.machine_config is autoslurm.machine_config
    assert utils.remote_storage_root_from_config is transport.remote_storage_root_from_config
    assert save_load_jobs.transfer_slurms_to_remote is file_transfer.transfer_slurms_to_remote
    assert save_load_jobs.select_bundle_snapshot is bundle_selection.select_bundle_snapshot
    assert submission.atomic_json is record_files.atomic_json


def test_ssh_construction_is_pure_and_does_not_mutate_profile(monkeypatch):
    import copy
    from autoslurm.transport import ssh_command

    machine = {"username": "scientist", "hosturl": "cluster", "key_path": "/keys/science key"}
    before = copy.deepcopy(machine)
    monkeypatch.setattr("builtins.open", lambda *a, **k: (_ for _ in ()).throw(AssertionError("No configuration or file read")))
    monkeypatch.setattr("subprocess.run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("No process")))
    command = ssh_command(machine, "recorded", "cat -- '/results/part 1'", options=["-o", "BatchMode=yes"])
    assert command == ["ssh", "-o", "BatchMode=yes", "-i", "/keys/science key", "scientist@cluster", "cat -- '/results/part 1'"]
    assert machine == before
