"""Local declared expectations and pure comparison of target environment evidence."""

from pathlib import Path
import re
import subprocess
import os

from packaging.requirements import Requirement, InvalidRequirement
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name
from packaging.version import Version, InvalidVersion


MAJOR_DEPENDENCIES = {"numpy", "jax", "jaxlib", "torch", "scipy"}


def software_expectations(*, local_project=None, requirements=None, package=None,
                          expected_version=None, expected_commit=None, dependencies=()):
    """Read project requirements, never the workstation's installed freeze."""
    selected = MAJOR_DEPENDENCIES | {canonicalize_name(name) for name in dependencies}
    declared, warnings = [], []
    python_requirement = None
    project_path = Path(local_project).resolve() if local_project is not None else None
    if project_path is not None:
        try:
            import tomllib
        except ImportError:  # Python < 3.11
            import tomli as tomllib
        with (project_path / "pyproject.toml").open("rb") as stream:
            project = tomllib.load(stream).get("project", {})
        package = package or project.get("name")
        expected_version = expected_version or project.get("version")
        python_requirement = project.get("requires-python")
        if python_requirement:
            SpecifierSet(python_requirement)
        declared.extend(project.get("dependencies", []))
        if requirements is None and (project_path / "requirements.txt").is_file():
            requirements = project_path / "requirements.txt"
        if expected_commit is None and any((directory / ".git").exists() for directory in (project_path, *project_path.parents)):
            try:
                options = {"capture_output": True, "text": True, "timeout": 5,
                           "env": {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}}
                commit = subprocess.run(["git", "-C", str(project_path), "rev-parse", "--verify", "HEAD"], **options)
                if commit.returncode == 0:
                    expected_commit = commit.stdout.strip()
                else:
                    warnings.append("Local Git revision could not be established.")
                dirty = subprocess.run(["git", "-C", str(project_path), "status", "--porcelain=v1", "--untracked-files=normal", "--ignore-submodules=all"], **options)
                if dirty.returncode or dirty.stdout.strip():
                    warnings.append("Local source cleanliness is unverified or changed; HEAD may not describe the desired code.")
            except (OSError, subprocess.TimeoutExpired):
                warnings.append("Local Git revision could not be established.")
    seen = set()

    def read_requirements(path):
        path = Path(path).resolve()
        if path in seen or len(seen) >= 20:
            warnings.append("Requirements include cycle or limit; some declarations could not be checked.")
            return
        seen.add(path)
        for number, raw in enumerate(path.read_text().splitlines(), 1):
            line = re.split(r"\s+#", raw, maxsplit=1)[0].strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith(("-r ", "--requirement ", "-c ", "--constraint ")):
                read_requirements(path.parent / line.split(maxsplit=1)[1])
            elif line.startswith("-"):
                # Never execute pip directives or treat ignored lines as verified.
                warnings.append(f"Unsupported requirements option at line {number}.")
            else:
                declared.append(line)
    if requirements is not None:
        read_requirements(requirements)
    focused = []
    for declaration in declared:
        try:
            requirement = Requirement(declaration)
        except InvalidRequirement:
            warnings.append("A requirement declaration could not be interpreted.")
            continue
        if canonicalize_name(requirement.name) in selected:
            if requirement.url:
                warnings.append(f"Direct source for {canonicalize_name(requirement.name)} needs separate source verification.")
                # Source addresses can contain credentials; never copy them to
                # terminal/status evidence merely to say they are unverifiable.
                focused.append(requirement.name + ("; " + str(requirement.marker) if requirement.marker else ""))
            else:
                focused.append(str(requirement))
    if package is not None:
        package = canonicalize_name(package)
        if not re.fullmatch(r"[a-z0-9][a-z0-9.-]*", package):
            raise ValueError("package must be a distribution name.")
    if expected_version is not None:
        Version(expected_version)
    if expected_commit is not None and not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", expected_commit):
        raise ValueError("expected_commit must be a full lowercase Git commit ID.")
    if (expected_version is not None or expected_commit is not None) and package is None:
        raise ValueError("Specify the application package for a version or commit expectation.")
    return {"requirements": focused, "package": package, "expected_version": expected_version,
            "expected_commit": expected_commit, "warnings": warnings,
            "python_requirement": python_requirement,
            "dependencies": sorted(selected), "local_project": str(project_path) if project_path else None}


def compare_environment(expectations, environment):
    """Report potential mismatches; absence/unknown evidence never becomes a pass."""
    checks = []
    for warning in expectations["warnings"]:
        checks.append({"name": "requirements", "state": "unknown", "message": warning})
    if environment.get("state") != "observed":
        return {"state": "unknown", "checks": checks + [{"name": "environment", "state": "unknown",
                "message": environment.get("error", "Selected environment could not be inspected.")}]}
    installed = environment["packages"]
    if expectations.get("python_requirement"):
        version = environment.get("python_version")
        try:
            matches = SpecifierSet(expectations["python_requirement"]).contains(Version(version)) if version else None
        except InvalidVersion:
            matches = None
        checks.append({"name": "python", "state": "unknown" if matches is None else "compatible" if matches else "mismatch",
                       "installed": version, "requirement": expectations["python_requirement"],
                       "message": "Target Python version versus the project's requires-python declaration."})
    for text in expectations["requirements"]:
        requirement = Requirement(text)
        name = canonicalize_name(requirement.name)
        if requirement.marker:
            markers = environment["markers"]
            used = {name for name in ("implementation_name", "implementation_version", "os_name", "platform_machine",
                    "platform_python_implementation", "platform_release", "platform_system", "platform_version",
                    "python_full_version", "python_version", "sys_platform", "extra")
                    if re.search(r"\b" + name + r"\b", str(requirement.marker))}
            if not used <= markers.keys():
                checks.append({"name": name, "state": "unknown", "message": "Target marker environment is incomplete."})
                continue
            if not requirement.marker.evaluate(environment=markers):
                continue
        actual = installed.get(name, {"state": "unknown"})
        check = {"name": name, "requirement": text, "installed": actual.get("version")}
        if actual["state"] == "missing":
            check.update(state="mismatch", message="Required dependency is not installed.")
        elif actual["state"] != "installed":
            check.update(state="unknown", message="Installed dependency version is unavailable.")
        elif requirement.url:
            check.update(state="unknown", message="A direct source requirement needs source verification.")
        elif not requirement.specifier:
            check.update(state="unknown", message="No version constraint is declared for this dependency.")
        else:
            try:
                matches = requirement.specifier.contains(Version(actual["version"]))
                check.update(state="compatible" if matches else "mismatch",
                             message="Installed version satisfies the declared requirement." if matches else "Installed version violates the declared requirement.")
            except InvalidVersion:
                check.update(state="unknown", message="Installed version could not be interpreted.")
        checks.append(check)
    name = expectations.get("package")
    if name:
        actual = installed.get(name, {"state": "unknown"})
        checks.append({"name": name, "state": "compatible" if actual["state"] == "installed" else "mismatch" if actual["state"] == "missing" else "unknown",
                       "installed": actual.get("version"), "message": "Application package installation."})
        if actual["state"] == "installed":
            desired = expectations["expected_version"]
            if desired:
                try:
                    matches = Version(actual["version"]) == Version(desired)
                    checks.append({"name": name, "state": "compatible" if matches else "mismatch",
                                   "installed": actual["version"], "expected": desired, "message": "Application package version."})
                except InvalidVersion:
                    checks.append({"name": name, "state": "unknown", "message": "Application version could not be compared."})
            commit = expectations["expected_commit"]
            if commit:
                actual_commit = actual.get("source_commit")
                checks.append({"name": name, "state": "unknown" if not actual_commit else "compatible" if commit == actual_commit else "mismatch",
                               "expected_commit": commit, "installed_commit": actual_commit,
                               "message": "Application Git revision; a version string alone does not establish this identity."})
            if actual.get("source_dirty"):
                checks.append({"name": name, "state": "mismatch", "message": "Installed editable source has local changes."})
            if actual.get("editable") and actual.get("source_dirty") is None:
                checks.append({"name": name, "state": "unknown", "message": "Editable source cleanliness could not be verified."})
            if actual.get("metadata_warning"):
                checks.append({"name": name, "state": "unknown", "message": actual["metadata_warning"]})
    if not checks:
        checks.append({"name": "requirements", "state": "unknown", "message": "No focused dependency constraints or application expectation were supplied."})
    state = "potential_problem" if any(check["state"] == "mismatch" for check in checks) else "unknown" if any(check["state"] == "unknown" for check in checks) else "compatible"
    return {"state": state, "checks": checks,
            "scope": "Declared major dependency constraints and distribution metadata; no imports, GPU checks or transitive dependency verification."}
