"""Mocked Git remotes exercise the source engine without network, pip or Slurm."""

import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap
from types import SimpleNamespace

import pytest

from autoslurm import prepare_software_sources, SoftwarePreparationError
from autoslurm.git_projects import GitCommands, GitProjectError


REPOSITORY = "git@github.com:lab/science.git"
FIRST, SECOND = "a" * 40, "b" * 40


def manifest(**project):
    return {"projects": [{"name": "science", "repository": REPOSITORY, **project}]}


class RemoteGit:
    """A moving remote plus independently checked-out local source directories."""

    def __init__(self):
        self.head = FIRST
        self.refs = {"refs/heads/main": FIRST}
        self.calls = []
        self.checkouts = {}
        self.fail = None
        self.bad_checkout = False
        self.bad_object = False
        self.subdirectory = None
        self.subdirectory_target = None
        self.submodule = False

    def run(self, args):
        self.calls.append(args)
        operation = args[2] if args[0] in {"-C", "--git-dir"} else args[0]
        if operation == self.fail:
            raise GitProjectError(operation, "Mock Git operation failed.")
        if operation == "clone":
            Path(args[-1]).mkdir(parents=True)
            return ""
        if operation == "ls-remote":
            if "--symref" in args:
                return f"ref: refs/heads/main\tHEAD\n{self.head}\tHEAD\n"
            selectors = args[args.index(REPOSITORY) + 1:]
            return "".join(f"{commit}\t{ref}\n" for ref, commit in self.refs.items() if ref in selectors)
        if operation == "config":
            return REPOSITORY + "\n"
        if operation == "fetch":
            return ""
        if operation == "ls-files":
            return f"160000 {FIRST} 0\tdependency\n" if self.submodule else ""
        if operation == "checkout":
            checkout = Path(args[1])
            self.checkouts[str(checkout)] = args[-1]
            (checkout / "version.txt").write_text(args[-1])
            if self.subdirectory_target:
                (checkout / "package").symlink_to(self.subdirectory_target, target_is_directory=True)
            elif self.subdirectory:
                (checkout / self.subdirectory).mkdir(parents=True)
            return ""
        if operation == "rev-parse":
            if args[-1] == "--is-bare-repository":
                return "true\n"
            if args[-1] == "HEAD":
                return (SECOND if self.bad_checkout else self.checkouts[args[1]]) + "\n"
            return (SECOND if self.bad_object else args[-1].split("^")[0]) + "\n"
        pytest.fail(f"Unexpected Git operation: {args}")


def prepare(tmp_path, git, request=None):
    return prepare_software_sources(request or manifest(), software_root=tmp_path / "software with spaces", git_commands=git)


def test_first_clone_resolves_exact_commit_in_separate_software_storage(tmp_path):
    git = RemoteGit()
    request = manifest()
    before = copy.deepcopy(request)
    results = tmp_path / "data"
    results.mkdir()
    (results / "science.json").write_text("keep scientific data")
    evidence = prepare(tmp_path, git, request)
    assert evidence["state"] == "sources_prepared"
    assert "environment" not in evidence
    assert request == before
    assert json.loads(Path(evidence["evidence_path"]).read_text()) == evidence
    project = evidence["projects"][0]
    assert project["revision"] is None and project["commit"] == FIRST
    assert (Path(project["checkout"]) / "version.txt").read_text() == FIRST
    assert project["install_path"] == project["checkout"]
    assert (results / "science.json").read_text() == "keep scientific data"
    assert len(list(results.iterdir())) == 1
    assert sum("--mirror" in call for call in git.calls) == 1


def test_each_new_omitted_revision_resolves_upstream_without_changing_old_checkout(tmp_path):
    git = RemoteGit()
    first = prepare(tmp_path, git)
    original_record = Path(first["evidence_path"]).read_bytes()
    git.head = SECOND
    second = prepare(tmp_path, git)
    assert first["projects"][0]["commit"] == FIRST
    assert second["projects"][0]["commit"] == SECOND
    assert first["projects"][0]["checkout"] != second["projects"][0]["checkout"]
    assert Path(first["evidence_path"]).read_bytes() == original_record
    assert (Path(first["projects"][0]["checkout"]) / "version.txt").read_text() == FIRST
    assert sum("--mirror" in call for call in git.calls) == 1
    assert sum(call[0] == "ls-remote" for call in git.calls) == 2


def test_pinned_commit_is_fetched_exactly_without_latest_resolution(tmp_path):
    git = RemoteGit()
    git.head = SECOND
    evidence = prepare(tmp_path, git, manifest(revision=FIRST))
    assert evidence["projects"][0]["commit"] == FIRST
    assert not any(call[0] == "ls-remote" for call in git.calls)
    assert any(call[-1] == FIRST and "fetch" in call for call in git.calls)


@pytest.mark.parametrize("revision", ["v1", "refs/tags/v1"])
def test_annotated_tag_is_peeled_and_recorded_as_commit(tmp_path, revision):
    git = RemoteGit()
    git.refs = {"refs/tags/v1": SECOND, "refs/tags/v1^{}": FIRST}
    evidence = prepare(tmp_path, git, manifest(revision=revision))
    assert evidence["projects"][0]["revision"] == revision
    assert evidence["projects"][0]["commit"] == FIRST


@pytest.mark.parametrize("operation", ["clone", "ls-remote", "fetch", "checkout"])
def test_source_failure_is_saved_and_never_claims_readiness(tmp_path, operation):
    git = RemoteGit()
    git.fail = operation
    with pytest.raises(SoftwarePreparationError) as failure:
        prepare(tmp_path, git)
    evidence = failure.value.evidence
    assert evidence["state"] == "failed"
    assert evidence["current_project"] == "science"
    assert evidence["error"]["stage"] == operation
    assert json.loads(Path(evidence["evidence_path"]).read_text())["state"] == "failed"
    assert not list((tmp_path / "software with spaces" / "repositories").glob("*.lock"))


@pytest.mark.parametrize("operation", ["ls-remote", "fetch"])
def test_failed_latest_resolution_does_not_return_cached_sources(tmp_path, operation):
    git = RemoteGit()
    first = prepare(tmp_path, git)
    git.fail = operation
    with pytest.raises(SoftwarePreparationError) as failure:
        prepare(tmp_path, git)
    assert failure.value.evidence["projects"] == []
    assert Path(first["projects"][0]["checkout"]).is_dir()


@pytest.mark.parametrize("output", ["", "not a ref\n", "not-a-commit\tHEAD\n", f"{FIRST}\tHEAD\n{SECOND}\tHEAD\n"])
def test_missing_or_malformed_remote_identity_fails_closed(tmp_path, output):
    git = RemoteGit()
    original = git.run
    git.run = lambda args: output if args[0] == "ls-remote" else original(args)
    with pytest.raises(SoftwarePreparationError):
        prepare(tmp_path, git)
    assert not git.checkouts


def test_submodule_sources_are_explicitly_unsupported(tmp_path):
    git = RemoteGit()
    git.submodule = True
    with pytest.raises(SoftwarePreparationError, match="submodule"):
        prepare(tmp_path, git)


def test_tampered_managed_cache_origin_is_not_fetched(tmp_path):
    git = RemoteGit()
    prepare(tmp_path, git)
    original = git.run
    git.calls.clear()
    git.run = lambda args: "other-repository\n" if "config" in args else original(args)
    with pytest.raises(SoftwarePreparationError, match="cache identity"):
        prepare(tmp_path, git)
    assert not any("fetch" in args for args in git.calls)


def test_branch_tag_ambiguity_requires_an_explicit_namespace(tmp_path):
    git = RemoteGit()
    git.refs = {"refs/heads/release": FIRST, "refs/tags/release": SECOND}
    with pytest.raises(SoftwarePreparationError, match="branch and tag"):
        prepare(tmp_path, git, manifest(revision="release"))
    assert prepare(tmp_path, git, manifest(revision="refs/heads/release"))["projects"][0]["commit"] == FIRST


def test_unknown_revision_and_wrong_checkout_never_produce_success(tmp_path):
    git = RemoteGit()
    with pytest.raises(SoftwarePreparationError, match="unavailable upstream"):
        prepare(tmp_path, git, manifest(revision="missing"))
    git.bad_checkout = True
    with pytest.raises(SoftwarePreparationError, match="does not match"):
        prepare(tmp_path, git)


def test_unavailable_commit_object_is_rejected_before_checkout(tmp_path):
    git = RemoteGit()
    git.bad_object = True
    with pytest.raises(SoftwarePreparationError, match="resolved commit"):
        prepare(tmp_path, git, manifest(revision=FIRST))
    assert not git.checkouts


def test_install_subdirectory_must_exist_and_cannot_escape_through_symlinks(tmp_path):
    git = RemoteGit()
    with pytest.raises(SoftwarePreparationError, match="does not exist"):
        prepare(tmp_path, git, manifest(subdirectory="package"))
    git.subdirectory = "package"
    assert prepare(tmp_path, git, manifest(subdirectory="package"))["projects"][0]["install_path"].endswith("/package")
    outside = tmp_path / "unrelated"
    outside.mkdir()
    git.subdirectory_target = outside
    with pytest.raises(SoftwarePreparationError, match="escapes"):
        prepare(tmp_path, git, manifest(subdirectory="package"))


def test_unmanaged_and_symlinked_cache_is_never_modified(tmp_path):
    git = RemoteGit()
    root = tmp_path / "software with spaces"
    cache = root / "repositories" / (hashlib.sha256(REPOSITORY.encode()).hexdigest() + ".git")
    cache.mkdir(parents=True)
    sentinel = cache / "uncommitted-science.py"
    sentinel.write_text("keep my checkout")
    with pytest.raises(SoftwarePreparationError, match="unmanaged"):
        prepare(tmp_path, git)
    assert not git.calls and sentinel.read_text() == "keep my checkout"
    sentinel.unlink()
    cache.rmdir()
    outside = tmp_path / "other-checkout"
    outside.mkdir()
    cache.symlink_to(outside, target_is_directory=True)
    with pytest.raises(SoftwarePreparationError, match="symlink"):
        prepare(tmp_path, git)
    assert not git.calls and not list(outside.iterdir())


def test_cache_lock_blocks_concurrent_writers_without_breaking_their_lock(tmp_path):
    git = RemoteGit()
    root = tmp_path / "software with spaces" / "repositories"
    root.mkdir(parents=True)
    lock = root / (hashlib.sha256(REPOSITORY.encode()).hexdigest() + ".lock")
    lock.write_text("existing operation")
    with pytest.raises(SoftwarePreparationError, match="locked"):
        prepare(tmp_path, git)
    assert lock.read_text() == "existing operation" and not git.calls


def test_later_project_failure_keeps_exact_partial_evidence(tmp_path):
    git = RemoteGit()
    request = manifest()
    request["projects"].append({"name": "z-reducer", "repository": REPOSITORY, "revision": "missing"})
    with pytest.raises(SoftwarePreparationError) as failure:
        prepare(tmp_path, git, request)
    evidence = failure.value.evidence
    assert evidence["state"] == "failed" and evidence["current_project"] == "z-reducer"
    assert evidence["projects"][0]["commit"] == FIRST
    assert len(evidence["projects"]) == 1


def test_interruption_retains_failure_evidence_and_releases_cache_lock(tmp_path):
    git = RemoteGit()
    real_run = git.run
    def interrupt(args):
        if "fetch" in args:
            raise KeyboardInterrupt
        return real_run(args)
    git.run = interrupt
    with pytest.raises(SoftwarePreparationError) as failure:
        prepare(tmp_path, git)
    assert failure.value.evidence["state"] == "failed"
    assert not list((tmp_path / "software with spaces" / "repositories").glob("*.lock"))


def test_record_write_failure_preserves_in_memory_failure_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr("autoslurm.software_sources.atomic_json", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    git = RemoteGit()
    with pytest.raises(SoftwarePreparationError) as failure:
        prepare(tmp_path, git)
    assert failure.value.evidence["state"] == "failed"
    assert "tracking_error" in failure.value.evidence
    assert not git.calls


def test_evidence_identity_collision_does_not_overwrite_another_operation(tmp_path, monkeypatch):
    root = tmp_path / "software with spaces"
    records = root / "source_preparations"
    records.mkdir(parents=True)
    original = records / "existing.json"
    original.write_text('{"state": "sources_prepared", "owner": "previous operation"}')
    before = original.read_bytes()
    monkeypatch.setattr("autoslurm.software_sources.uuid4", lambda: SimpleNamespace(hex="existing"))
    git = RemoteGit()
    with pytest.raises(SoftwarePreparationError) as failure:
        prepare(tmp_path, git)
    assert original.read_bytes() == before
    assert failure.value.evidence["state"] == "failed"
    assert "tracking_error" in failure.value.evidence
    assert not git.calls


def test_invalid_request_or_relative_software_root_has_no_effects(tmp_path):
    git = RemoteGit()
    with pytest.raises(ValueError):
        prepare_software_sources(manifest(), software_root="relative", git_commands=git)
    with pytest.raises(ValueError):
        prepare_software_sources(manifest(revision="--bad"), software_root=tmp_path / "unused", git_commands=git)
    assert not (tmp_path / "unused").exists() and not git.calls


def test_git_adapter_uses_literal_arguments_noninteractive_mode_and_hides_remote_errors(monkeypatch):
    calls = []
    def run(command, **options):
        calls.append((command, options))
        return SimpleNamespace(returncode=128, stdout="", stderr="fatal: secret token in remote URL")
    monkeypatch.setattr("subprocess.run", run)
    with pytest.raises(GitProjectError) as failure:
        GitCommands().run(["ls-remote", "--", REPOSITORY, "HEAD"])
    assert "secret" not in str(failure.value)
    assert calls[0][0] == ["git", "ls-remote", "--", REPOSITORY, "HEAD"]
    assert calls[0][1]["env"]["GIT_TERMINAL_PROMPT"] == "0"
    assert calls[0][1]["timeout"] == 120


@pytest.mark.local_processes
def test_real_local_git_clones_fetches_and_keeps_previous_sources(tmp_path):
    # A Python fixture process is explicitly permitted by the offline guard.
    # Its only Git remote is a temporary local bare repo; no cluster or network.
    fixture = tmp_path / "local_git_fixture.py"
    fixture.write_text(textwrap.dedent('''
        import json
        import os
        from pathlib import Path
        import subprocess
        import sys
        from autoslurm import prepare_software_sources, SoftwarePreparationError
        from autoslurm.git_projects import GitCommands

        root = Path(sys.argv[1])
        source, remote = root / "author", root / "origin.git"
        def git(*args):
            return subprocess.run(["git", *map(str, args)], check=True, text=True, capture_output=True).stdout.strip()
        git("init", "-b", "main", source)
        git("init", "--bare", remote)
        git("-C", source, "config", "user.name", "Local fixture")
        git("-C", source, "config", "user.email", "fixture@example.invalid")
        git("-C", source, "config", "commit.gpgsign", "false")
        git("-C", source, "remote", "add", "origin", remote)
        git("--git-dir", remote, "symbolic-ref", "HEAD", "refs/heads/main")
        repository = "https://example.invalid/science.git"
        # Git preserves the requested remote identity while all transport goes
        # through a local file URL owned by this fixture.
        os.environ.update(GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0=f"url.{remote.as_uri()}.insteadOf", GIT_CONFIG_VALUE_0=repository)
        request = {"projects": [{"name": "science", "repository": repository}]}
        def commit(text):
            (source / "science.py").write_text(text)
            git("-C", source, "add", "science.py")
            git("-C", source, "commit", "-m", text)
            git("-C", source, "push", "origin", "main")
            return git("-C", source, "rev-parse", "HEAD")
        first_commit = commit("first")
        first = prepare_software_sources(request, software_root=root / "software")
        assert first["projects"][0]["commit"] == first_commit
        second_commit = commit("second")
        second = prepare_software_sources(request, software_root=root / "software")
        assert second["projects"][0]["commit"] == second_commit != first_commit
        assert (Path(first["projects"][0]["checkout"]) / "science.py").read_text() == "first"
        git("-C", source, "checkout", "-b", "new-default")
        (source / "science.py").write_text("new default branch")
        git("-C", source, "add", "science.py")
        git("-C", source, "commit", "-m", "new default branch")
        git("-C", source, "push", "origin", "new-default")
        git("--git-dir", remote, "symbolic-ref", "HEAD", "refs/heads/new-default")
        latest = prepare_software_sources(request, software_root=root / "software")
        assert latest["projects"][0]["commit"] == git("-C", source, "rev-parse", "HEAD")
        assert (Path(latest["projects"][0]["checkout"]) / "science.py").read_text() == "new default branch"
        pinned = {"projects": [{**request["projects"][0], "revision": first_commit}]}
        assert prepare_software_sources(pinned, software_root=root / "software")["projects"][0]["commit"] == first_commit
        git("-C", source, "tag", "-a", "v1", first_commit, "-m", "old tag")
        git("-C", source, "push", "origin", "v1")
        tagged = {"projects": [{**request["projects"][0], "revision": "v1"}]}
        assert prepare_software_sources(tagged, software_root=root / "software")["projects"][0]["commit"] == first_commit
        missing = {"projects": [{**request["projects"][0], "revision": "c" * 40}]}
        try:
            prepare_software_sources(missing, software_root=root / "software")
        except SoftwarePreparationError as error:
            assert error.evidence["state"] == "failed"
        else:
            raise AssertionError("An unavailable commit was accepted")
        print("local Git source preparation verified")
    '''))
    environment = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
                   "AUTOSLURM_STORAGE_ROOT": str(tmp_path / "fixture-state")}
    for key in list(environment):
        if key.startswith("GIT_CONFIG_") and key not in {"GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM"}:
            environment.pop(key)
    result = subprocess.run([sys.executable, str(fixture), str(tmp_path)],
                            capture_output=True, text=True, env=environment, timeout=30)
    assert result.returncode == 0, result.stderr
    assert "local Git source preparation verified" in result.stdout
