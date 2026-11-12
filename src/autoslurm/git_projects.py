"""Host-side Git adapter and managed caches; never touch application checkouts."""

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from uuid import uuid4

from .record_files import atomic_json


def is_commit(value):
    return isinstance(value, str) and bool(re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", value))


class GitProjectError(RuntimeError):
    """A bounded, credential-free error at a named source preparation stage."""

    def __init__(self, stage, message):
        self.stage = stage
        super().__init__(message)


class GitCommands:
    """All Git subprocess effects. Callers/tests can substitute this adapter."""

    def run(self, arguments):
        operation = arguments[2] if arguments[0] in {"-C", "--git-dir"} else arguments[0]
        try:
            result = subprocess.run(
                ["git", *arguments], capture_output=True, text=True, timeout=120,
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            )
        except (OSError, subprocess.TimeoutExpired):
            raise GitProjectError(operation, f"Git {operation} could not run or timed out.") from None
        if result.returncode:
            # Remote stderr may contain credentials supplied through Git config.
            raise GitProjectError(operation, f"Git {operation} failed (exit {result.returncode}).")
        return result.stdout


def managed_path(root, *parts):
    """Reject redirected managed children; the configured root may be a symlink."""
    path = root.joinpath(*parts)
    if any(parent.is_symlink() for parent in (path, *path.parents) if parent != root and root in parent.parents):
        raise GitProjectError("storage", "A managed software path is a symlink.")
    try:
        path.resolve().relative_to(root)
    except ValueError:
        raise GitProjectError("storage", "A managed software path leaves software_root.") from None
    return path


@contextmanager
def _cache_lock(path):
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise GitProjectError("cache", "Repository preparation is locked; inspect the existing operation before retrying.") from None
    try:
        os.close(descriptor)
        yield
    finally:
        path.unlink()


def resolve_revision(commands, repository, revision):
    """Resolve each new request upstream, never a cache's stale default branch."""
    if is_commit(revision):
        return revision
    if revision is None:
        arguments = ["ls-remote", "--symref", "--", repository, "HEAD"]
    else:
        refs = [revision] if revision.startswith(("refs/heads/", "refs/tags/")) else [f"refs/heads/{revision}", f"refs/tags/{revision}"]
        arguments = ["ls-remote", "--", repository, *refs, *[ref + "^{}" for ref in refs if ref.startswith("refs/tags/")]]
    output = commands.run(arguments)
    references = {}
    for line in output.splitlines():
        fields = line.split("\t")
        if len(fields) != 2:
            raise GitProjectError("resolution", "Git returned malformed revision evidence.")
        commit, ref = fields
        if commit.startswith("ref: ") and revision is None:
            continue
        if not is_commit(commit) or (ref in references and references[ref] != commit):
            raise GitProjectError("resolution", "Git returned invalid or conflicting commit evidence.")
        references[ref] = commit
    if revision is None:
        commit = references.get("HEAD")
    else:
        matched = [ref for ref in refs if ref in references]
        if len(matched) > 1:
            raise GitProjectError("resolution", "Revision names both a branch and tag; use refs/heads/ or refs/tags/ explicitly.")
        commit = references.get(matched[0] + "^{}", references.get(matched[0])) if matched else None
    if not is_commit(commit):
        raise GitProjectError("resolution", "Requested revision is unavailable upstream.")
    return commit


def materialize_project(project, root, destination, commands):
    """Clone/fetch a managed bare cache and create a fresh detached checkout."""
    repository = project["repository"]
    identity = hashlib.sha256(repository.encode()).hexdigest()
    caches = managed_path(root, "repositories")
    caches.mkdir(parents=True, exist_ok=True)
    cache = managed_path(root, "repositories", identity + ".git")
    marker = cache / "autoslurm-repository.json"
    expected = {"version": 1, "repository": repository}
    with _cache_lock(managed_path(root, "repositories", identity + ".lock")):
        if cache.exists():
            try:
                owned = json.loads(marker.read_text()) == expected
            except (OSError, ValueError):
                owned = False
            if not owned:
                raise GitProjectError("cache", "Refusing to modify an unmanaged repository cache.")
            if (commands.run(["--git-dir", str(cache), "rev-parse", "--is-bare-repository"]).strip() != "true"
                    or commands.run(["--git-dir", str(cache), "config", "--get", "remote.origin.url"]).strip() != repository):
                raise GitProjectError("cache", "Managed cache identity no longer matches its repository.")
        else:
            staging = managed_path(root, "repositories", identity + ".partial-" + uuid4().hex)
            commands.run(["clone", "--mirror", "--", repository, str(staging)])
            atomic_json(staging / "autoslurm-repository.json", expected)
            staging.rename(cache)
        commit = resolve_revision(commands, repository, project["revision"])
        # Fetch only into the managed bare cache; never pull an active checkout.
        commands.run(["--git-dir", str(cache), "fetch", "--no-tags", "--no-recurse-submodules", "origin", commit])
        verified = commands.run(["--git-dir", str(cache), "rev-parse", "--verify", commit + "^{commit}"]).strip()
        if verified != commit:
            raise GitProjectError("verification", "Requested object is not the resolved commit.")
        commands.run(["clone", "--no-hardlinks", "--no-checkout", "--", str(cache), str(destination)])
        commands.run(["-C", str(destination), "checkout", "--detach", commit])
        actual = commands.run(["-C", str(destination), "rev-parse", "HEAD"]).strip()
        if actual != commit:
            raise GitProjectError("verification", "Materialized checkout does not match the resolved commit.")
        if any(line.startswith("160000 ") for line in commands.run(["-C", str(destination), "ls-files", "--stage"]).splitlines()):
            raise GitProjectError("verification", "Git submodule preparation is not supported yet.")
        install_path = (destination / project["subdirectory"]).resolve()
        try:
            install_path.relative_to(destination)
        except ValueError:
            raise GitProjectError("verification", "Install subdirectory escapes its project checkout.") from None
        if not install_path.is_dir():
            raise GitProjectError("verification", "Install subdirectory does not exist in the selected revision.")
        return {**project, "commit": commit, "checkout": str(destination), "install_path": str(install_path)}
