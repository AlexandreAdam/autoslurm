"""Machine-owned runtime policy and pure release/request identity rules."""

from pathlib import PurePosixPath
import re

from .machine_paths import absolute_machine_path


def release_identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{32}", value):
        raise ValueError("Release ID must be the exact 32-character preparation ID.")
    return value


def runtime_policy(profile, runtime="default"):
    policies = profile.get("software_runtimes", {})
    if not isinstance(policies, dict) or (runtime != "default" and runtime not in policies):
        raise ValueError("Configure the requested software runtime on this machine.")
    if not isinstance(policies.get(runtime, {}), dict):
        raise ValueError('Software runtime must be a mapping.')
    policy = dict(policies.get(runtime, {}))
    if set(policy) - {"python", "constraints"}:
        raise ValueError("Runtime policy supports only python and constraints; dependencies stay unchanged.")
    python = policy.get("python")
    if python is None:
        if not profile.get("venv_path"):
            raise ValueError("Configure venv_path or a software_runtimes Python interpreter before preparation.")
        python = str(PurePosixPath(absolute_machine_path(profile["venv_path"], "venv_path")) / "bin/python")
    result = {"name": runtime, "python": absolute_machine_path(python, "Runtime Python"),
              "dependency_mode": "existing_environment"}
    if policy.get("constraints"):
        result["constraints"] = absolute_machine_path(policy["constraints"], "Runtime constraints")
    return result
