"""Only declared important dependencies are compared, using target-machine markers."""

import copy

import pytest

from autoslurm.software_requirements import software_expectations, compare_environment


def environment(**packages):
    return {"state": "observed", "markers": {"python_version": "3.11", "sys_platform": "linux"},
            "packages": {name: {"state": "installed", "version": version} for name, version in packages.items()}}


def test_local_project_and_requirement_files_focus_on_major_dependencies(tmp_path):
    (tmp_path / "pyproject.toml").write_text('''[project]
name = "science-demo"
version = "1.2.0"
dependencies = ["numpy>=1.26,<3", "jax>=0.4", "tiny-helper==1"]
''')
    (tmp_path / "requirements.txt").write_text("-c pins.txt\ntorch==2.5.1 # target compatible\npytest==8\n")
    (tmp_path / "pins.txt").write_text("numpy<2\n")
    expectations = software_expectations(local_project=tmp_path)
    assert expectations["package"] == "science-demo"
    assert expectations["expected_version"] == "1.2.0"
    assert set(expectations["requirements"]) == {"numpy<3,>=1.26", "jax>=0.4", "numpy<2", "torch==2.5.1"}
    assert not expectations["warnings"]
    assert "tiny-helper" not in str(expectations)


def test_stricter_remote_version_that_satisfies_local_range_is_compatible(tmp_path):
    path = tmp_path / "requirements.txt"
    path.write_text("numpy>=1.24,<2\ntorch==2.5.1\n")
    expected = software_expectations(requirements=path)
    before = copy.deepcopy(expected)
    result = compare_environment(expected, environment(numpy="1.26.4", torch="2.5.1+cu124"))
    assert result["state"] == "compatible"
    assert expected == before


def test_selected_python_must_satisfy_the_projects_declared_python_version(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname="science"\nversion="1"\nrequires-python=">=3.12"\n')
    expected = software_expectations(local_project=tmp_path)
    actual = environment(science="1")
    actual["python_version"] = "3.11.11"
    assert compare_environment(expected, actual)["state"] == "potential_problem"
    actual["python_version"] = "3.12.1"
    assert compare_environment(expected, actual)["state"] == "compatible"


@pytest.mark.parametrize("actual,state", [("2.0", "potential_problem"), ("1.26.4", "compatible"), ("bad-version", "unknown")])
def test_version_constraints_and_uninterpretable_metadata(tmp_path, actual, state):
    path = tmp_path / "requirements.txt"
    path.write_text("numpy<2\n")
    assert compare_environment(software_expectations(requirements=path), environment(numpy=actual))["state"] == state


def test_missing_dependency_does_not_become_compatible(tmp_path):
    path = tmp_path / "requirements.txt"
    path.write_text("jax>=0.4\n")
    actual = environment()
    actual["packages"]["jax"] = {"state": "missing"}
    result = compare_environment(software_expectations(requirements=path), actual)
    assert result["state"] == "potential_problem"
    assert "not installed" in result["checks"][0]["message"]


def test_markers_are_evaluated_on_the_remote_python_platform(tmp_path):
    path = tmp_path / "requirements.txt"
    path.write_text('numpy<2; python_version < "3.12"\ntorch==1; sys_platform == "win32"\n')
    result = compare_environment(software_expectations(requirements=path), environment(numpy="2.0"))
    assert result["state"] == "potential_problem"
    assert [check["name"] for check in result["checks"]] == ["numpy"]


def test_missing_target_marker_never_uses_the_workstation_platform(tmp_path):
    path = tmp_path / "requirements.txt"
    path.write_text('numpy<2; platform_machine == "arm64"\n')
    result = compare_environment(software_expectations(requirements=path), environment(numpy="1"))
    assert result["state"] == "unknown"


def test_application_version_commit_and_editable_changes_are_independent_checks():
    expected = software_expectations(package="science", expected_version="1.0", expected_commit="a" * 40)
    actual = environment(science="1.0")
    actual["packages"]["science"].update(source_commit="b" * 40, editable=True, source_dirty=True)
    result = compare_environment(expected, actual)
    assert result["state"] == "potential_problem"
    assert any(check.get("expected_commit") for check in result["checks"])
    assert any("local changes" in check["message"] for check in result["checks"])
    actual["packages"]["science"].update(source_commit="a" * 40, source_dirty=False)
    assert compare_environment(expected, actual)["state"] == "compatible"
    actual["packages"]["science"].update(version="2.0")
    assert compare_environment(expected, actual)["state"] == "potential_problem"


def test_matching_package_version_without_requested_commit_evidence_stays_unknown():
    expected = software_expectations(package="science", expected_version="1", expected_commit="a" * 40)
    result = compare_environment(expected, environment(science="1"))
    assert result["state"] == "unknown"
    assert any(check.get("installed_commit") is None and "expected_commit" in check for check in result["checks"])


def test_unconstrained_and_unsupported_source_declarations_are_not_verified(tmp_path):
    path = tmp_path / "requirements.txt"
    path.write_text("numpy\njax @ https://example.invalid/jax.whl\n--only-binary=:all:\n")
    expected = software_expectations(requirements=path)
    assert compare_environment(expected, environment(numpy="1", jax="1"))["state"] == "unknown"


def test_credential_bearing_dependency_urls_are_not_copied_into_status_evidence(tmp_path):
    path = tmp_path / "requirements.txt"
    path.write_text("jax @ https://token-secret@example.invalid/jax.whl\n")
    expected = software_expectations(requirements=path)
    assert "token-secret" not in str(expected)
    assert compare_environment(expected, environment(jax="1"))["state"] == "unknown"


def test_additional_major_dependency_is_opt_in_and_includes_are_cycle_safe(tmp_path):
    path = tmp_path / "requirements.txt"
    path.write_text("astropy>=6\n-r requirements.txt\n")
    expected = software_expectations(requirements=path, dependencies=["astropy"])
    assert expected["requirements"] == ["astropy>=6"]
    assert expected["warnings"]


def test_unavailable_environment_and_empty_expectations_cannot_pass():
    expected = software_expectations()
    assert compare_environment(expected, {"state": "unavailable"})["state"] == "unknown"
    assert compare_environment(expected, environment())["state"] == "unknown"


def test_expected_application_identity_needs_a_package():
    with pytest.raises(ValueError, match="application package"):
        software_expectations(expected_version="1")


def test_local_source_revision_is_read_only_and_dirty_code_is_flagged(tmp_path, monkeypatch):
    from subprocess import CompletedProcess
    (tmp_path / "pyproject.toml").write_text('[project]\nname="science"\nversion="1"\n')
    (tmp_path / ".git").mkdir()
    commands = []
    def git(command, **options):
        commands.append(command)
        assert options["env"]["GIT_OPTIONAL_LOCKS"] == "0"
        return CompletedProcess(command, 0, "a" * 40 if "rev-parse" in command else " M science.py\n", "")
    monkeypatch.setattr("subprocess.run", git)
    expected = software_expectations(local_project=tmp_path)
    assert expected["expected_commit"] == "a" * 40
    assert expected["warnings"]
    assert all("fetch" not in command and "pull" not in command for command in commands)
