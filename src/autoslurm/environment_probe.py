"""Standalone distribution metadata probe; never imports scientific packages."""

import importlib.metadata
import json
import os
import platform
import subprocess
import sys
from urllib.parse import unquote, urlsplit


def _metadata_failure(stage, error=None, *, returncode=None):
    problem = ('command_timeout' if isinstance(error, subprocess.TimeoutExpired) else
               'command_unavailable' if isinstance(error, (FileNotFoundError, PermissionError)) else
               'resource_inaccessible' if isinstance(error, OSError) else
               'operation_interrupted' if returncode is not None and returncode < 0 else
               'command_failed' if returncode else 'protocol_invalid')
    return {'stage': stage, 'problem': problem, 'kind': type(error).__name__ if error is not None else 'DistributionMetadata',
            'errno': getattr(error, 'errno', None), 'returncode': returncode}


def _unique_metadata(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Repeated source metadata key.')
        result[key] = value
    return result


def _source_query(source, arguments):
    response = subprocess.run(['git', '-C', source, *arguments], capture_output=True, text=True, timeout=5,
        env={**os.environ, 'GIT_OPTIONAL_LOCKS': '0', 'GIT_TERMINAL_PROMPT': '0'})
    if (type(response.returncode) is not int or not -(2**63) <= response.returncode < 2**63
            or not isinstance(response.stdout, str) or len(response.stdout.encode('utf-8')) > 65536):
        raise ValueError('Invalid source metadata response.')
    return response


def inspect_environment(names):
    result = {'state': 'observed', 'python': sys.executable, 'prefix': sys.prefix,
              'python_version': platform.python_version(), 'packages': {},
              'markers': {'implementation_name': sys.implementation.name,
                          'implementation_version': platform.python_version(),
                          'os_name': os.name, 'platform_machine': platform.machine(),
                          'platform_python_implementation': platform.python_implementation(),
                          'platform_release': platform.release(), 'platform_system': platform.system(),
                          'platform_version': platform.version(), 'python_full_version': platform.python_version(),
                          'python_version': '.'.join(platform.python_version_tuple()[:2]),
                          'sys_platform': sys.platform, 'extra': ''}}
    for name in names:
        try:
            distribution = importlib.metadata.distribution(name)
            version = distribution.version
            location = str(distribution.locate_file(''))
            if not isinstance(version, str) or not version or len(version) > 256:
                raise ValueError('Invalid installed distribution version.')
        except importlib.metadata.PackageNotFoundError:
            result['packages'][name] = {'state': 'missing'}
            continue
        except (OSError, ValueError, UnicodeError) as error:
            result['packages'][name] = {'state': 'unavailable', 'failure': _metadata_failure('read_distribution', error)}
            continue
        package = {'state': 'installed', 'version': version, 'location': location,
                   'source_commit': None, 'editable': False, 'source_dirty': None}
        stage = 'read_source_metadata'
        try:
            text = distribution.read_text('direct_url.json')
            if text is not None and (not isinstance(text, str) or len(text.encode('utf-8')) > 65536):
                raise ValueError('Invalid source metadata size.')
            direct = json.loads(text, object_pairs_hook=_unique_metadata) if text else {}
            if (not isinstance(direct, dict) or not isinstance(direct.get('vcs_info', {}), dict)
                    or not isinstance(direct.get('dir_info', {}), dict)
                    or type(direct.get('dir_info', {}).get('editable', False)) is not bool
                    or not isinstance(direct.get('url', ''), str)):
                raise ValueError('Invalid source metadata shape.')
            commit = direct.get('vcs_info', {}).get('commit_id')
            if commit is not None and (not isinstance(commit, str) or len(commit) not in (40, 64)
                                      or any(c not in '0123456789abcdef' for c in commit)):
                raise ValueError('Invalid source commit.')
            package['source_commit'] = commit
            package['editable'] = direct.get('dir_info', {}).get('editable', False)
            url = urlsplit(direct.get('url', ''))
            if package['editable'] and url.scheme == 'file' and not url.netloc:
                source = unquote(url.path)
                package['source_path'] = source
                stage = 'source_commit'
                response = _source_query(source, ['rev-parse', '--verify', 'HEAD'])
                if response.returncode:
                    package['failure'] = _metadata_failure(stage, returncode=response.returncode)
                    package['metadata_warning'] = 'Editable source has no readable Git identity.'
                else:
                    commit = response.stdout.strip()
                    if len(commit) not in (40, 64) or any(c not in '0123456789abcdef' for c in commit):
                        raise ValueError('Invalid source commit.')
                    package['source_commit'] = commit
                    stage = 'source_status'
                    changes = _source_query(source, ['status', '--porcelain=v1', '--untracked-files=normal', '--ignore-submodules=all'])
                    if changes.returncode:
                        package['failure'] = _metadata_failure(stage, returncode=changes.returncode)
                        package['metadata_warning'] = 'Editable source cleanliness could not be verified.'
                    else:
                        package['source_dirty'] = bool(changes.stdout.strip())
        except (OSError, ValueError, UnicodeError, RecursionError, subprocess.TimeoutExpired) as error:
            package['metadata_warning'] = 'Source metadata could not be verified.'
            package['failure'] = _metadata_failure(stage, error)
        result['packages'][name] = package
    return result
