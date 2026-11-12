"""Software requests are pure data; accepting a request must never imply readiness."""

import copy

import pytest

from autoslurm.software_manifest import (
    attach_software_manifest, bundle_software_manifest, normalize_software_manifest,
)
from autoslurm.bundle_preparation import prepare_bundle
from autoslurm.execution import resolve_execution_context


def request(**changes):
    return {"projects": [{"name": "science", "repository": "git@github.com:lab/science.git", **changes}]}


def test_request_is_pure_canonical_and_does_not_copy_workstation_dependencies(monkeypatch):
    original = request()
    before = copy.deepcopy(original)
    monkeypatch.setattr("subprocess.run", lambda *a, **k: pytest.fail("No process in manifest normalization"))
    normalized = normalize_software_manifest(original)
    assert normalized == {"version": 1, "runtime": "default", "projects": [
        {**original["projects"][0], "revision": None, "subdirectory": "."}]}
    assert original == before
    normalized["projects"][0]["name"] = "changed"
    assert original == before


@pytest.mark.parametrize("project", [
    {"name": "../science"}, {"repository": "/home/scientist/project"},
    {"repository": "https://user:secret@example.com/repo.git"},
    {"repository": "https://token@example.com/repo.git"},
    {"repository": "https://example.com/repo.git?token=secret"},
    {"repository": "--upload-pack=bad"}, {"revision": "--config=bad"},
    {"revision": "main^{commit}"}, {"revision": ""},
    {"subdirectory": "../other"}, {"subdirectory": "/home/project"},
    {"subdirectory": "pkg/../../other"}, {"subdirectory": "pkg\\other"},
    {"requirements": "local-lock.txt"},
])
def test_invalid_or_machine_owned_project_fields_fail(project):
    with pytest.raises(ValueError):
        normalize_software_manifest(request(**project))


@pytest.mark.parametrize("manifest", [None, {}, {"projects": []}, {"version": 2, **request()},
    {"version": True, **request()}, {"runtime": "/env", **request()},
    {"python": "/local/python", **request()}, {"projects": [request()["projects"][0]] * 2}])
def test_invalid_requests_fail(manifest):
    with pytest.raises(ValueError):
        normalize_software_manifest(manifest)


def test_shared_attachment_preserves_the_existing_bundle_container_and_copies_values():
    bundle = {"worker": {"script": "science"}, "reducer": {"script": "reduce"}}
    updated = attach_software_manifest(bundle, request(revision="refs/tags/v1", subdirectory="packages/science"))
    assert set(updated) == set(bundle)
    assert bundle == {"worker": {"script": "science"}, "reducer": {"script": "reduce"}}
    assert bundle_software_manifest(list(updated.values()))["projects"][0]["revision"] == "refs/tags/v1"
    updated["worker"]["software"]["runtime"] = "changed"
    with pytest.raises(ValueError, match="same software"):
        bundle_software_manifest(list(updated.values()))


def test_partial_opt_in_and_mismatched_revisions_fail():
    jobs = [{"software": request()}, {}]
    with pytest.raises(ValueError, match="same software"):
        bundle_software_manifest(jobs)
    jobs[1] = {"software": request(revision="main")}
    with pytest.raises(ValueError, match="same software"):
        bundle_software_manifest(jobs)
    assert bundle_software_manifest([{}, {}]) is None


def test_canonical_project_order_and_default_values_compare_equal():
    first = request()["projects"][0]
    second = {**first, "name": "reducer", "revision": "v2"}
    one = {"software": {"projects": [first, second]}}
    two = {"software": {"version": 1, "runtime": "default", "projects": [second, first]}}
    assert len(bundle_software_manifest([one, two])["projects"]) == 2


def test_managed_request_cannot_silently_submit_using_legacy_runtime():
    jobs = list(attach_software_manifest({"worker": {"name": "worker", "script": "science", "slurm": {}}}, request()).values())
    with pytest.raises(ValueError, match="runtime readiness"):
        prepare_bundle(jobs, {"worker": []}, resolve_execution_context("mock", {}))
