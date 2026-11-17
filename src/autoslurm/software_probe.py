"""Standalone, read-only Git probe; also sent over SSH without installation.

Keep this module standard-library-only and free of AutoSlurm imports. Merely
reading it or importing it performs no filesystem or process operations.
"""

from datetime import datetime, timezone
import os
import errno
import stat
import json
from pathlib import Path
import subprocess
import time


class _ProbeFailure(Exception):
    def __init__(self, stage, *, problem='protocol_invalid', error=None, returncode=None):
        if error is not None:
            problem = ('command_timeout' if isinstance(error, subprocess.TimeoutExpired) else
                       'protocol_invalid' if isinstance(error, (ValueError, RecursionError, UnicodeError)) else
                       'command_unavailable' if isinstance(error, (FileNotFoundError, PermissionError)) else
                       'resource_inaccessible')
        self.facts = {'stage': stage, 'problem': problem, 'kind': type(error).__name__ if error is not None else 'SoftwareProbe',
                      'errno': getattr(error, 'errno', None), 'returncode': returncode}
        super().__init__('Software observation failed.')


def _metadata(path):
    try:
        return path.stat()
    except OSError as error:
        if error.errno in {errno.ENOENT, errno.ENOTDIR}:
            return None
        raise


def _git(path, *arguments):
    stage = ('git_repository' if '--is-bare-repository' in arguments else
             'git_commit' if 'rev-parse' in arguments else
             'git_branch' if 'symbolic-ref' in arguments else 'git_status')
    try:
        result = subprocess.run(
            ['git', '-C', str(path), *arguments], capture_output=True, text=True,
            timeout=5, env={**os.environ, 'GIT_OPTIONAL_LOCKS': '0', 'GIT_TERMINAL_PROMPT': '0'})
    except (OSError, subprocess.TimeoutExpired, UnicodeError) as error:
        raise _ProbeFailure(stage, error=error) from error
    if (type(result.returncode) is not int or not -(2**63) <= result.returncode < 2**63
            or not isinstance(result.stdout, str)):
        raise _ProbeFailure(stage)
    try:
        if len(result.stdout.encode('utf-8')) > 65536:
            raise _ProbeFailure(stage)
    except UnicodeError as error:
        raise _ProbeFailure(stage, error=error) from error
    if result.returncode and not (stage == 'git_branch' and result.returncode == 1):
        raise _ProbeFailure(stage, problem='operation_interrupted' if result.returncode < 0 else 'command_failed',
                            returncode=result.returncode)
    return result.returncode, result.stdout


def _project_status(root, path, name):
    result = {"name": name, "path": str(path), "state": "unavailable",
              "commit": None, "branch": None, "dirty": None}
    try:
        try:
            path.resolve().relative_to(root.resolve())
        except ValueError:
            return {**result, 'state': 'outside_root', 'error': 'Project resolves outside software_root.',
                    'failure': {'stage': 'select_project', 'problem': 'invalid_argument', 'kind': 'ProjectBoundary', 'errno': None, 'returncode': None}}
        if _metadata(path) is None:
            return {**result, "state": "missing"}
        if not (_metadata(path / '.git') or (_metadata(path / 'HEAD') and _metadata(path / 'objects'))):
            return {**result, "state": "not_a_repository"}
        code, bare = _git(path, "rev-parse", "--is-bare-repository")
        if code or bare.strip() not in {"true", "false"}:
            raise _ProbeFailure('git_repository')
        result["bare"] = bare.strip() == "true"
        code, commit = _git(path, "rev-parse", "--verify", "HEAD")
        commit = commit.strip()
        if code or len(commit) not in {40, 64} or any(c not in "0123456789abcdef" for c in commit):
            raise _ProbeFailure('git_commit')
        result["commit"] = commit
        code, branch = _git(path, "symbolic-ref", "--quiet", "--short", "HEAD")
        if code not in {0, 1}:
            raise _ProbeFailure('git_branch')
        if code == 0 and (not branch.strip() or len(branch.strip().splitlines()) != 1):
            raise _ProbeFailure('git_branch')
        result["branch"] = branch.strip() if code == 0 else None
        if not result["bare"]:
            code, changes = _git(path, "status", "--porcelain=v1", "--untracked-files=normal", "--ignore-submodules=all")
            if code:
                raise _ProbeFailure('git_status')
            lines = changes.splitlines()
            result.update(dirty=bool(lines), changed_paths=len(lines),
                          changes=lines[:20], changes_truncated=len(lines) > 20)
        return {**result, "state": "observed"}
    except _ProbeFailure as error:
        return {**result, 'error': 'Project inspection failed; known commit evidence is retained.', 'failure': error.facts}
    except OSError as error:
        return {**result, 'error': 'Project metadata cannot be read.',
                'failure': {'stage': 'read_project', 'problem': 'resource_inaccessible', 'kind': type(error).__name__,
                            'errno': error.errno, 'returncode': None}}


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Repeated metadata key.')
        result[key] = value
    return result


def _environment_status(python_path, script):
    result = {'state': 'unavailable', 'error': 'The selected environment could not be inspected.'}
    try:
        if not python_path:
            raise _ProbeFailure('environment_python', problem='configuration_invalid')
        try:
            response = subprocess.run([python_path, '-B', '-c', script], capture_output=True,
                text=True, timeout=25, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
        except (OSError, subprocess.TimeoutExpired, UnicodeError) as error:
            raise _ProbeFailure('environment_python', error=error) from error
        if type(response.returncode) is not int or not -(2**63) <= response.returncode < 2**63:
            raise _ProbeFailure('environment_python')
        if response.returncode:
            raise _ProbeFailure('environment_python', problem='operation_interrupted' if response.returncode < 0 else 'command_failed',
                                returncode=response.returncode)
        try:
            if not isinstance(response.stdout, str) or len(response.stdout.encode('utf-8')) > 1024 * 1024:
                raise ValueError('Invalid environment response size.')
            value = json.loads(response.stdout, object_pairs_hook=_unique_object)
            if (not isinstance(value, dict) or value.get('state') != 'observed'
                    or not isinstance(value.get('packages'), dict) or not isinstance(value.get('markers'), dict)
                    or not isinstance(value.get('prefix'), str) or not value['prefix']):
                raise ValueError('Invalid environment response.')
        except (ValueError, RecursionError) as error:
            raise _ProbeFailure('read_environment', error=error) from error
        if str(Path(value['prefix']).resolve()) != str(Path(python_path).parent.parent.resolve()):
            result['error'] = 'Interpreter identity does not match the selected virtual environment.'
            raise _ProbeFailure('environment_identity', problem='compatibility_mismatch')
        value.update(selected_python=python_path, identity_verified=True)
        return value
    except _ProbeFailure as error:
        return {**result, 'failure': error.facts}
    except OSError as error:
        return {**result, 'failure': {'stage': 'environment_identity', 'problem': 'resource_inaccessible',
                'kind': type(error).__name__, 'errno': error.errno, 'returncode': None}}


def inspect_software_root(root_path, project=None, limit=20, python_path=None, environment_script=None):
    """Read immediate existing repositories; never fetch or write."""
    root = Path(root_path)
    started = time.monotonic()
    result = {"version": 1, "software_root": str(root), "state": "observed",
              "observed_at": datetime.now(timezone.utc).isoformat(),
              "projects": [], "truncated": False}
    if environment_script is not None:
        result['environment'] = _environment_status(python_path, environment_script)
    candidates = []
    try:
        root_metadata = _metadata(root)
        if root_metadata is None:
            return {**result, "state": "missing"}
        if not stat.S_ISDIR(root_metadata.st_mode):
            return {**result, "state": "unavailable", "error": "software_root is not a directory."}
        if project is not None:
            candidates = [(root / project, project)]
        else:
            candidates = []
            # Discovery is bounded in depth; scientific data trees are not scanned.
            if _metadata(root / '.git'):
                candidates.append((root, "."))
            for entry in root.iterdir():
                try:
                    repository = _metadata(entry / '.git')
                except OSError:
                    # Keep an unavailable row instead of hiding this neighbour.
                    repository = True
                if repository:
                    candidates.append((entry, entry.name))
    except OSError as error:
        result.update(state='unavailable', error='The software directory could not be read.',
            failure={'stage': 'read_software_root', 'problem': 'resource_inaccessible',
                     'kind': type(error).__name__, 'errno': error.errno, 'returncode': None})
    candidates.sort(key=lambda item: item[1])
    result['truncated'] = len(candidates) > limit
    for path, name in candidates[:limit]:
        if time.monotonic() - started > 35:
            result['truncated'] = True
            break
        result['projects'].append(_project_status(root, path, name))
    return result
