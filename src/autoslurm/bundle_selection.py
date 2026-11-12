"""Local snapshot discovery and the shared draft/latest/exact selection policy."""

from datetime import datetime
from graphlib import TopologicalSorter, CycleError
from pathlib import Path
from typing import Optional
import json
import re

from .config import load_config, save_config
from .definitions import DATE_FORMAT
from .job_dependency import dependency_graph
from .storage import ensure_storage_dirs, jobs_dir

SNAPSHOT_KIND_KEY = "_autoslurm_snapshot_kind"
__all__ = ['get_bundle_filter_mode', 'set_bundle_filter_mode', 'bundle_snapshot_state', 'all_bundle_snapshots', 'list_saved_bundles', 'latest_bundle_summaries', 'bundle_snapshots', 'stale_bundle_snapshots', 'inactive_bundle_snapshots', 'nearest_bundle_filename', 'select_bundle_snapshot']


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
