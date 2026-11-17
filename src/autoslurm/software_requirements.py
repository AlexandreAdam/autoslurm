"""Local declared expectations and pure comparison of target environment evidence."""

from pathlib import Path
import re
import subprocess
import os
import errno

from packaging.requirements import Requirement, InvalidRequirement
from packaging.specifiers import SpecifierSet, InvalidSpecifier
from packaging.utils import canonicalize_name
from packaging.version import Version, InvalidVersion
from .errors import DiagnosticError, DiagnosticCause, InvalidRequestError, _software_status_failure, _text


MAJOR_DEPENDENCIES = {"numpy", "jax", "jaxlib", "torch", "scipy"}


def _read_expectations(*, local_project=None, requirements=None, package=None,
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
        declaration = project_path / 'pyproject.toml'
        try:
            with declaration.open('rb') as stream:
                project = tomllib.load(stream).get('project', {})
        except (OSError, UnicodeError, tomllib.TOMLDecodeError) as native:
            raise _declaration_error(declaration, native) from native
        if (not isinstance(project, dict) or not isinstance(project.get('dependencies', []), list)
                or any(not isinstance(item, str) for item in project.get('dependencies', []))):
            raise InvalidRequestError('Project dependencies must be a list of requirement strings.',
                                      field='project.dependencies', stage='read_declarations', context={'path': str(declaration)})
        for key in ('name', 'version', 'requires-python'):
            if project.get(key) is not None and not isinstance(project[key], str):
                raise InvalidRequestError('Expected a string project declaration.', field='project.' + key,
                                          stage='read_declarations', context={'path': str(declaration)})
        package = package or project.get("name")
        expected_version = expected_version or project.get("version")
        python_requirement = project.get("requires-python")
        if python_requirement:
            SpecifierSet(python_requirement)
        declared.extend(project.get("dependencies", []))
        if requirements is None and (project_path / "requirements.txt").is_file():
            requirements = project_path / "requirements.txt"
        repository_found = False
        if expected_commit is None:
            for directory in (project_path, *project_path.parents):
                try:
                    (directory / '.git').stat()
                except OSError as error:
                    if error.errno not in (errno.ENOENT, errno.ENOTDIR):
                        warnings.append('Local Git discovery is unavailable; source identity is unverified.')
                        break
                else:
                    repository_found = True
                    break
        if expected_commit is None and repository_found:
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
            except (OSError, UnicodeError, subprocess.TimeoutExpired):
                warnings.append("Local Git revision could not be established.")
    seen = set()

    def read_requirements(path):
        path = Path(path).resolve()
        if path in seen or len(seen) >= 20:
            warnings.append("Requirements include cycle or limit; some declarations could not be checked.")
            return
        seen.add(path)
        try:
            lines = path.read_text(encoding='utf-8').splitlines()
        except (OSError, UnicodeError) as native:
            raise _declaration_error(path, native) from native
        for number, raw in enumerate(lines, 1):
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
            raise InvalidRequestError('package must be a distribution name.', field='package', stage='read_declarations')
    if expected_version is not None:
        Version(expected_version)
    if expected_commit is not None and not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", expected_commit):
        raise InvalidRequestError('expected_commit must be a full lowercase Git commit ID.', field='expected_commit', stage='read_declarations')
    if (expected_version is not None or expected_commit is not None) and package is None:
        raise InvalidRequestError('Specify the application package for a version or commit expectation.', field='package', stage='read_declarations')
    return {"requirements": focused, "package": package, "expected_version": expected_version,
            "expected_commit": expected_commit, "warnings": warnings,
            "python_requirement": python_requirement,
            "dependencies": sorted(selected), "local_project": str(project_path) if project_path else None}


def _declaration_error(path, native):
    code = 'resource_missing' if isinstance(native, FileNotFoundError) else 'resource_inaccessible' if isinstance(native, OSError) else 'record_invalid'
    return DiagnosticError(_software_status_failure(code, 'read_declarations', {'path': str(path), 'field': 'requirements'},
        DiagnosticCause.from_exception(native, detail='The local declaration could not be read or parsed.')))


def _name(value, field):
    if not isinstance(value, str) or re.fullmatch('[A-Za-z0-9][A-Za-z0-9._-]*', value) is None:
        raise InvalidRequestError('Use a distribution name for ' + field + '.', field=field, stage='read_declarations')
    return canonicalize_name(value)


def validate_expectations(value):
    """Pure validation of the public expectation dictionary, without caller mutation."""
    if not isinstance(value, dict):
        raise InvalidRequestError('expectations must be a software expectation mapping.', field='expectations', stage='select_software')
    allowed = {'dependencies', 'requirements', 'warnings', 'package', 'expected_version', 'expected_commit', 'python_requirement', 'local_project'}
    if set(value) - allowed:
        raise InvalidRequestError('Unknown expectation fields.', field='expectations', stage='select_software')
    result = dict(value)
    for field in ('dependencies', 'requirements', 'warnings'):
        entries = value.get(field)
        if (not isinstance(entries, (list, tuple)) or len(entries) > (100 if field == 'dependencies' else 1000)
                or any(not isinstance(item, str) or len(item) > 4096 for item in entries)):
            raise InvalidRequestError('Invalid expectation list: ' + field + '.', field=field, stage='select_software')
        result[field] = list(entries)
    result['dependencies'] = sorted(set(_name(name, 'dependencies') for name in result['dependencies']))
    result['package'] = _name(value['package'], 'package') if value.get('package') is not None else None
    for field in ('expected_version', 'expected_commit', 'python_requirement', 'local_project'):
        if value.get(field) is not None and not isinstance(value[field], str):
            raise InvalidRequestError('Expected a string for ' + field + '.', field=field, stage='select_software')
        result[field] = value.get(field)
    try:
        if result['expected_version'] is not None:
            Version(result['expected_version'])
        if result['python_requirement'] is not None:
            SpecifierSet(result['python_requirement'])
        for declaration in result['requirements']:
            requirement = Requirement(declaration)
            if requirement.url:
                raise InvalidRequestError('Direct requirement sources need separate verification; use software_expectations to read declarations safely.',
                                          field='requirements', stage='select_software')
            if canonicalize_name(requirement.name) not in result['dependencies']:
                raise InvalidRequestError('A requirement is outside the requested dependency scope.', field='dependencies', stage='select_software')
    except (InvalidVersion, InvalidRequirement, InvalidSpecifier) as native:
        raise InvalidRequestError('An expectation version or requirement could not be interpreted.', field='expectations', stage='select_software') from native
    commit = result['expected_commit']
    if commit is not None and re.fullmatch('[0-9a-f]{40}|[0-9a-f]{64}', commit) is None:
        raise InvalidRequestError('expected_commit must be a full lowercase Git commit ID.', field='expected_commit', stage='select_software')
    if (result['expected_version'] is not None or commit is not None) and result['package'] is None:
        raise InvalidRequestError('Specify the application package for a version or commit expectation.', field='package', stage='select_software')
    result['warnings'] = [_text(text) for text in result['warnings']]
    return result


def software_expectations(*, local_project=None, requirements=None, package=None,
                          expected_version=None, expected_commit=None, dependencies=()):
    """Read declared important dependencies with typed local diagnostics."""
    for field, value in (('local_project', local_project), ('requirements', requirements)):
        if value is not None and (not isinstance(value, (str, os.PathLike)) or not str(value).strip()
                                  or any(ord(c) < 32 or ord(c) == 127 for c in str(value))):
            raise InvalidRequestError('Use a local declaration path.', field=field, stage='read_declarations')
    if not isinstance(dependencies, (list, tuple, set)) or len(dependencies) > 95:
        raise InvalidRequestError('dependencies must be a bounded collection of distribution names.', field='dependencies', stage='read_declarations')
    for name in dependencies:
        _name(name, 'dependencies')
    if package is not None:
        _name(package, 'package')
    for field, value in (('expected_version', expected_version), ('expected_commit', expected_commit)):
        if value is not None and not isinstance(value, str):
            raise InvalidRequestError('Expected a string for ' + field + '.', field=field, stage='read_declarations')
    try:
        result = _read_expectations(local_project=local_project, requirements=requirements, package=package,
            expected_version=expected_version, expected_commit=expected_commit, dependencies=dependencies)
    except (InvalidVersion, InvalidSpecifier) as native:
        raise InvalidRequestError('The declared version or Python constraint could not be interpreted.', field='expected_version', stage='read_declarations') from native
    return validate_expectations(result)


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
            try:
                applies = requirement.marker.evaluate(environment=markers)
            except InvalidVersion:
                checks.append({'name': name, 'state': 'unknown', 'message': 'Target marker version could not be interpreted.'})
                continue
            if not applies:
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
    for name, actual in installed.items():
        if actual.get('diagnostic') is not None and actual.get('state') == 'installed':
            checks.append({'name': name, 'state': 'unknown', 'message': 'Additional installed-source metadata could not be verified.'})
    if environment.get('diagnostic') is not None:
        checks.append({'name': 'environment', 'state': 'unknown', 'message': 'Some environment metadata could not be verified.'})
    if not checks:
        checks.append({"name": "requirements", "state": "unknown", "message": "No focused dependency constraints or application expectation were supplied."})
    state = "potential_problem" if any(check["state"] == "mismatch" for check in checks) else "unknown" if any(check["state"] == "unknown" for check in checks) else "compatible"
    return {"state": state, "checks": checks,
            "scope": "Declared major dependency constraints and distribution metadata; no imports, GPU checks or transitive dependency verification."}
