"""Explicit local/SSH software inspection over the shared read-only probe."""

import json
from pathlib import Path, PurePosixPath
import subprocess

from .config import load_config, is_remote_machine, absolute_machine_path
from .software_probe import inspect_software_root
from .software_requirements import compare_environment
from .storage import storage_root
from .transport import ssh_command


def _validate_result(result, root, limit):
    if (not isinstance(result, dict) or result.get("version") != 1
            or result.get("software_root") != root or not isinstance(result.get("projects"), list)
            or result.get("state") not in {"observed", "missing", "unavailable"}
            or not isinstance(result.get("observed_at"), str) or type(result.get("truncated")) is not bool
            or len(result["projects"]) > limit):
        raise ValueError("Invalid software probe evidence.")
    for item in result["projects"]:
        if (not isinstance(item, dict) or not isinstance(item.get("name"), str) or not isinstance(item.get("path"), str)
                or item.get("state") not in {"observed", "missing", "not_a_repository", "outside_root", "unavailable"}
                or "dirty" not in item or "commit" not in item or "branch" not in item):
            raise ValueError("Invalid project evidence.")
        if item["state"] == "observed" and (type(item.get("bare")) is not bool
                or (not item["bare"] and type(item["dirty"]) is not bool)
                or not isinstance(item["commit"], str)):
            raise ValueError("Incomplete observed project evidence.")
    if "environment" in result:
        environment = result["environment"]
        if not isinstance(environment, dict) or environment.get("state") not in {"observed", "unavailable"}:
            raise ValueError("Invalid environment evidence.")
        if environment["state"] == "observed":
            if not isinstance(environment.get("packages"), dict) or not isinstance(environment.get("markers"), dict):
                raise ValueError("Invalid environment package evidence.")
            for package in environment["packages"].values():
                if (not isinstance(package, dict) or package.get("state") not in {"installed", "missing", "unavailable"}
                        or (package["state"] == "installed" and not isinstance(package.get("version"), str))):
                    raise ValueError("Invalid installed package evidence.")


def inspect_software(*, machine=None, project=None, limit=20, expectations=None):
    """Inspect configured software on one machine without installation or updates.

    Project selectors are relative to that machine's software_root. Remote probes
    use system python3 and need no remote AutoSlurm package or activated runtime.
    The result describes Git evidence, never environment readiness or latest Git
    upstream state. An unavailable observation must not become a clean checkout.
    """
    if (project is not None and (not isinstance(project, str) or not project
            or PurePosixPath(project).is_absolute() or ".." in PurePosixPath(project).parts
            or "\\" in project or any(ord(c) < 32 for c in project))):
        raise ValueError("project must be relative to software_root without traversal.")
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100.")
    config = load_config()
    name = machine or config["default_machine"]
    if name not in config["machines"]:
        raise ValueError(f"No configuration found for machine: {name}")
    profile = config["machines"][name]
    remote = is_remote_machine(profile)
    root = profile.get("software_root")
    if root is None:
        if remote:
            raise ValueError("Configure software_root before inspecting remote projects.")
        root = str(storage_root() / "software")
    root = absolute_machine_path(root, "software_root")
    environment_script, python_path = None, None
    if expectations is not None:
        names = sorted(set(expectations["dependencies"]) | ({expectations["package"]} if expectations["package"] else set()))
        environment_script = Path(__file__).with_name("environment_probe.py").read_text() + "\nprint(json.dumps(inspect_environment(" + repr(names) + ")))\n"
        if profile.get("venv_path"):
            python_path = absolute_machine_path(profile["venv_path"], "venv_path") + "/bin/python"
    if remote:
        # Package source is shipped through stdin, never copied/installed on disk.
        probe = Path(__file__).with_name("software_probe.py").read_text()
        script = probe + "\nprint(json.dumps(inspect_software_root(" + ", ".join(map(repr, (root, project, limit, python_path, environment_script))) + ")))\n"
        command = ssh_command(profile, name, "python3 -B -", options=[
            "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
            "-o", "ServerAliveInterval=10", "-o", "ServerAliveCountMax=2",
        ])
        try:
            response = subprocess.run(command, input=script, capture_output=True, text=True, timeout=60)
            if response.returncode:
                raise RuntimeError("SSH software inspection failed; check access through the configured alias and availability of python3.")
            if len(response.stdout) > 1024 * 1024:
                raise RuntimeError("Remote software status exceeded the response limit.")
            result = json.loads(response.stdout)
            _validate_result(result, root, limit)
        except (OSError, subprocess.TimeoutExpired, ValueError) as error:
            raise RuntimeError("Remote software inspection failed or returned invalid evidence.") from error
    else:
        result = inspect_software_root(root, project, limit, python_path, environment_script)
    if expectations is not None:
        result["expectations"] = expectations
        result["compatibility"] = compare_environment(expectations, result.get("environment", {"state": "unavailable"}))
    return {**result, "machine": name, "ssh_alias": profile.get("ssh_alias")}
