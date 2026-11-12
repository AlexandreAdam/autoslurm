"""Standalone, read-only Git probe; also sent over SSH without installation.

Keep this module standard-library-only and free of AutoSlurm imports. Merely
reading it or importing it performs no filesystem or process operations.
"""

from datetime import datetime, timezone
import os
import json
from pathlib import Path
import subprocess
import time


def _git(path, *arguments):
    result = subprocess.run(
        ["git", "-C", str(path), *arguments], capture_output=True, text=True,
        timeout=5, env={**os.environ, "GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0"},
    )
    return result.returncode, result.stdout


def _project_status(root, path, name):
    result = {"name": name, "path": str(path), "state": "unavailable",
              "commit": None, "branch": None, "dirty": None}
    try:
        path.resolve().relative_to(root.resolve())
        if not path.exists():
            return {**result, "state": "missing"}
        if not ((path / ".git").exists() or ((path / "HEAD").is_file() and (path / "objects").is_dir())):
            return {**result, "state": "not_a_repository"}
        code, bare = _git(path, "rev-parse", "--is-bare-repository")
        if code or bare.strip() not in {"true", "false"}:
            return {**result, "error": "Repository metadata is unreadable."}
        result["bare"] = bare.strip() == "true"
        code, commit = _git(path, "rev-parse", "--verify", "HEAD")
        commit = commit.strip()
        if code or len(commit) not in {40, 64} or any(c not in "0123456789abcdef" for c in commit):
            return {**result, "error": "No readable commit; the repository may be empty or invalid."}
        result["commit"] = commit
        code, branch = _git(path, "symbolic-ref", "--quiet", "--short", "HEAD")
        if code not in {0, 1}:
            return {**result, "error": "Could not determine the current branch."}
        result["branch"] = branch.strip() if code == 0 else None
        if not result["bare"]:
            code, changes = _git(path, "status", "--porcelain=v1", "--untracked-files=normal", "--ignore-submodules=all")
            if code:
                return {**result, "error": "Could not inspect working-tree changes."}
            lines = changes.splitlines()
            result.update(dirty=bool(lines), changed_paths=len(lines),
                          changes=lines[:20], changes_truncated=len(lines) > 20)
        return {**result, "state": "observed"}
    except ValueError:
        return {**result, "state": "outside_root", "error": "Project resolves outside software_root."}
    except (OSError, subprocess.TimeoutExpired):
        return {**result, "error": "Git inspection failed or timed out."}


def inspect_software_root(root_path, project=None, limit=20, python_path=None, environment_script=None):
    """Read immediate repositories and managed source sets; never fetch or write."""
    root = Path(root_path)
    result = {"version": 1, "software_root": str(root), "state": "observed",
              "observed_at": datetime.now(timezone.utc).isoformat(),
              "projects": [], "truncated": False}
    if environment_script is not None:
        environment = {"state": "unavailable", "error": "Configure venv_path to inspect the selected environment."}
        if python_path:
            try:
                probe = subprocess.run([python_path, "-B", "-c", environment_script], capture_output=True,
                                       text=True, timeout=25, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
                if probe.returncode == 0 and len(probe.stdout) <= 1024 * 1024:
                    candidate = json.loads(probe.stdout)
                    expected_prefix = str(Path(python_path).parent.parent.resolve())
                    if (candidate.get("state") == "observed" and isinstance(candidate.get("packages"), dict)
                            and isinstance(candidate.get("markers"), dict)
                            and str(Path(candidate.get("prefix", "")).resolve()) == expected_prefix):
                        environment = candidate
                    else:
                        environment["error"] = "Interpreter identity does not match the selected virtual environment."
                else:
                    environment["error"] = "The selected environment's interpreter could not be inspected."
            except (OSError, ValueError, TypeError, AttributeError, subprocess.TimeoutExpired):
                environment["error"] = "The selected environment's interpreter is unavailable or returned invalid evidence."
        result["environment"] = environment
    started = time.monotonic()
    try:
        if not root.exists():
            return {**result, "state": "missing"}
        if not root.is_dir():
            return {**result, "state": "unavailable", "error": "software_root is not a directory."}
        if project is not None:
            candidates = [(root / project, project)]
        else:
            candidates = []
            # Discovery is bounded in depth; scientific data trees are not scanned.
            if (root / ".git").exists():
                candidates.append((root, "."))
            for entry in sorted(root.iterdir()):
                if (entry / ".git").exists():
                    candidates.append((entry, entry.name))
            sources = root / "sources"
            if sources.is_dir() and not sources.is_symlink():
                for source_set in sorted(sources.iterdir()):
                    if not source_set.is_dir() or source_set.is_symlink():
                        continue
                    for entry in sorted(source_set.iterdir()):
                        if (entry / ".git").exists():
                            candidates.append((entry, str(entry.relative_to(root))))
                            if len(candidates) > limit:
                                break
                    if len(candidates) > limit:
                        break
        result["truncated"] = len(candidates) > limit
        for path, name in candidates[:limit]:
            if time.monotonic() - started > 35:
                result["truncated"] = True
                break
            result["projects"].append(_project_status(root, path, name))
    except OSError:
        result.update(state="unavailable", error="The software directory could not be read.")
    return result
