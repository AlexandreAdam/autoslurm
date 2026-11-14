"""Local snapshot discovery and the shared draft/latest/exact selection policy."""

from datetime import datetime
from pathlib import Path
from typing import Optional
import json
import os
import re
import stat

from .config import load_config, save_config, _bundle_filter_mode
from .definitions import DATE_FORMAT
from .errors import ConfigurationError, InvalidRequestError, SelectionError, DiagnosticCause, selection_failure
from .job_dependency import dependency_graph
from .storage import config_file_path, jobs_dir

SNAPSHOT_KIND_KEY = "_autoslurm_snapshot_kind"
__all__ = ['get_bundle_filter_mode', 'set_bundle_filter_mode', 'bundle_snapshot_state', 'all_bundle_snapshots', 'list_saved_bundles', 'latest_bundle_summaries', 'bundle_snapshots', 'stale_bundle_snapshots', 'inactive_bundle_snapshots', 'nearest_bundle_filename', 'select_bundle_snapshot']


def get_bundle_filter_mode() -> str:
    """
    Return the filter; only an absent configuration defaults to active.
    """
    try:
        cfg = load_config()
    except ConfigurationError as error:
        if error.diagnostic.code == 'resource_missing':
            return 'active'
        raise
    return _bundle_filter_mode(cfg.get('bundle_filter_mode', 'active'), path=config_file_path())


def set_bundle_filter_mode(mode: str) -> str:
    """
    Persist global bundle visibility filter mode.
    """
    normalized = _bundle_filter_mode(mode, path=config_file_path())
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
        return datetime.fromtimestamp(_file_metadata(path).st_mtime)


def _selection_error(*, field, stage='select_snapshot', problem='invalid', summary=None, path=None,
                     cause=None, detail=None, context=None):
    facts = {**(context or {}), 'field': field}
    if path is not None:
        facts['bundle_path' if field == 'bundle_path' else 'path'] = str(path)
    return SelectionError(selection_failure(stage=stage, problem=problem, summary=summary,
        context=facts, cause=DiagnosticCause.from_exception(cause, detail=detail) if cause is not None else None))


def _file_metadata(path):
    try:
        metadata = path.stat()
    except FileNotFoundError as error:
        # A dangling link is unavailable, rather than an absent record.
        try:
            path.lstat()
        except FileNotFoundError:
            problem = 'missing'
        except OSError as metadata_error:
            raise _selection_error(field='bundle_path', problem='unreadable', path=path,
                                   cause=metadata_error) from metadata_error
        else:
            problem = 'unreadable'
        raise _selection_error(field='bundle_path', problem=problem, path=path, cause=error) from error
    except OSError as error:
        raise _selection_error(field='bundle_path', problem='unreadable', path=path, cause=error) from error
    if not stat.S_ISREG(metadata.st_mode):
        raise _selection_error(field='bundle_path', problem='unreadable', path=path,
                               summary='The selected snapshot is not a regular file.')
    return metadata


def _snapshot_files():
    """Enumerate once without creating storage or suppressing directory errors."""
    directory = jobs_dir()
    try:
        with os.scandir(directory) as entries:
            return [Path(entry.path) for entry in entries
                    if entry.name.endswith('.json') and not entry.name.startswith('.')]
    except FileNotFoundError as error:
        try:
            directory.lstat()
        except FileNotFoundError:
            return []
        except OSError as metadata_error:
            raise _selection_error(field='jobs_directory', stage='discover_snapshots', problem='unreadable',
                                   path=directory, cause=metadata_error) from metadata_error
        raise _selection_error(field='jobs_directory', stage='discover_snapshots', problem='unreadable',
                               path=directory, cause=error) from error
    except OSError as error:
        raise _selection_error(field='jobs_directory', stage='discover_snapshots', problem='unreadable',
                               path=directory, cause=error) from error


def _read_snapshot(path):
    """Read regular UTF-8 JSON only; never wait on a FIFO changed during lookup."""
    _file_metadata(path)
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NONBLOCK', 0))
        with os.fdopen(descriptor, 'r', encoding='utf-8') as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise _selection_error(field='bundle_path', stage='read_snapshot', problem='unreadable', path=path,
                                       summary='The selected snapshot is not a regular file.')
            payload = json.load(stream)
    except FileNotFoundError as error:
        raise _selection_error(field='bundle_path', stage='read_snapshot', problem='missing', path=path, cause=error) from error
    except OSError as error:
        raise _selection_error(field='bundle_path', stage='read_snapshot', problem='unreadable', path=path, cause=error) from error
    except (json.JSONDecodeError, UnicodeError) as error:
        detail = (f'Invalid JSON at line {error.lineno}, column {error.colno}.'
                  if isinstance(error, json.JSONDecodeError) else 'Saved bundles must contain UTF-8 JSON text.')
        raise _selection_error(field='bundle_path', stage='read_snapshot', problem='corrupt', path=path,
                               cause=error, detail=detail) from error
    if not isinstance(payload, dict):
        raise _selection_error(field='bundle_path', stage='validate_snapshot', problem='corrupt', path=path,
                               summary='A saved bundle must contain a dictionary of jobs.')
    return payload


def _failed_snapshot(entry, error):
    states = {'resource_missing': 'missing', 'resource_inaccessible': 'unavailable'}
    return {**entry, 'state': states.get(error.diagnostic.code, 'broken'),
            'diagnostic': error.diagnostic.to_dict()}


def _analyze_bundle_file(filename: Path, *, strict=False) -> dict:
    """Keep per-entry read/graph evidence; strict submission raises the same diagnosis."""
    saved_date = _snapshot_date(filename, fallback_to_mtime=True)
    bundle_name = filename.stem.rsplit('_', 1)[0] if re.fullmatch(r'.+_\d{14}', filename.stem) else filename.stem
    entry = {'bundle': bundle_name, 'date': saved_date, 'path': filename,
             'jobs': None, 'job_count': None, 'submitted_count': None}
    try:
        payload = _read_snapshot(filename)
    except SelectionError as error:
        if strict:
            raise
        return _failed_snapshot(entry, error)
    entry.update(jobs=list(payload), job_count=len(payload))
    if all(isinstance(job, dict) for job in payload.values()):
        entry['submitted_count'] = _submitted_job_count(payload)
    try:
        dependency_graph(payload)
    except InvalidRequestError as error:
        diagnostic = selection_failure(stage='validate_snapshot', problem='corrupt',
            summary=error.diagnostic.summary,
            context={**error.diagnostic.context, 'bundle_path': str(filename)}, cause=error.diagnostic.cause)
        failure = SelectionError(diagnostic)
        if strict:
            raise failure from error
        return _failed_snapshot(entry, failure)
    snapshot_kind = _snapshot_kind_from_payload(payload)
    active = snapshot_kind == 'submission' and (entry['submitted_count'] > 0
        or any(job.get('_autoslurm_submission') for job in payload.values()))
    return {**entry, 'state': 'active' if active else 'ready_to_go',
            'snapshot_kind': snapshot_kind, 'diagnostic': None}


def bundle_snapshot_state(bundle_path: str | Path, *, strict=False) -> dict:
    """
    Return metadata for an exact regular file, or raise its diagnosis in strict mode.
    """
    if type(strict) is not bool:
        raise _selection_error(field='strict', summary='strict must be a boolean.')
    path = _selected_path(bundle_path)
    _file_metadata(path)
    return _analyze_bundle_file(path, strict=strict)


def _is_placeholder_file(path: Path) -> bool:
    return path.name.startswith(".")


def _all_snapshot_entries() -> list[dict]:
    entries: list[dict] = []
    for filename in _snapshot_files():
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
    entries.sort(key=lambda entry: (entry['date'], entry['path'].name), reverse=True)
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
    - keep the latest broken/unavailable/missing entry alongside any history
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
        if latest.get('state') in {'broken', 'unavailable', 'missing'}:
            selected.append(latest)
    selected.sort(key=lambda entry: entry["date"], reverse=True)
    return selected


def _stale_snapshots(entries: list[dict]) -> list[dict]:
    """
    Stale snapshots are hidden entries with known submission counts.
    """
    visible = _active_visible_snapshots(entries)
    visible_paths = {str(entry["path"]) for entry in visible}
    stale = [entry for entry in entries if str(entry["path"]) not in visible_paths
             and entry.get('submitted_count') is not None]
    stale.sort(key=lambda entry: entry["date"], reverse=True)
    return stale


def list_saved_bundles(
    desired_date: Optional[datetime] = None,
    bundle_name: Optional[str] = None,
) -> list[dict]:
    """
    List snapshots with jobs/counts/state and a per-entry diagnostic when needed.

    Entries are ordered by proximity to a reference date. Unknown contents/counts
    are None, distinct from the empty list and zero counts of an empty draft.

    If ``bundle_name`` is provided, only versions of that bundle are returned.
    Otherwise every bundle under the jobs directory is included.
    """
    entries = _snapshot_paths(bundle_name, desired_date)
    for entry in entries:
        entry.update(_analyze_bundle_file(entry['path']))
    return entries


def _snapshot_paths(bundle_name=None, desired_date=None):
    """Filename-only candidates keep exact/nearest selection free of payload reads."""
    desired_date = _reference_date(desired_date)
    _bundle_name(bundle_name)
    entries = []
    for path in _snapshot_files():
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
    return sorted(entries, key=lambda entry: (entry['distance'], entry['date'], entry['path'].name))


def latest_bundle_summaries(desired_date: Optional[datetime] = None) -> list[dict]:
    """
    Return the newest saved bundle for each bundle name.

    The entries are sorted by proximity to ``desired_date`` (default: now).
    """
    desired_date = _reference_date(desired_date)
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
    _reference_date(desired_date)
    all_entries = _all_snapshot_entries()
    mode = get_bundle_filter_mode()
    if mode == "active":
        return _active_visible_snapshots(all_entries)
    return all_entries


def stale_bundle_snapshots() -> list[dict]:
    """
    Return superseded snapshots with known counts, preserving unreadable evidence.
    """
    return _stale_snapshots(_all_snapshot_entries())


def inactive_bundle_snapshots() -> list[dict]:
    """
    Return the same superseded known-count snapshots used by default cleanup.
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


def _reference_date(value):
    if value is not None and (not isinstance(value, datetime) or value.utcoffset() is not None):
        raise _selection_error(field='desired_date', summary='Reference date must be a naive datetime matching saved snapshot timestamps.')
    return datetime.now() if value is None else value


def _bundle_name(value):
    if value is not None and (not isinstance(value, str) or not value.strip()):
        raise _selection_error(field='name', summary='Bundle name must be a nonempty string.')


def _selected_path(value):
    if not isinstance(value, (str, Path)) or not str(value).strip():
        raise _selection_error(field='bundle_path', summary='Bundle path must be a nonempty string or Path.')
    return Path(value)


def select_bundle_snapshot(name=None, *, bundle_path=None, latest=False, index=None, desired_date=None, prefer_draft=True):
    """One selection policy for explicit paths, UI indices, draft/latest and nearest dates."""
    _bundle_name(name)
    _reference_date(desired_date)
    if type(latest) is not bool or type(prefer_draft) is not bool:
        raise _selection_error(field='latest/prefer_draft', summary='latest and prefer_draft must be booleans.')
    if index is not None and (type(index) is not int or index < 1):
        raise _selection_error(field='index', summary='Bundle index must be a positive integer.')
    if sum([bundle_path is not None, latest, index is not None]) > 1:
        raise _selection_error(field='selector', summary='Select only one of bundle_path, latest or index.')
    if (latest or index is not None) and name is not None:
        raise _selection_error(field='selector', summary='latest/index selectors do not take a bundle name.')
    if bundle_path is not None:
        path = _selected_path(bundle_path)
        _file_metadata(path)
        if name is None:
            if "_" not in path.stem:
                raise _selection_error(field='name', path=path, summary='Unable to infer bundle name; provide an explicit name.')
            name = path.stem.rsplit("_", 1)[0]
        return {"bundle": name, "path": path, "date": _snapshot_date(path, fallback_to_mtime=True)}
    if index is not None:
        rows = bundle_snapshots(desired_date)
        if not 1 <= index <= len(rows):
            raise _selection_error(field='index', summary=f'Bundle index {index!r} is out of range.')
        return rows[index - 1]
    if name is None and not latest:
        raise _selection_error(field='selector', summary='Select a bundle name, explicit path, latest or index.')
    if prefer_draft and desired_date is None:
        entries = bundle_snapshots() if latest else [row for row in all_bundle_snapshots() if row['bundle'] == name]
        if entries and entries[0].get('diagnostic') is not None:
            return entries[0]
        drafts = [row for row in entries if row.get('state') == 'ready_to_go']
        if drafts:
            return max(drafts, key=lambda row: row["date"])
    candidates = latest_bundle_summaries(desired_date) if latest else _snapshot_paths(name, desired_date)
    if not candidates:
        raise _selection_error(field='name', problem='missing', path=jobs_dir(),
            context={'bundle': name}, summary=f'No files found with name {name!r} in directory {jobs_dir()}')
    return max(candidates, key=lambda row: row["date"]) if latest else candidates[0]
