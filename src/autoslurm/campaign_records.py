"""Opt-in immutable grouping of exact ordinary runs in this controller's store."""
from datetime import datetime, timezone
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import uuid

from .job_dependency import dependency_graph
from .errors import InvalidRequestError, SelectionError, DiagnosticError, DiagnosticCause, _campaign_failure
from .record_files import read_json, atomic_json
from .storage import storage_root

__all__ = ['create_campaign', 'load_campaign', 'list_campaigns']
_RECORD_LIMIT = 65536
_BUNDLE_LIMIT = 8 * 1024 * 1024


def _invalid(message, *, field='campaign', path=None, member=None):
    return InvalidRequestError(message, field=field, stage='validate_campaign',
        context={'path': str(path) if path is not None else None, 'resource': member})


def _name(value, field):
    if not isinstance(value, str) or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,95}', value) is None:
        raise _invalid('Use a nonempty name with at most 96 letters, digits, dots, underscores or hyphens.', field=field)
    return value


def _path(name):
    return storage_root() / 'campaigns' / (_name(name, 'name') + '.json')


def _text(value, field, limit):
    if not isinstance(value, str) or len(value.encode('utf-8')) > limit or any(ord(c) < 32 and c not in '\n\t' for c in value) or '\x7f' in value:
        raise _invalid('Campaign text must be bounded readable text without control characters.', field=field)
    return value


def _resolve_reference(value):
    if not isinstance(value, (str, Path)) or not str(value).strip() or any(ord(c) < 32 or ord(c) == 127 for c in str(value)):
        raise _invalid('Select an exact readable bundle path without control characters.', field='bundle_path')
    try:
        return Path(value).resolve()
    except OSError as error:
        raise SelectionError(_campaign_failure('The bundle reference could not be resolved.', path=value,
            code='resource_inaccessible', cause=DiagnosticCause.from_exception(error, detail='Local path resolution failed.'))) from error


def _bundle_definition(path):
    payload = read_json(path, max_bytes=_BUNDLE_LIMIT, context={'bundle_path': str(path)})
    if not isinstance(payload, dict) or not payload or any(not isinstance(job, dict) for job in payload.values()):
        raise _invalid('A campaign member must reference a nonempty ordinary bundle.', path=path)
    # Shared snapshot validation supplies the graph/record policy. It never queries Slurm.
    dependency_graph(payload)
    definition = copy.deepcopy(payload)
    for job in definition.values():
        reference = job.get('_autoslurm_submission')
        if isinstance(reference, dict) and all(isinstance(reference.get(k), str) and reference[k] for k in ('submission_id', 'receipt_path')):
            job.pop('id', None)
            for key in ('state', 'id', 'error'):
                reference.pop(key, None)
    try:
        encoded = json.dumps(definition, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    except ValueError as error:
        raise _invalid('Bundle values must contain finite JSON numbers.', path=path) from error
    return payload, hashlib.sha256(encoded).hexdigest()


def _validate_record(record, path):
    keys = {'format_version','campaign_id','name','revision','created_at','context','members'}
    if not isinstance(record, dict) or set(record) != keys or type(record.get('format_version')) is not int or record['format_version'] != 1:
        raise _invalid('Unsupported or malformed campaign record; only format_version 1 is supported.', path=path)
    if _name(record['name'], 'name') != path.stem or type(record['revision']) is not int or record['revision'] != 1:
        raise _invalid('Campaign name/revision does not match its immutable record.', path=path)
    if not isinstance(record['campaign_id'], str) or re.fullmatch('[0-9a-f]{32}', record['campaign_id']) is None:
        raise _invalid('Campaign identity must be a generated unique identifier.', path=path)
    _text(record['context'], 'context', 8192)
    if not isinstance(record['created_at'], str):
        raise _invalid('Campaign creation time must be an ISO timestamp.', path=path)
    try:
        created = datetime.fromisoformat(record['created_at'])
    except ValueError as error:
        raise _invalid('Campaign creation time must be an ISO timestamp.', path=path) from error
    if created.tzinfo is None:
        raise _invalid('Campaign creation time must include a timezone.', path=path)
    if not isinstance(record['members'], list) or not 1 <= len(record['members']) <= 2:
        raise _invalid('A campaign currently groups one or two members.', field='members', path=path)
    seen = set(); machines = set(); refs = set()
    for member in record['members']:
        if not isinstance(member, dict) or set(member) != {'member_id','machine','bundle_ref','bundle_sha256'}:
            raise _invalid('A member needs its exact identity, machine, bundle reference and digest.', path=path)
        identity = _name(member['member_id'], 'member_id'); machine = _name(member['machine'], 'machine')
        reference = member['bundle_ref']
        if (not isinstance(reference, str) or not reference or Path(reference).is_absolute()
                or any(ord(c) < 32 or ord(c) == 127 for c in reference)):
            raise _invalid('Bundle record references must be relative to the campaign directory.', path=path, member=identity)
        digest = member['bundle_sha256']
        if not isinstance(digest, str) or re.fullmatch('[0-9a-f]{64}', digest) is None:
            raise _invalid('A member needs the saved definition digest.', path=path, member=identity)
        resolved = str(_resolve_reference(path.parent / reference))
        if identity in seen or machine in machines or resolved in refs:
            raise _invalid('Member identities, machines and bundle references must be distinct.', path=path, member=identity)
        seen.add(identity); machines.add(machine); refs.add(resolved)
    return record


def _member_definition(member, campaign_path):
    path = _resolve_reference(Path(campaign_path).parent / member['bundle_ref'])
    payload, digest = _bundle_definition(path)
    if digest != member['bundle_sha256']:
        raise SelectionError(_campaign_failure('The campaign member definition changed; retain the original campaign.',
            path=path, member=member['member_id'], code='record_invalid'))
    for name, job in payload.items():
        execution = job.get('_autoslurm_execution', {})
        if not isinstance(execution, dict):
            raise _invalid('Recorded execution metadata must be a mapping.', path=path, member=member['member_id'])
        actual = execution.get('machine', job.get('machine'))
        if actual != member['machine'] or job.get('machine', actual) != member['machine']:
            raise _invalid('Every member job must record its selected machine explicitly.', path=path, member=member['member_id'])
    return path, payload


def create_campaign(name, members, *, context=''):
    """Group exact existing definitions offline. No copies, discovery or submission.

    members: one/two dictionaries with member_id, machine and bundle_path.
    Immutable v1 records contain relative controller-file references and canonical
    JSON definition digests. Changed definitions require a new campaign name.
    """
    path = _path(name)
    if not isinstance(members, list) or not 1 <= len(members) <= 2:
        raise _invalid('Supply one or two campaign members.', field='members')
    stored = []
    for item in members:
        if not isinstance(item, dict) or set(item) != {'member_id','machine','bundle_path'}:
            raise _invalid('Each member needs member_id, machine and exact bundle_path.', field='members')
        _name(item['member_id'], 'member_id'); _name(item['machine'], 'machine')
        if not isinstance(item['bundle_path'], (str, Path)) or not str(item['bundle_path']).strip():
            raise _invalid('Select an exact bundle path.', field='bundle_path')
        reference = _resolve_reference(item['bundle_path'])
        _, digest = _bundle_definition(reference)
        member = {'member_id': item['member_id'], 'machine': item['machine'],
                  'bundle_ref': os.path.relpath(reference, path.parent), 'bundle_sha256': digest}
        _member_definition(member, path)
        stored.append(member)
    record = {'format_version': 1, 'campaign_id': uuid.uuid4().hex, 'name': name, 'revision': 1,
              'created_at': datetime.now(timezone.utc).isoformat(), 'context': context, 'members': stored}
    _validate_record(record, path)
    if len(json.dumps(record).encode('utf-8')) > _RECORD_LIMIT:
        raise _invalid('Campaign record exceeds 64 KiB.', path=path)
    atomic_json(path, record, exclusive=True)
    return {**record, 'campaign_path': str(path)}


def load_campaign(name):
    """Read an immutable controller-local record; member failures are inspected separately."""
    path = _path(name)
    record = read_json(path, max_bytes=_RECORD_LIMIT, context={'path': str(path), 'resource': 'campaign'})
    _validate_record(record, path)
    return {**record, 'campaign_path': str(path)}


def list_campaigns():
    """Discover saved campaigns without network; unreadable entries retain diagnostics."""
    directory = storage_root() / 'campaigns'
    try:
        with os.scandir(directory) as entries:
            paths = sorted(Path(entry.path) for entry in entries if entry.name.endswith('.json') and not entry.name.startswith('.'))
    except FileNotFoundError:
        return []
    except OSError as error:
        raise SelectionError(_campaign_failure('Campaign discovery failed.', path=directory,
                                               code='resource_inaccessible', cause=DiagnosticCause.from_exception(error, detail='Campaign directory enumeration failed.'))) from error
    result = []
    for path in paths:
        try:
            record = load_campaign(path.stem)
            result.append({'name': record['name'], 'campaign_id': record['campaign_id'],
                'created_at': record['created_at'], 'members': len(record['members']),
                'campaign_path': str(path), 'state': 'available', 'diagnostic': None})
        except DiagnosticError as error:
            result.append({'name': path.stem, 'campaign_path': str(path), 'state': 'unavailable',
                           'diagnostic': error.diagnostic.to_dict()})
    return result
