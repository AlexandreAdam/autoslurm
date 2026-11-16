"""Standalone single-checkout updater, also sent over SSH through stdin.

Only standard-library imports. Pull one checkout, then refresh its editable
installation in an existing selected environment. No clones or tracking files.
"""

from datetime import datetime, timezone
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess


def relative_project_path(project):
    if (not isinstance(project, str) or not project or PurePosixPath(project).is_absolute()
            or '..' in PurePosixPath(project).parts or '\\' in project
            or any(ord(c) < 32 or ord(c) == 127 for c in project)):
        raise ValueError('project must be relative to software_root without traversal.')
    return str(PurePosixPath(project))


class _UpdateCheckFailure(ValueError):
    """Explicit probe guard; plain facts cross SSH, native causes stay local."""

    def __init__(self, message, *, problem='invalid_argument', returncode=None):
        super().__init__(message)
        self.problem, self.returncode = problem, returncode


def _git(path, *arguments, timeout=10):
    return subprocess.run(['git', '-C', str(path), *arguments], capture_output=True, text=True,
                          timeout=timeout, env={**os.environ, 'GIT_TERMINAL_PROMPT': '0',
                                               'GIT_OPTIONAL_LOCKS': '0'})


def _commit(path):
    response = _git(path, 'rev-parse', '--verify', 'HEAD^{commit}')
    commit = response.stdout.strip()
    if response.returncode or not re.fullmatch(r'(?:[0-9a-f]{40}|[0-9a-f]{64})', commit):
        raise _UpdateCheckFailure('Existing checkout has no readable commit.',
            problem=_command_problem(response.returncode) if response.returncode else 'protocol_invalid', returncode=response.returncode)
    return commit


def _command_problem(returncode):
    return 'operation_interrupted' if returncode < 0 else 'command_failed'


def _environment_python(venv_path):
    if not isinstance(venv_path, str) or not venv_path or not Path(venv_path).is_absolute():
        raise _UpdateCheckFailure('Configure an absolute venv_path before updating software.')
    python = str(Path(venv_path) / 'bin/python')
    response = subprocess.run(
        [python, '-I', '-B', '-c', 'import json, sys; print(json.dumps({"prefix": sys.prefix}))'],
        capture_output=True, text=True, timeout=15,
    )
    if response.returncode:
        raise _UpdateCheckFailure('Configured environment Python identity check failed; pull was not started.',
            problem='operation_interrupted' if response.returncode < 0 else 'command_failed', returncode=response.returncode)
    if not isinstance(response.stdout, str) or len(response.stdout) >= 4096:
        raise _UpdateCheckFailure('Invalid environment Python identity response.', problem='protocol_invalid')
    try:
        evidence = json.loads(response.stdout)
    except (ValueError, UnicodeError) as error:
        raise _UpdateCheckFailure('Invalid environment Python identity response.', problem='protocol_invalid') from error
    if not isinstance(evidence, dict) or not isinstance(evidence.get('prefix'), str):
        raise _UpdateCheckFailure('Invalid environment Python identity response.', problem='protocol_invalid')
    if Path(evidence['prefix']).resolve() != Path(venv_path).resolve():
        raise _UpdateCheckFailure('Interpreter identity does not match the configured virtual environment; pull was not started.',
                                  problem='compatibility_mismatch')
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


def _run_update_checkout(software_root, project, venv_path=None):
    """Return plain evidence and the native local cause separately."""
    project = relative_project_path(project)
    root = Path(software_root)
    if not root.is_absolute():
        raise ValueError('software_root must be an absolute machine path.')
    path = root / project
    result = {'version': 1, 'software_root': str(root), 'project': project, 'path': str(path),
              'state': 'failed', 'stage': 'preflight', 'check': 'checkout_root', 'branch': None, 'upstream': None,
              'before_commit': None, 'after_commit': None,
              'effects': {'git_pull': 'not_started', 'editable_install': 'not_started'},
              'installation': {'state': 'not_started',
                               'python': str(Path(venv_path) / 'bin/python') if isinstance(venv_path, str) else None,
                               'editable': True, 'path': str(path), 'returncode': None}}
    cause = None
    try:
        for directory in (root, path):
            if not stat.S_ISDIR(directory.stat().st_mode):
                raise _UpdateCheckFailure('Existing project checkout is not a directory; updates never clone or create directories.',
                                          problem='resource_inaccessible')
        resolved_root, resolved_path = root.resolve(), path.resolve()
        try:
            resolved_path.relative_to(resolved_root)
        except ValueError:
            raise _UpdateCheckFailure('Project resolves outside software_root.') from None
        result['check'] = 'git_checkout'
        top = _git(path, 'rev-parse', '--show-toplevel')
        if top.returncode or Path(top.stdout.strip()).resolve() != resolved_path:
            raise _UpdateCheckFailure('Project must select the existing Git checkout root, not a parent repository or subdirectory.',
                problem=_command_problem(top.returncode) if top.returncode else 'invalid_argument', returncode=top.returncode)
        result['check'] = 'git_commit_before'
        result['before_commit'] = result['after_commit'] = _commit(path)
        result['check'] = 'git_branch'
        branch = _git(path, 'symbolic-ref', '--quiet', '--short', 'HEAD')
        if branch.returncode and branch.returncode != 1:
            raise _UpdateCheckFailure('Could not read the current Git branch; pull was not started.',
                problem=_command_problem(branch.returncode), returncode=branch.returncode)
        if branch.returncode == 1:
            raise _UpdateCheckFailure('Checkout has a detached HEAD; select its tracking branch before updating.', returncode=branch.returncode)
        if not branch.stdout.strip():
            raise _UpdateCheckFailure('Git returned no branch identity; pull was not started.', problem='protocol_invalid')
        result['branch'] = branch.stdout.strip()
        result['check'] = 'git_upstream'
        upstream = _git(path, 'rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{upstream}')
        if upstream.returncode or not upstream.stdout.strip():
            raise _UpdateCheckFailure('Current branch has no readable configured upstream; verify its tracking branch before updating.',
                problem=_command_problem(upstream.returncode) if upstream.returncode else 'protocol_invalid', returncode=upstream.returncode)
        result['upstream'] = upstream.stdout.strip()
        result['check'] = 'git_status'
        changes = _git(path, 'status', '--porcelain=v1', '--untracked-files=normal')
        if changes.returncode:
            raise _UpdateCheckFailure('Could not inspect working-tree changes; pull was not started.',
                problem=_command_problem(changes.returncode), returncode=changes.returncode)
        if changes.stdout.strip():
            raise _UpdateCheckFailure('Checkout has local changes or untracked files; pull was not started. No stash or reset was performed.')
        result['check'] = 'environment_python'
        result['installation']['python'] = _environment_python(venv_path)
        result['stage'] = 'pull'
        result['check'] = 'git_pull'
        result['after_commit'] = None
        result['effects']['git_pull'] = 'unknown'
        response = _git(path, '-c', 'submodule.recurse=false', '-c', 'pull.rebase=false',
                        '-c', 'rebase.autoStash=false', '-c', 'merge.autoStash=false',
                        'pull', '--ff-only', '--no-recurse-submodules', timeout=120)
        if response.returncode < 0:
            raise _UpdateCheckFailure('Git pull was interrupted; inspect checkout status before trying again.',
                problem='operation_interrupted', returncode=response.returncode)
        result['effects']['git_pull'] = 'failed' if response.returncode else 'succeeded'
        result['check'] = 'git_commit_after'
        result['after_commit'] = _commit(path)
        result['check'] = 'git_pull'
        if response.returncode:
            # Git diagnostics can expose credential-bearing URLs or local config.
            # Explain recognized failures without copying raw command output.
            if any(text in response.stderr.lower() for text in ('fast-forward', 'divergent', 'unrelated histories')):
                message = 'Git pull cannot fast-forward this branch; no merge or reset was requested.'
            elif any(text in response.stderr.lower() for text in ('permission denied', 'authentication failed', 'host key verification')):
                message = 'Git pull failed: check repository authentication and SSH access.'
            else:
                message = f'Git pull failed (exit {response.returncode}); check upstream access and branch history.'
            raise _UpdateCheckFailure(message, problem='command_failed', returncode=response.returncode)
        result['stage'] = 'install'
        result['check'] = 'editable_install'
        result['installation']['state'] = 'unknown'
        result['effects']['editable_install'] = 'unknown'
        installation = _install_editable(result['installation']['python'], path)
        result['installation'].update(state='installed' if installation.returncode == 0 else 'failed',
                                      returncode=installation.returncode)
        result['effects']['editable_install'] = 'succeeded' if installation.returncode == 0 else 'partial'
        if installation.returncode:
            tail = _pip_output_tail(installation)
            result['installation']['output_tail'] = tail
        if installation.returncode < 0:
            result['effects']['editable_install'] = 'unknown'
            result['installation']['state'] = 'unknown'
            raise _UpdateCheckFailure('Editable installation was interrupted; inspect the selected environment before trying again.',
                problem='operation_interrupted', returncode=installation.returncode)
        if installation.returncode:
            raise _UpdateCheckFailure(f'Editable installation failed (exit {installation.returncode}); '
                             'the checkout was pulled but the environment may be partially changed. '
                             'Check pip/build requirements before running jobs.'
                             + (f'\nPip output (tail):\n{tail}' if tail else ''),
                             problem='command_failed', returncode=installation.returncode)
        result.update(state='updated' if result['after_commit'] != result['before_commit'] else 'up_to_date', stage='complete')
    except (_UpdateCheckFailure, OSError, subprocess.TimeoutExpired, KeyboardInterrupt) as error:
        cause = error
        if isinstance(error, _UpdateCheckFailure):
            problem = error.problem
        elif isinstance(error, subprocess.TimeoutExpired):
            problem = 'command_timeout'
        elif isinstance(error, KeyboardInterrupt):
            problem = 'operation_interrupted'
        else:
            command = result['check'] != 'checkout_root'
            launch_failed = isinstance(error, (FileNotFoundError, PermissionError))
            problem = ('command_unavailable' if launch_failed else 'command_failed') if command else (
                'resource_missing' if isinstance(error, FileNotFoundError) else 'resource_inaccessible')
            if result['check'] == 'git_pull' and launch_failed:
                result['effects']['git_pull'] = 'not_started'
            elif result['check'] == 'editable_install' and launch_failed:
                result['effects']['editable_install'] = 'not_started'
                result['installation']['state'] = 'not_started'
        result['failure'] = {'problem': problem, 'cause_kind': 'ValueError' if isinstance(error, _UpdateCheckFailure) else type(error).__name__,
            'errno': getattr(error, 'errno', None), 'returncode': getattr(error, 'returncode', None)}
        result['error'] = str(error) if isinstance(error, _UpdateCheckFailure) else 'Software update check could not finish.'
        if result['stage'] == 'preflight' and not isinstance(error, _UpdateCheckFailure):
            result['error'] = 'Checkout/environment preflight could not finish; pull and installation were not started.'
        if result['check'] == 'checkout_root' and isinstance(error, FileNotFoundError):
            result['error'] = 'Existing project checkout is missing; updates never clone or create directories.'
        if result['stage'] == 'pull' and result['after_commit'] is None and result['effects']['git_pull'] != 'not_started':
            result.update(state='unknown', error='Pull finished without readable commit evidence; inspect checkout status before trying again.')
        elif result['stage'] == 'install' and result['effects']['editable_install'] == 'unknown':
            result.update(state='unknown', error='Editable installation outcome is unknown; '
                          'the checkout was pulled. Inspect the selected environment before trying again.')
    result['observed_at'] = datetime.now(timezone.utc).isoformat()
    return result, cause


def update_checkout(software_root, project, venv_path=None):
    """Standalone JSON-safe entry point; no remote AutoSlurm dependency."""
    return _run_update_checkout(software_root, project, venv_path)[0]
