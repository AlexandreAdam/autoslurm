"""Standalone metadata probe, run with the selected environment's interpreter.

Do not import application packages: inspecting torch/JAX must not allocate a GPU,
initialize a scientific runtime, or execute application initialization code.
"""

import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from urllib.parse import unquote, urlsplit


def inspect_environment(names):
    result = {"state": "observed", "python": sys.executable, "prefix": sys.prefix,
              "python_version": platform.python_version(), "packages": {},
              "markers": {"implementation_name": sys.implementation.name,
                          "implementation_version": platform.python_version(),
                          "os_name": os.name, "platform_machine": platform.machine(),
                          "platform_python_implementation": platform.python_implementation(),
                          "platform_release": platform.release(), "platform_system": platform.system(),
                          "platform_version": platform.version(), "python_full_version": platform.python_version(),
                          "python_version": ".".join(platform.python_version_tuple()[:2]),
                          "sys_platform": sys.platform, "extra": ""}}
    for name in names:
        try:
            distribution = importlib.metadata.distribution(name)
        except importlib.metadata.PackageNotFoundError:
            result["packages"][name] = {"state": "missing"}
            continue
        except (OSError, ValueError):
            result["packages"][name] = {"state": "unavailable"}
            continue
        package = {"state": "installed", "version": distribution.version,
                   "location": str(distribution.locate_file("")), "source_commit": None,
                   "editable": False, "source_dirty": None}
        if not isinstance(package["version"], str) or not package["version"]:
            result["packages"][name] = {"state": "unavailable"}
            continue
        try:
            direct = distribution.read_text("direct_url.json")
            direct = json.loads(direct) if direct else {}
            package["source_commit"] = direct.get("vcs_info", {}).get("commit_id")
            package["editable"] = bool(direct.get("dir_info", {}).get("editable"))
            url = urlsplit(direct.get("url", ""))
            if package["editable"] and url.scheme == "file" and not url.netloc:
                source = unquote(url.path)
                package["source_path"] = source
                options = {"capture_output": True, "text": True, "timeout": 5,
                           "env": {**os.environ, "GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0"}}
                # Git discovers the enclosing repository for install subdirectories.
                commit = subprocess.run(["git", "-C", source, "rev-parse", "--verify", "HEAD"], **options)
                if commit.returncode == 0:
                    package["source_commit"] = commit.stdout.strip()
                    changes = subprocess.run(["git", "-C", source, "status", "--porcelain=v1", "--untracked-files=normal", "--ignore-submodules=all"], **options)
                    if changes.returncode == 0:
                        package["source_dirty"] = bool(changes.stdout.strip())
                else:
                    package["metadata_warning"] = "Editable source has no readable Git identity."
        except (OSError, ValueError, TypeError, AttributeError, subprocess.TimeoutExpired):
            package["metadata_warning"] = "Source metadata could not be verified."
        result["packages"][name] = package
    return result
