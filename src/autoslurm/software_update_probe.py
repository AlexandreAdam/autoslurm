"""Standalone single-checkout updater, also sent over SSH through stdin.

Only standard-library imports. Pull one checkout, then refresh its editable
installation in an existing selected environment. No clones or tracking files.
"""

from datetime import datetime, timezone
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess


def relative_project_path(project):
    if (not isinstance(project, str) or not project or PurePosixPath(project).is_absolute()
            or '..' in PurePosixPath(project).parts or '\\' in project
            or any(ord(c) < 32 for c in project)):
        raise ValueError('project must be relative to software_root without traversal.')
    return str(PurePosixPath(project))


def _git(path, *arguments, timeout=10):
    return subprocess.run(['git', '-C', str(path), *arguments], capture_output=True, text=True,
                          timeout=timeout, env={**os.environ, 'GIT_TERMINAL_PROMPT': '0',
                                               'GIT_OPTIONAL_LOCKS': '0'})


def _commit(path):
    response = _git(path, 'rev-parse', '--verify', 'HEAD^{commit}')
    commit = response.stdout.strip()
    if response.returncode or not re.fullmatch(r'(?:[0-9a-f]{40}|[0-9a-f]{64})', commit):
        raise ValueError('Existing checkout has no readable commit.')
    return commit


def _environment_python(venv_path):
    if not isinstance(venv_path, str) or not venv_path or not Path(venv_path).is_absolute():
        raise ValueError('Configure an absolute venv_path before updating software.')
    python = str(Path(venv_path) / 'bin/python')
    response = subprocess.run(
        [python, '-I', '-B', '-c', 'import json, sys; print(json.dumps({"prefix": sys.prefix}))'],
        capture_output=True, text=True, timeout=15,
    )
    try:
        evidence = json.loads(response.stdout) if response.returncode == 0 and len(response.stdout) < 4096 else {}
        prefix = evidence.get('prefix')
        if not isinstance(prefix, str) or Path(prefix).resolve() != Path(venv_path).resolve():
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise ValueError('Interpreter identity does not match the configured virtual environment; pull was not started.') from None
    return python


def _install_editable(python, path):
    # Only install the project into the selected environment. Pip manages its
    # build requirements in a temporary isolated environment, using its index.
    environment = {key: value for key, value in os.environ.items() if not key.startswith('PIP_')}
    environment.update(PIP_CONFIG_FILE=os.devnull, PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1')
    return subprocess.run(
        [python, '-I', '-B', '-m', 'pip', '--disable-pip-version-check', '--no-input',
         'install', '--no-deps', '--no-cache-dir',
         '--editable', str(path)],
        cwd=str(path), capture_output=True, text=True, timeout=120, env=environment,
    )


def _pip_output_tail(result):
    """Keep useful bounded build diagnostics without URL credentials."""
    output = '\n'.join(part for part in (result.stdout, result.stderr) if part)
    lines = [line for line in output.splitlines()[-20:]
             if not re.search(r'\b[a-zA-Z][a-zA-Z0-9+.-]*://[^\s/]*@', line)]
    return '\n'.join(lines).encode('utf-8', errors='replace')[-4096:].decode('utf-8', errors='replace')


def update_checkout(software_root, project, venv_path=None):
    """Pull the tracking branch, then reinstall this checkout editable once."""
    project = relative_project_path(project)
    root = Path(software_root)
    if not root.is_absolute():
        raise ValueError('software_root must be an absolute machine path.')
    path = root / project
    result = {'version': 1, 'software_root': str(root), 'project': project, 'path': str(path),
              'state': 'failed', 'stage': 'preflight', 'branch': None, 'upstream': None,
              'before_commit': None, 'after_commit': None,
              'installation': {'state': 'not_started', 'python': None, 'editable': True,
                               'path': str(path), 'returncode': None}}
    try:
        if not root.is_dir() or not path.is_dir():
            raise ValueError('Existing project checkout is missing; updates never clone or create directories.')
        resolved_root, resolved_path = root.resolve(), path.resolve()
        try:
            resolved_path.relative_to(resolved_root)
        except ValueError:
            raise ValueError('Project resolves outside software_root.') from None
        top = _git(path, 'rev-parse', '--show-toplevel')
        if top.returncode or Path(top.stdout.strip()).resolve() != resolved_path:
            raise ValueError('Project must select the existing Git checkout root, not a parent repository or subdirectory.')
        result['before_commit'] = result['after_commit'] = _commit(path)
        branch = _git(path, 'symbolic-ref', '--quiet', '--short', 'HEAD')
        if branch.returncode or not branch.stdout.strip():
            raise ValueError('Checkout has a detached HEAD; select its tracking branch before updating.')
        result['branch'] = branch.stdout.strip()
        upstream = _git(path, 'rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{upstream}')
        if upstream.returncode or not upstream.stdout.strip():
            raise ValueError('Current branch has no configured upstream; configure its tracking branch before updating.')
        result['upstream'] = upstream.stdout.strip()
        changes = _git(path, 'status', '--porcelain=v1', '--untracked-files=normal')
        if changes.returncode:
            raise ValueError('Could not inspect working-tree changes; pull was not started.')
        if changes.stdout.strip():
            raise ValueError('Checkout has local changes or untracked files; pull was not started. No stash or reset was performed.')
        result['installation']['python'] = _environment_python(venv_path)
        result['stage'] = 'pull'
        result['after_commit'] = None
        response = _git(path, '-c', 'submodule.recurse=false', '-c', 'pull.rebase=false',
                        '-c', 'rebase.autoStash=false', '-c', 'merge.autoStash=false',
                        'pull', '--ff-only', '--no-recurse-submodules', timeout=120)
        result['after_commit'] = _commit(path)
        if response.returncode:
            # Git diagnostics can expose credential-bearing URLs or local config.
            # Explain recognized failures without copying raw command output.
            if any(text in response.stderr.lower() for text in ('fast-forward', 'divergent', 'unrelated histories')):
                message = 'Git pull cannot fast-forward this branch; no merge or reset was requested.'
            elif any(text in response.stderr.lower() for text in ('permission denied', 'authentication failed', 'host key verification')):
                message = 'Git pull failed: check repository authentication and SSH access.'
            else:
                message = f'Git pull failed (exit {response.returncode}); check upstream access and branch history.'
            raise ValueError(message)
        result['stage'] = 'install'
        result['installation']['state'] = 'unknown'
        installation = _install_editable(result['installation']['python'], path)
        result['installation'].update(state='installed' if installation.returncode == 0 else 'failed',
                                      returncode=installation.returncode)
        if installation.returncode:
            tail = _pip_output_tail(installation)
            result['installation']['output_tail'] = tail
            raise ValueError(f'Editable installation failed (exit {installation.returncode}); '
                             'the checkout was pulled but the environment may be partially changed. '
                             'Check pip/build requirements before running jobs.'
                             + (f'\nPip output (tail):\n{tail}' if tail else ''))
        result.update(state='updated' if result['after_commit'] != result['before_commit'] else 'up_to_date', stage='complete')
    except ValueError as error:
        result['error'] = str(error)
        if result['stage'] == 'pull' and result['after_commit'] is None:
            result.update(state='unknown', error='Pull finished without readable commit evidence; inspect checkout status before trying again.')
    except (OSError, subprocess.TimeoutExpired, KeyboardInterrupt):
        if result['stage'] == 'pull':
            result.update(state='unknown', after_commit=None,
                          error='Pull outcome is unknown; inspect the checkout status before trying again.')
        elif result['stage'] == 'install':
            result.update(state='unknown', error='Editable installation outcome is unknown; '
                          'the checkout was pulled. Inspect the selected environment before trying again.')
        else:
            result['error'] = 'Checkout/environment preflight could not finish; pull and installation were not started.'
    result['observed_at'] = datetime.now(timezone.utc).isoformat()
    return result
