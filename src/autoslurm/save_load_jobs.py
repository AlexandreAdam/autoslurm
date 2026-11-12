"""
Utility functions to save/load bundle of jobs to/from a JSON file in the jobs directory
"""

from .utils import (
    load_config,
    save_config,
    scp_host_and_keypath_from_config,
    remote_storage_root_from_config,
    ssh_host_from_config,
)
from .definitions import DATE_FORMAT
from .execution import resolve_execution_context
from .job_dependency import dependency_graph
from typing import Optional
from graphlib import TopologicalSorter
from graphlib import CycleError
from datetime import datetime, timedelta
import warnings
import subprocess
import json
import os
import re
import shlex
from pathlib import Path
from .storage import ensure_storage_dirs, jobs_dir, slurm_dir, storage_root
from .utils import ssh_host_from_config

__all__ = [
    "schedule_job",
    "save_bundle",
    "load_bundle",
    "load_bundle_from_path",
    "list_saved_bundles",
    "latest_bundle_summaries",
    "bundle_snapshots",
    "get_bundle_filter_mode",
    "set_bundle_filter_mode",
    "stale_bundle_snapshots",
    "inactive_bundle_snapshots",
    "all_bundle_snapshots",
    "bundle_snapshot_state",
    "transfer_slurm_to_remote",
    "transfer_slurms_to_remote",
    "transfer_bundle_to_remote",
    "nearest_bundle_filename",
    "select_bundle_snapshot",
]

_ENSURED_REMOTE_DIRS: set[tuple[str, str]] = set()
SNAPSHOT_KIND_KEY = "_autoslurm_snapshot_kind"


def get_bundle_filter_mode() -> str:
    """
    Return global bundle visibility filter mode ('active' or 'all').
    """
    try:
        cfg = load_config()
    except Exception:
        return "active"
    mode = str(cfg.get("bundle_filter_mode", "active")).strip().lower()
    return mode if mode in {"active", "all"} else "active"


def set_bundle_filter_mode(mode: str) -> str:
    """
    Persist global bundle visibility filter mode.
    """
    normalized = str(mode).strip().lower()
    if normalized not in {"active", "all"}:
        raise ValueError("mode must be 'active' or 'all'")
    cfg = load_config()
    cfg["bundle_filter_mode"] = normalized
    save_config(cfg)
    return normalized


def _submitted_job_count(jobs_obj) -> int:
    if not isinstance(jobs_obj, dict):
        return 0
    return sum(1 for job in jobs_obj.values() if isinstance(job, dict) and job.get("id") is not None)


def _snapshot_kind_from_payload(payload: dict) -> str:
    explicit: set[str] = set()
    for job in payload.values():
        if not isinstance(job, dict):
            continue
        value = str(job.get(SNAPSHOT_KIND_KEY, "")).strip().lower()
        if value in {"draft", "submission"}:
            explicit.add(value)
    if "submission" in explicit:
        return "submission"
    if "draft" in explicit:
        return "draft"
    # Backward-compatibility for legacy snapshots created before kind stamping.
    submitted_count = _submitted_job_count(payload)
    return "submission" if submitted_count > 0 else "draft"


def _ensure_snapshot_kind(payload: dict, *, kind: str) -> dict:
    if kind not in {"draft", "submission"}:
        raise ValueError("kind must be 'draft' or 'submission'")
    if not isinstance(payload, dict):
        return payload
    for job in payload.values():
        if isinstance(job, dict):
            value = str(job.get(SNAPSHOT_KIND_KEY, "")).strip().lower()
            if value not in {"draft", "submission"}:
                job[SNAPSHOT_KIND_KEY] = kind
    return payload


def _snapshot_date(path, *, fallback_to_mtime=False):
    path = Path(path)
    try:
        if re.fullmatch(r".+_\d{14}", path.stem) is None:
            raise ValueError(f"Not a versioned AutoSlurm snapshot: {path.name}")
        return datetime.strptime(path.stem.rsplit("_", 1)[-1], DATE_FORMAT)
    except ValueError:
        if not fallback_to_mtime:
            raise
        return datetime.fromtimestamp(path.stat().st_mtime)


def _analyze_bundle_file(filename: Path) -> dict:
    """
    Classify a saved bundle snapshot as active/ready_to_go/broken.
    """
    stem = filename.stem
    bundle_name, date_text = stem.rsplit("_", 1)
    saved_date = _snapshot_date(filename)
    try:
        with open(filename, "r") as file:
            payload = json.load(file)
    except (json.JSONDecodeError, OSError):
        return {
            "bundle": bundle_name,
            "date": saved_date,
            "path": filename,
            "job_count": 0,
            "submitted_count": 0,
            "state": "broken",
        }

    if not isinstance(payload, dict):
        return {
            "bundle": bundle_name,
            "date": saved_date,
            "path": filename,
            "job_count": 0,
            "submitted_count": 0,
            "state": "broken",
        }

    if any(not isinstance(job, dict) for job in payload.values()):
        return {
            "bundle": bundle_name,
            "date": saved_date,
            "path": filename,
            "job_count": len(payload),
            "submitted_count": 0,
            "state": "broken",
        }

    for job_name, job in payload.items():
        dependencies = job.get("dependencies")
        if dependencies is None:
            continue
        if not isinstance(dependencies, (list, tuple)):
            return {
                "bundle": bundle_name,
                "date": saved_date,
                "path": filename,
                "job_count": len(payload),
                "submitted_count": 0,
                "state": "broken",
            }
        for dep in dependencies:
            if not isinstance(dep, str) or dep not in payload:
                return {
                    "bundle": bundle_name,
                    "date": saved_date,
                    "path": filename,
                    "job_count": len(payload),
                    "submitted_count": 0,
                    "state": "broken",
                }

    try:
        dependencies = dependency_graph(payload)
        tuple(TopologicalSorter(dependencies).static_order())
    except (CycleError, ValueError, TypeError):
        return {
            "bundle": bundle_name,
            "date": saved_date,
            "path": filename,
            "job_count": len(payload),
            "submitted_count": 0,
            "state": "broken",
        }

    submitted_count = _submitted_job_count(payload)
    snapshot_kind = _snapshot_kind_from_payload(payload)
    return {
        "bundle": bundle_name,
        "date": saved_date,
        "path": filename,
        "job_count": len(payload),
        "submitted_count": submitted_count,
        "state": "active" if (snapshot_kind == "submission" and (submitted_count > 0 or any(job.get("_autoslurm_submission") for job in payload.values()))) else "ready_to_go",
        "snapshot_kind": snapshot_kind,
    }


def bundle_snapshot_state(bundle_path: str | Path) -> dict:
    """
    Return analyzed snapshot metadata for an explicit bundle file path.
    """
    path = Path(bundle_path)
    if not path.is_file():
        raise FileNotFoundError(f"Bundle file not found: {path}")
    stem = path.stem
    if "_" not in stem:
        raise ValueError(
            f"Bundle filename must include a timestamp suffix '_{DATE_FORMAT}'. Got: {path.name}"
        )
    _, date_text = stem.rsplit("_", 1)
    _snapshot_date(path)
    return _analyze_bundle_file(path)


def _is_placeholder_file(path: Path) -> bool:
    return path.name.startswith(".")


def _all_snapshot_entries() -> list[dict]:
    ensure_storage_dirs()
    entries: list[dict] = []
    for filename in jobs_dir().glob("*.json"):
        if _is_placeholder_file(filename):
            continue
        stem = filename.stem
        if "_" not in stem:
            continue
        _, date_text = stem.rsplit("_", 1)
        try:
            _snapshot_date(filename)
        except ValueError:
            continue
        entries.append(_analyze_bundle_file(filename))
    entries.sort(key=lambda entry: entry["date"], reverse=True)
    return entries


def all_bundle_snapshots() -> list[dict]:
    """
    Return all saved bundle snapshots regardless of global filter mode.
    """
    return _all_snapshot_entries()


def _active_visible_snapshots(entries: list[dict]) -> list[dict]:
    """
    Policy for the `active` filter:
    - keep all submitted snapshots (`state=active`)
    - keep the latest `ready_to_go` snapshot if it is the latest snapshot
      overall for that bundle name, even if older submitted snapshots exist
    - if no submitted snapshots and latest is `broken`, keep latest broken
    """
    by_bundle: dict[str, list[dict]] = {}
    for entry in entries:
        by_bundle.setdefault(str(entry["bundle"]), []).append(entry)
    selected: list[dict] = []
    for _, group in by_bundle.items():
        group = sorted(group, key=lambda entry: entry["date"], reverse=True)
        latest = group[0]
        active_group = [entry for entry in group if entry.get("state") == "active"]
        if active_group:
            selected.extend(active_group)
        if latest.get("state") == "ready_to_go":
            selected.append(latest)
            continue
        if not active_group and latest.get("state") == "broken":
            selected.append(latest)
    selected.sort(key=lambda entry: entry["date"], reverse=True)
    return selected


def _stale_snapshots(entries: list[dict]) -> list[dict]:
    """
    Stale snapshots are entries not selected by the active-visibility policy.
    """
    visible = _active_visible_snapshots(entries)
    visible_paths = {str(entry["path"]) for entry in visible}
    stale = [entry for entry in entries if str(entry["path"]) not in visible_paths]
    stale.sort(key=lambda entry: entry["date"], reverse=True)
    return stale


def save_bundle(
    bundle: dict,
    name: str,
    append: bool = False,
) -> Path:
    """
    Save job bundle configuration to a JSON file.

    Args:
        name (str): The name of the job bundle to save.
        bundle (dict): A dict of jobs (dict).
        append (bool): Flag indicating whether to append the job configurations to an existing file. Defaults to False.

    Behavior:
        - If append=False, a new job file is created.
        - If append=True, the jobs are saved to the last modified bundle with pattern 'name_*'. If no bundle file exists, a new one is created.
        - If job does not have key 'name', one is provided based on the key in the bundle.

    Returns:
        Path: The exact saved snapshot, suitable for explicit loading/submission.
    """
    if not isinstance(bundle, dict):
        raise TypeError("bundle must be a dictionary")
    for _, job in bundle.items():
        if not isinstance(job, dict):
            raise TypeError(
                "Each job in the bundle must be a dictionary. If you want to save a single job, use schedule_job() instead."
            )
        if "script" not in job:
            raise KeyError(
                "Each job in the bundle must minimally contain the 'script' entry to run an application"
            )

    if append:
        bundle = _ensure_snapshot_kind(bundle, kind="draft")
        for job_name, job in bundle.items():
            job["name"] = _effective_job_name(job, job_name)
            _, file_path = schedule_job(job, name, append=True)
    else:
        # Make sure a file with the same date does not exists, otherwise add 1 second to timestamp
        try:
            date = datetime.now()
            _, nearest_date = nearest_bundle_filename(name)
            if date - nearest_date < timedelta(seconds=1):
                warnings.warn(
                    "Found a job saved at the same time. "
                    "If you wanted the job to be appended to a bundle instead, "
                    "use the flags --append and --bundle=name_of_bundle."
                )
                date += timedelta(seconds=1)
        except FileNotFoundError:
            pass
        ensure_storage_dirs()
        # Make sure every job has a name
        for job_name, job in bundle.items():
            job["name"] = _effective_job_name(job, job_name)
        bundle = _ensure_snapshot_kind(bundle, kind="draft")
        while True:
            file_path = jobs_dir() / f"{name}_{date.strftime(DATE_FORMAT)}.json"
            try:
                with open(file_path, "x") as file:
                    json.dump(bundle, file, indent=4)
                break
            except FileExistsError:
                date += timedelta(seconds=1)
    print(f"Saved bundle {name} to {file_path}")
    return file_path


def schedule_job(
    job: dict,
    bundle_name: Optional[str] = None,
    append: bool = False,
) -> None:
    """
    Save job configurations to a JSON file.

    Args:
        job (dict): A dict of job configurations.
        bundle_name (Optional[str]): The name of the job bundle file to save to a JSON file. If None, the job name is used. Defaults to None.
        append (bool): Flag indicating whether to append the job configuration to an existing bundle. Defaults to False.

    Behavior:
        - If append=False and bundle_name=None, a new job file is created.
        - If append=False and bundle_name is specified, a new job file is created.
        - If append=True and bundle_name=None, the job is saved to the last modified bundle with pattern 'job['name']_*'.
            If no bundle file exists, a new one is created.
        - If append=True and bundle_name is specified, the job is saved to the latest bundle with the specified name.
            If no bundle file exists, a new one is created.
        - If job does not have key 'name', one is provided based on the script name. Note that name must be unique in the bundle,
            so the scheduler reserves the right to modify it.
    Returns:
        dict: The saved job configuration
    """
    ensure_storage_dirs()
    job_dir = jobs_dir()
    if "script" not in job:
        raise KeyError(
            "Job configuration must minimally contain the 'script' entry to run an application"
        )

    if "name" not in job:  # If job does not have a name, use the script name
        script_value = job["script"]
        tokens = script_value.split()
        candidate = tokens[-1]
        if candidate.endswith(".py"):
            job["name"] = Path(candidate).stem
        elif Path(script_value).suffix:
            job["name"] = Path(script_value).stem
        else:
            job["name"] = script_value
    # Normalize python script paths without invocation
    if len(job["script"].split()) == 1 and job["script"].endswith(".py"):
        job["script"] = f"python {job['script']}"
    job_name = job["name"]

    if bundle_name is None:
        bundle_name = job_name

    if append:
        try:  # Save the job in existing bundle file
            # Load the job file
            filename, date = nearest_bundle_filename(bundle_name)
            file_path = job_dir / filename
            with open(file_path, "r") as file:
                bundle = json.load(file)
            # Create a unique name in case of name conflict
            if job_name in bundle:
                i = 1
                job_name = f"{job_name}_{i:03d}"
                while job_name in bundle:
                    i += 1
                    job_name = f"{job_name[:-4]}_{i:03d}"
            job["name"] = job_name  # Update name of the job
            value = str(job.get(SNAPSHOT_KIND_KEY, "")).strip().lower()
            if value not in {"draft", "submission"}:
                job[SNAPSHOT_KIND_KEY] = "draft"
            bundle[job_name] = job  # Save it in bundle
        except (
            FileNotFoundError
        ):  # Create a new empty bundle file and save the job inside it
            date = datetime.now().strftime(DATE_FORMAT)
            print(
                f"Did not find a file with the pattern '{bundle_name}_*' in the directory {job_dir}. "
                f"Creating a new bundle file '{bundle_name}_{date}.json'"
            )
            file_path = job_dir / f"{bundle_name}_{date}.json"
            bundle = {job_name: job}
    else:  # Create a new job file
        date = datetime.now()
        try:
            # Make sure a file with the same date does not exists, otherwise add 1 second to timestamp
            _, nearest_date = nearest_bundle_filename(bundle_name)
            if date - nearest_date < timedelta(seconds=1):
                date += timedelta(seconds=1)
        except FileNotFoundError:
            pass
        date = date.strftime(DATE_FORMAT)
        file_path = job_dir / f"{bundle_name}_{date}.json"
        value = str(job.get(SNAPSHOT_KIND_KEY, "")).strip().lower()
        if value not in {"draft", "submission"}:
            job[SNAPSHOT_KIND_KEY] = "draft"
        bundle = {job_name: job}

    with open(file_path, "w") as file:
        json.dump(bundle, file, indent=4)
    print(f"Saved job {job_name} to {file_path}")
    return job, file_path


def _resolve_machine_config(
    machine_name: Optional[str], machine_config: Optional[dict]
) -> tuple[Optional[str], dict]:
    if machine_name is not None:
        user_config = load_config()
        machine_config = user_config.get(machine_name)
        if not machine_config:
            raise EnvironmentError(
                f"No configuration found for machine: {machine_name}"
            )
    if machine_config is None:
        raise ValueError("Either machine_name or machine_config must be specified")
    return machine_name, machine_config


def _transfer_context(machine_name, machine_config, context):
    if context is not None:
        return context
    machine_name, machine_config = _resolve_machine_config(machine_name, machine_config)
    return resolve_execution_context(machine_name, machine_config, root_resolver=remote_storage_root_from_config)


def _scp_to_remote(local_path: Path, remote_path: str, machine_name: Optional[str], machine_config: dict) -> None:
    hostname, key_path = scp_host_and_keypath_from_config(machine_config, machine_name)
    ssh_command = ["scp"]
    if key_path:
        ssh_command.extend(shlex.split(key_path))
    ssh_command.extend([str(local_path), f"{hostname}:{remote_path}"])
    result = subprocess.run(ssh_command, capture_output=True, text=True)
    if result.returncode != 0:
        raise ValueError(f"Error running scp command: {result.stderr}")


def _ensure_remote_directory(machine_name: Optional[str], machine_config: dict, remote_dir: str) -> None:
    cache_key = (ssh_host_from_config(machine_config, machine_name), remote_dir)
    if cache_key in _ENSURED_REMOTE_DIRS:
        return
    hostname = ssh_host_from_config(machine_config, machine_name)
    result = subprocess.run(
        ["ssh", *shlex.split(hostname), f"mkdir -p {shlex.quote(remote_dir)}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(
            f"Unable to create remote directory '{remote_dir}' for machine '{machine_name or ''}': {message}"
        )
    _ENSURED_REMOTE_DIRS.add(cache_key)


def transfer_slurm_to_remote(
    slurm_name,
    machine_name: Optional[str] = None,
    machine_config: Optional[dict] = None,
    *, context=None,
) -> None:
    """
    Transfers a script from the local machine to a remote machine.
    """
    ensure_storage_dirs()
    local_script_path = slurm_dir() / slurm_name
    context = _transfer_context(machine_name, machine_config, context)
    machine_name, machine_config = context.machine_name, context.config
    remote_path = context.storage_root
    remote_script_path = os.path.join(remote_path, "slurm", slurm_name)
    _ensure_remote_directory(machine_name, machine_config, os.path.join(remote_path, "slurm"))
    _scp_to_remote(local_script_path, remote_script_path, machine_name, machine_config)
    print(f"Saved SLURM script {slurm_name} remotely")


def transfer_slurms_to_remote(
    slurm_names: list[str],
    machine_name: Optional[str] = None,
    machine_config: Optional[dict] = None,
    *, context=None,
) -> None:
    """
    Transfer many SLURM scripts in one SCP call to reduce connection/setup overhead.
    """
    if not slurm_names:
        return
    ensure_storage_dirs()
    context = _transfer_context(machine_name, machine_config, context)
    machine_name, machine_config = context.machine_name, context.config
    remote_path = context.storage_root
    remote_slurm_dir = os.path.join(remote_path, "slurm")
    _ensure_remote_directory(machine_name, machine_config, remote_slurm_dir)
    _ensure_remote_directory(machine_name, machine_config, os.path.join(remote_path, "out"))

    hostname, key_path = scp_host_and_keypath_from_config(machine_config, machine_name)
    scp_command = ["scp"]
    if key_path:
        scp_command.extend(shlex.split(key_path))
    scp_command.extend([str(slurm_dir() / slurm_name) for slurm_name in slurm_names])
    scp_command.append(f"{hostname}:{remote_slurm_dir}/")
    result = subprocess.run(scp_command, capture_output=True, text=True)
    if result.returncode != 0:
        raise ValueError(f"Error running scp command: {result.stderr}")


def transfer_bundle_to_remote(
    bundle_name: str,
    date: datetime,
    machine_name: Optional[str] = None,
    machine_config: Optional[dict] = None,
    *, context=None,
) -> None:
    """
    Transfers the bundle JSON file to the remote machine jobs directory.
    """
    ensure_storage_dirs()
    local_bundle_path = jobs_dir() / f"{bundle_name}_{date.strftime(DATE_FORMAT)}.json"
    context = _transfer_context(machine_name, machine_config, context)
    machine_name, machine_config = context.machine_name, context.config
    remote_path = context.storage_root
    remote_bundle_path = os.path.join(remote_path, "jobs", local_bundle_path.name)
    _ensure_remote_directory(machine_name, machine_config, os.path.join(remote_path, "jobs"))
    _scp_to_remote(local_bundle_path, remote_bundle_path, machine_name, machine_config)


def order_jobs(jobs, sorted_names):
    jobs_list = []
    for name in sorted_names:
        job = jobs[name]
        job["name"] = _effective_job_name(job, name)
        jobs_list.append(job)
    return jobs_list


def _effective_job_name(job, definition_key):
    name = job.get("name")
    if name is None:
        return definition_key
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Job names must be nonempty strings.")
    return name


def load_bundle(
    name: str, desired_date: Optional[datetime] = None
) -> tuple[list, dict, datetime]:
    """
    Read the job bundle JSON file and extract the dependency graph.

    Parameters:
    name (str): The name of the job bundle to load.
    topological_sort (bool): Flag indicating whether to perform a topological sort on the dependency graph.
                             Defaults to True.

    Returns:
    tuple: A tuple containing the loaded jobs and the dependency graph.

    Raises:
    FileNotFoundError: If the specified job file does not exist.
    JSONDecodeError: If the job file is not a valid JSON file.
    """

    job_file, _ = nearest_bundle_filename(name, desired_date)
    return load_bundle_from_path(jobs_dir() / job_file)


def load_bundle_from_path(
    bundle_path: str | Path,
) -> tuple[list, dict, datetime]:
    """
    Load a bundle from an explicit JSON file path.

    This is the path-based counterpart to :func:`load_bundle`, which looks up
    bundles by name under the AutoSlurm storage root.

    Saved snapshot dates come from the filename; unversioned external files
    use modification time as a fallback.
    """
    file_path = Path(bundle_path)
    if not file_path.is_file():
        raise FileNotFoundError(f"Bundle file not found: {file_path}")

    with open(file_path, "r") as file:
        try:
            jobs = json.load(file)
        except json.JSONDecodeError:
            raise OSError(
                f"Error decoding the job bundle file {file_path}. Make sure it is a valid JSON file."
            )

    dependencies = dependency_graph(jobs)
    sorted_job_names = tuple(TopologicalSorter(dependencies).static_order())[::-1]
    jobs = order_jobs(jobs, sorted_job_names)
    # AutoSlurm snapshot identity comes from its filename, not mutable mtime.
    saved_date = _snapshot_date(file_path, fallback_to_mtime=True)
    return jobs, dependencies, saved_date


def list_saved_bundles(
    desired_date: Optional[datetime] = None,
    bundle_name: Optional[str] = None,
) -> list[dict]:
    """
    List saved bundle files ordered by proximity to a reference date.

    If ``bundle_name`` is provided, only versions of that bundle are returned.
    Otherwise every bundle under the jobs directory is included.
    """
    entries = _snapshot_paths(bundle_name, desired_date)
    for entry in entries:
        try:
            with open(entry["path"], "r") as file:
                entry["jobs"] = list(json.load(file).keys())
        except (json.JSONDecodeError, OSError, AttributeError):
            entry["jobs"] = []
    return entries


def _snapshot_paths(bundle_name=None, desired_date=None):
    """Filename-only candidates keep exact/nearest selection free of payload reads."""
    desired_date = desired_date or datetime.now()
    ensure_storage_dirs()
    entries = []
    for path in jobs_dir().glob("*.json"):
        if _is_placeholder_file(path):
            continue
        try:
            saved_date = _snapshot_date(path)
        except ValueError:
            continue
        name = path.stem.rsplit("_", 1)[0]
        if bundle_name is not None and name != bundle_name:
            continue
        entries.append({"bundle": name, "date": saved_date, "path": path, "distance": abs(saved_date - desired_date)})
    return sorted(entries, key=lambda entry: (entry["distance"], entry["date"]))


def latest_bundle_summaries(desired_date: Optional[datetime] = None) -> list[dict]:
    """
    Return the newest saved bundle for each bundle name.

    The entries are sorted by proximity to ``desired_date`` (default: now).
    """
    if desired_date is None:
        desired_date = datetime.now()
    all_entries = _all_snapshot_entries()
    mode = get_bundle_filter_mode()
    entries_for_mode = _active_visible_snapshots(all_entries) if mode == "active" else all_entries
    latest_by_name: dict[str, dict] = {}
    for entry in entries_for_mode:
        bundle_name = str(entry["bundle"])
        current = latest_by_name.get(bundle_name)
        if current is None or entry["date"] > current["date"]:
            latest_by_name[bundle_name] = entry

    entries = list(latest_by_name.values())
    entries.sort(key=lambda entry: (abs(entry["date"] - desired_date), entry["bundle"]))
    return entries


def bundle_snapshots(desired_date: Optional[datetime] = None) -> list[dict]:
    """
    Return every saved bundle snapshot (including duplicate bundle names).

    Entries are sorted by saved timestamp descending (latest first), which is
    the canonical order used by index-based CLI selectors.
    """
    all_entries = _all_snapshot_entries()
    mode = get_bundle_filter_mode()
    if mode == "active":
        return _active_visible_snapshots(all_entries)
    return all_entries


def stale_bundle_snapshots() -> list[dict]:
    """
    Return bundle snapshots that are ready to submit (valid graph, no submitted job id).
    """
    return _stale_snapshots(_all_snapshot_entries())


def inactive_bundle_snapshots() -> list[dict]:
    """
    Return bundle snapshots that are not currently running/completed (ready_to_go or broken).
    """
    return _stale_snapshots(_all_snapshot_entries())


def nearest_bundle_filename(
    name: str, desired_date: Optional[datetime] = None
) -> tuple[str, datetime]:
    """
    Get the filename of a job bundle nearest in time to desired date from the jobs directory.
    """
    selected = select_bundle_snapshot(name, desired_date=desired_date, prefer_draft=False)
    return selected["path"].name, selected["date"]


def select_bundle_snapshot(name=None, *, bundle_path=None, latest=False, index=None, desired_date=None, prefer_draft=True):
    """One selection policy for explicit paths, UI indices, draft/latest and nearest dates."""
    if sum([bundle_path is not None, bool(latest), index is not None]) > 1:
        raise ValueError("Select only one of bundle_path, latest or index.")
    if (latest or index is not None) and name is not None:
        raise ValueError("latest/index selectors do not take a bundle name.")
    if bundle_path is not None:
        path = Path(bundle_path)
        if not path.is_file():
            raise FileNotFoundError(f"Bundle file not found: {path}")
        if name is None:
            if "_" not in path.stem:
                raise ValueError("Unable to infer bundle name; provide an explicit name.")
            name = path.stem.rsplit("_", 1)[0]
        return {"bundle": name, "path": path, "date": _snapshot_date(path, fallback_to_mtime=True)}
    if index is not None:
        rows = bundle_snapshots(desired_date)
        if not 1 <= index <= len(rows):
            raise ValueError(f"Bundle index {index!r} is out of range.")
        return rows[index - 1]
    if name is None and not latest:
        raise ValueError("Select a bundle name, explicit path, latest or index.")
    if prefer_draft and desired_date is None:
        drafts = [row for row in all_bundle_snapshots() if row.get("state") == "ready_to_go" and (name is None or row["bundle"] == name)]
        if drafts:
            return max(drafts, key=lambda row: row["date"])
    candidates = latest_bundle_summaries(desired_date) if latest else _snapshot_paths(name, desired_date)
    if not candidates:
        raise FileNotFoundError(f"No files found with name {name!r} in directory {jobs_dir()}")
    return max(candidates, key=lambda row: row["date"]) if latest else candidates[0]
