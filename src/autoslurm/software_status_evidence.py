"""Validate software observations and attach host-owned plain diagnostics."""

import copy
from pathlib import PurePosixPath
import re

from .errors import DiagnosticCause, _software_status_failure, _text

_STATES = ('observed', 'missing', 'not_a_repository', 'outside_root', 'unavailable')
_PROBLEMS = ('invalid_argument', 'configuration_invalid', 'resource_missing', 'resource_inaccessible',
             'command_unavailable', 'command_timeout', 'command_failed', 'operation_interrupted',
             'protocol_invalid', 'compatibility_mismatch', 'observation_unavailable')
_STAGES = ('read_software_root', 'read_project', 'select_project', 'git_repository', 'git_commit',
           'git_branch', 'git_status', 'environment_python', 'read_environment', 'environment_identity',
           'read_distribution', 'read_source_metadata', 'source_commit', 'source_status')


def _commit(value):
    return value is None or isinstance(value, str) and re.fullmatch('[0-9a-f]{40}|[0-9a-f]{64}', value) is not None


def _plain(value, size=4096):
    try:
        return isinstance(value, str) and bool(value) and len(value.encode('utf-8')) <= size and all(ord(c) >= 32 and ord(c) != 127 for c in value)
    except UnicodeError:
        return False


def _diagnostic(item, context, default_stage, default_problem):
    failure = item.get('failure')
    if failure is None:
        return _software_status_failure(default_problem, default_stage, context)
    if (not isinstance(failure, dict) or failure.get('stage') not in _STAGES or failure.get('problem') not in _PROBLEMS
            or not isinstance(failure.get('kind'), str) or re.fullmatch('[A-Za-z][A-Za-z0-9_.-]{0,63}', failure['kind']) is None
            or any(failure.get(key) is not None and (type(failure[key]) is not int or not -(2**63) <= failure[key] < 2**63)
                   for key in ('errno', 'returncode'))):
        return _software_status_failure('protocol_invalid', default_stage, context)
    cause = DiagnosticCause(failure['kind'], 'Read-only software observation did not complete; raw output is omitted.',
                            failure.get('errno'), failure.get('returncode'))
    if failure['stage'].startswith('git_') or failure['stage'] in ('source_commit', 'source_status'):
        context = {**context, 'command': 'git', 'executable': 'git'}
        if isinstance(item.get('source_path'), str):
            context['source'] = item['source_path']
    return _software_status_failure(failure['problem'], failure['stage'], context, cause)


def _attach(item, context, stage, problem):
    if item.get('state') == 'missing' and 'failure' in item:
        item['state'] = 'unavailable'
        diagnostic = _software_status_failure('protocol_invalid', stage, context)
    else:
        diagnostic = _diagnostic(item, context, stage, problem)
    item.pop('failure', None)
    item['diagnostic'] = diagnostic.to_dict()
    item['error'] = diagnostic.summary


def validate_observation(result, root, project, limit, context, names, python_path):
    """Bad operation identity raises; bad items become unavailable beside good ones."""
    if (not isinstance(result, dict) or type(result.get('version')) is not int or result['version'] != 1
            or result.get('software_root') != root or result.get('state') not in ('observed', 'missing', 'unavailable')
            or not _plain(result.get('observed_at'), 128) or type(result.get('truncated')) is not bool
            or not isinstance(result.get('projects'), list) or len(result['projects']) > limit):
        raise ValueError('Invalid software observation identity or shape.')
    result = copy.deepcopy({key: value for key, value in result.items() if key in
        {'version', 'software_root', 'state', 'observed_at', 'projects', 'truncated', 'environment', 'failure'}})
    if result['state'] == 'observed' and 'failure' in result:
        result.update(state='unavailable', failure={'stage': 'read_software_root', 'problem': 'protocol_invalid',
                                                  'kind': 'SoftwareProbe', 'errno': None, 'returncode': None})
    if result['state'] != 'observed':
        _attach(result, context, 'read_software_root', 'resource_missing' if result['state'] == 'missing' else 'resource_inaccessible')
    else:
        result.pop('diagnostic', None)
        result.pop('error', None)
        result.pop('failure', None)
    projects, seen = [], set()
    for index, row in enumerate(result['projects']):
        if isinstance(row, dict):
            row = {key: value for key, value in row.items() if key in {'name', 'path', 'state', 'commit', 'branch',
                   'dirty', 'bare', 'changed_paths', 'changes', 'changes_truncated', 'failure'}}
        name = row.get('name') if isinstance(row, dict) else None
        safe_name = (_plain(name, 512) and not PurePosixPath(name).is_absolute()
                     and '..' not in PurePosixPath(name).parts and '\\' not in name)
        valid_name = safe_name and name not in seen and (project is None or name == project)
        name = name if safe_name else project or f'<project {index + 1}>'
        path = str(PurePosixPath(root) / name) if safe_name else root
        facts = {**context, 'project': name, 'path': path, 'resource': 'checkout'}
        valid = (valid_name and row.get('path') == path and row.get('state') in _STATES
                 and _commit(row.get('commit')) and (row.get('branch') is None or _plain(row['branch'], 512))
                 and (row.get('dirty') is None or type(row['dirty']) is bool)
                 and ('changed_paths' not in row or type(row['changed_paths']) is int and 0 <= row['changed_paths'] <= 2**63 - 1)
                 and ('changes' not in row or isinstance(row['changes'], list) and len(row['changes']) <= 20
                      and all(isinstance(line, str) for line in row['changes']))
                 and ('changes_truncated' not in row or type(row['changes_truncated']) is bool))
        if valid and row['state'] == 'observed':
            valid = (type(row.get('bare')) is bool and row.get('commit') is not None
                     and (row['bare'] or type(row.get('dirty')) is bool) and 'failure' not in row)
        if not valid:
            row = {'name': name, 'path': path, 'state': 'unavailable', 'commit': None, 'branch': None, 'dirty': None}
            _attach(row, facts, 'read_project', 'protocol_invalid')
        elif row['state'] != 'observed':
            row = dict(row)
            row['dirty'] = None
            _attach(row, facts, 'read_project', {'missing': 'resource_missing', 'outside_root': 'invalid_argument',
                    'not_a_repository': 'resource_inaccessible'}.get(row['state'], 'observation_unavailable'))
        else:
            row = dict(row)
            row.pop('diagnostic', None)
            row.pop('error', None)
        if row.get('branch'):
            row['branch'] = _text(row['branch'])
        if isinstance(row.get('changes'), list):
            row['changes'] = [_text(line) for line in row['changes'][:20] if isinstance(line, str)]
        projects.append(row)
        seen.add(name)
    if project is not None and not projects and result['state'] == 'observed':
        row = {'name': project, 'path': str(PurePosixPath(root) / project), 'state': 'unavailable',
               'commit': None, 'branch': None, 'dirty': None}
        _attach(row, {**context, 'project': project, 'path': row['path']}, 'read_project',
                'observation_unavailable' if result['truncated'] else 'protocol_invalid')
        projects.append(row)
    result['projects'] = projects
    if names is not None:
        environment = result.get('environment')
        if isinstance(environment, dict):
            environment = {key: value for key, value in environment.items() if key in {'state', 'python', 'prefix',
                'python_version', 'packages', 'markers', 'failure', 'selected_python', 'identity_verified'}}
        facts = {**context, 'path': python_path, 'executable': python_path, 'field': 'venv_path', 'resource': 'environment'}
        valid = isinstance(environment, dict) and environment.get('state') in ('observed', 'unavailable')
        if valid and environment['state'] == 'observed':
            valid = (isinstance(environment.get('packages'), dict) and isinstance(environment.get('markers'), dict)
                     and isinstance(environment.get('prefix'), str) and python_path is not None
                     and environment.get('selected_python') == python_path and environment.get('identity_verified') is True)
        if not valid:
            environment = {'state': 'unavailable'}
            _attach(environment, facts, 'read_environment', 'protocol_invalid')
        elif environment['state'] == 'unavailable':
            _attach(environment, facts, 'environment_python', 'observation_unavailable')
        else:
            environment.pop('diagnostic', None)
            environment.pop('failure', None)
            environment.pop('error', None)
            packages = {}
            for name in names:
                package = environment['packages'].get(name)
                if isinstance(package, dict):
                    package = {key: value for key, value in package.items() if key in {'state', 'version', 'location',
                        'source_commit', 'editable', 'source_dirty', 'source_path', 'metadata_warning', 'failure'}}
                facts_package = {**facts, 'resource': name, 'field': f'packages.{name}'}
                valid = (isinstance(package, dict) and package.get('state') in ('installed', 'missing', 'unavailable')
                         and (_plain(package.get('version'), 256) if package['state'] == 'installed' else package.get('version') is None))
                if valid and (not _commit(package.get('source_commit'))
                        or ('editable' in package and type(package['editable']) is not bool)
                        or (package.get('source_dirty') is not None and type(package['source_dirty']) is not bool)
                        or any(package.get(key) is not None and not _plain(package[key]) for key in ('location', 'source_path'))):
                    if package['state'] != 'installed':
                        valid = False
                    else:
                        package.update(source_commit=None, editable=True, source_dirty=None,
                            metadata_warning='Source metadata could not be verified.',
                            failure={'stage': 'read_source_metadata', 'problem': 'protocol_invalid', 'kind': 'DistributionMetadata',
                                     'errno': None, 'returncode': None})
                        package.pop('location', None)
                        package.pop('source_path', None)
                if not valid:
                    missing = package is None
                    package = {'state': 'unavailable'}
                    _attach(package, facts_package, 'read_distribution', 'observation_unavailable' if missing else 'protocol_invalid')
                elif package['state'] != 'installed' or 'failure' in package:
                    _attach(package, facts_package, 'read_distribution', 'resource_missing' if package['state'] == 'missing' else 'observation_unavailable')
                else:
                    package.pop('diagnostic', None)
                if package.get('version'):
                    package['version'] = _text(package['version'], 256)
                for key in ('location', 'source_path'):
                    if package.get(key):
                        package[key] = _text(package[key])
                if package.get('metadata_warning'):
                    package['metadata_warning'] = 'Source metadata could not be fully verified.'
                packages[name] = package
            environment['packages'] = packages
            markers = environment['markers']
            if any(not isinstance(value, str) or (value and not _plain(value, 512)) for value in markers.values()):
                environment['markers'] = {key: value for key, value in markers.items() if isinstance(value, str) and (not value or _plain(value, 512))}
                _attach(environment, facts, 'read_environment', 'protocol_invalid')
            if any(key in environment and not _plain(environment[key], 512) for key in ('python', 'python_version')):
                for key in ('python', 'python_version'):
                    if key in environment and not _plain(environment[key], 512):
                        environment.pop(key)
                _attach(environment, facts, 'read_environment', 'protocol_invalid')
        result['environment'] = environment
    else:
        result.pop('environment', None)
    return result


def add_compatibility_diagnostics(result, context):
    for check in result['checks']:
        if check['state'] != 'compatible':
            check['diagnostic'] = _software_status_failure(
                'compatibility_mismatch' if check['state'] == 'mismatch' else 'observation_unavailable',
                'compare_environment', {**context, 'resource': check['name']}, summary=check['message']).to_dict()
    return result
