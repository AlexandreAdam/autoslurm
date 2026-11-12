"""Standalone selected-interpreter verification; does not import scientific code."""

import importlib.metadata
import importlib.machinery
import os
from pathlib import Path
import platform
import sys

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name
from packaging.markers import default_environment


def inspect_runtime(artifacts=(), target=None, constraints=()):
    """Inspect actual visible distributions, their dependency closure and origins."""
    distributions = {}
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata.get("Name")
        if name:
            distributions.setdefault(canonicalize_name(name), distribution)
    inventory = {name: {"version": item.version, "location": str(item.locate_file(""))}
                 for name, item in sorted(distributions.items())}
    result = {"python": sys.executable, "prefix": sys.prefix, "python_version": platform.python_version(),
              "inventory": inventory, "commands": [], "errors": []}
    # Worker packaging is supplied in memory and must not become a runtime
    # dependency merely because it helped verify the selected environment.
    if not artifacts:
        return result
    target = Path(target).resolve()
    for project in artifacts:
        name = project["distribution"]
        installed = distributions.get(name)
        if (installed is None or installed.version != project["version"]
                or Path(installed.locate_file("")).resolve() != target):
            result["errors"].append(f"Wrong installed origin/version for {name}.")
            continue
        for module in project["modules"]:
            if module in sys.stdlib_module_names:
                result['errors'].append(f'Application module {module} conflicts with the Python standard library.')
                continue
            spec = importlib.machinery.PathFinder.find_spec(module, sys.path)
            origins = ([spec.origin] if spec and spec.origin else list(spec.submodule_search_locations or []) if spec else [])
            if not origins or any(not Path(origin).resolve().is_relative_to(target) for origin in origins):
                result["errors"].append(f"Import origin for {module} is outside the application release.")
        for entry in installed.entry_points:
            if entry.group == "console_scripts":
                if entry.module.split('.')[0] not in project['modules'] or not entry.name or '/' in entry.name or '\\' in entry.name:
                    result['errors'].append('Application entry point does not target its installed modules.')
                if entry.name in result["commands"]:
                    result["errors"].append("Requested applications have colliding command names.")
                result["commands"].append(entry.name)
                executable = target / "bin" / entry.name
                if not executable.is_file() or not os.access(executable, os.X_OK):
                    result["errors"].append(f"Installed entry point {entry.name} is unavailable.")
    queue = [(project["distribution"], frozenset()) for project in artifacts]
    visited = set()
    markers = default_environment()
    while queue:
        name, extras = queue.pop()
        if (name, extras) in visited:
            continue
        visited.add((name, extras))
        installed = distributions.get(name)
        if installed is None:
            result["errors"].append(f"Missing required distribution {name}.")
            continue
        python = installed.metadata.get("Requires-Python")
        if python and not SpecifierSet(python).contains(platform.python_version()):
            result["errors"].append(f"Python does not satisfy {name}'s requirement.")
        for text in installed.requires or []:
            requirement = Requirement(text)
            if requirement.marker and not any(requirement.marker.evaluate({**markers, "extra": extra}) for extra in (extras or {""})):
                continue
            dependency = canonicalize_name(requirement.name)
            actual = distributions.get(dependency)
            if requirement.url:
                result["errors"].append(f"Direct source dependency {dependency} needs explicit source verification.")
            elif actual is None or not requirement.specifier.contains(actual.version):
                result["errors"].append(f"Installed dependency {dependency} does not satisfy {name}'s requirements.")
            queue.append((dependency, frozenset(requirement.extras)))
    for text in constraints:
        requirement = Requirement(text)
        if requirement.marker and not requirement.marker.evaluate({**markers, "extra": ""}):
            continue
        actual = distributions.get(canonicalize_name(requirement.name))
        if actual and (requirement.url or not requirement.specifier.contains(actual.version)):
            result["errors"].append(f"Machine constraint for {requirement.name} is not satisfied.")
    result["commands"].sort()
    return result
