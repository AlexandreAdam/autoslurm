"""Shared machine, working-directory and application-path policy."""

from dataclasses import dataclass
import json
from pathlib import Path, PurePosixPath
import shlex
import subprocess

from .storage import storage_root
from .config import machine_config as select_machine, is_remote_machine, normalize_machine_profile, absolute_machine_path as _absolute
from .transport import remote_storage_root_from_config, ssh_command

__all__ = ["ExecutionContext", "resolve_execution_context", "execution_context_from_snapshot", "recorded_execution"]
EXECUTION_METADATA_KEY = "_autoslurm_execution"


def _names(value, label):
    if value is None:
        return set()
    if not isinstance(value, (list, tuple)) or any(not isinstance(name, str) or not name for name in value):
        raise ValueError(f"{label} must be a list of argument names.")
    return set(value)


@dataclass(frozen=True)
class ExecutionContext:
    machine_name: str | None
    config: dict
    storage_root: str
    project_root: str | None  # Historical input base; new contexts alias results_root.
    results_root: str
    is_remote: bool
    software_root: str | None = None

    def resolve_path(self, value, base="results", *, relative_only=False):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Application paths must be nonempty strings.")
        path = PurePosixPath(value)
        if base not in {"project", "results", "storage"}:
            raise ValueError(f"Unknown path base: {base!r}")
        if relative_only and path.is_absolute():
            raise ValueError(f"Application path must be relative: {value!r}")
        if ".." in path.parts:
            raise ValueError(f"Application path must not traverse its declared root: {value!r}")
        if path.is_absolute():
            return str(path)
        roots = {"project": self.project_root, "results": self.results_root, "storage": self.storage_root}
        root = roots[base]
        if root is None:
            raise ValueError("Saved execution has no root for this path base.")
        return str(PurePosixPath(root) / path)

    def resolve_job(self, job):
        arguments = dict(job.get("script_args") or {})
        inputs = _names(job.get("input_args"), "input_args")
        results = _names(job.get("path_args"), "path_args") | {"output_dir"}
        if inputs & results:
            raise ValueError("An argument cannot be both a required input and a result path.")
        rooted = bool(self.config.get("results_root") or self.config.get("software_root"))
        strict = rooted or bool(inputs) or "working_directory" in job
        logical = {}
        resolved = {}
        for name in sorted(inputs | results):
            value = arguments.get(name)
            if name not in inputs and value in (None, ""):
                continue
            if not isinstance(value, str):
                raise ValueError(f"Declared path argument {name!r} must be a nonempty string.")
            logical[name] = value
            resolved[name] = self.resolve_path(value, "project" if name in inputs else "results", relative_only=strict)
            arguments[name] = resolved[name]
        working_directory = None
        if rooted or inputs or "working_directory" in job:
            working_directory = self.resolve_path(job.get("working_directory", "."), "project", relative_only=True)
            if job.get("slurm", {}).get("chdir") is not None:
                raise ValueError("Use working_directory rather than a separate Slurm chdir directive.")
        transport = {key: self.config[key] for key in ("hostname", "hosturl", "username", "key_path") if key in self.config}
        log_pattern = job.get("slurm", {}).get("output") or str(PurePosixPath(self.storage_root) / "out/%x-%j.out")
        if working_directory and job.get("slurm", {}).get("output"):
            path = PurePosixPath(log_pattern)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("Slurm output paths must be relative without traversal.")
            log_pattern = str(PurePosixPath(working_directory) / path)
        return {
            "machine": self.machine_name, "storage_root": self.storage_root,
            "results_root": self.results_root,
            "software_root": self.software_root,
            "working_directory": working_directory,
            "logical_working_directory": job.get("working_directory", ".") if working_directory else None,
            "logical_paths": logical, "resolved_paths": resolved,
            "script_args": arguments, "input_args": sorted(inputs),
            "log_pattern": log_pattern,
            "transport": transport, "is_remote": self.is_remote,
        }

    def validate_jobs(self, jobs):
        self.validate_resolved_jobs([self.resolve_job(job) for job in jobs])

    def validate_resolved_jobs(self, executions):
        """Preflight prepared paths without resolving the definitions again."""
        checks = set()
        if self.project_root is not None and any(item["working_directory"] for item in executions):
            checks.add(("-d", self.project_root, "Data root"))
        for resolved in executions:
            if resolved["working_directory"]:
                checks.add(("-d", resolved["working_directory"], "Working directory"))
            for name in resolved["input_args"]:
                checks.add(("-e", resolved["resolved_paths"][name], f"Required input {name}"))
        if not checks:
            return
        if not self.is_remote:
            for kind, path, label in sorted(checks):
                exists = Path(path).is_dir() if kind == "-d" else Path(path).exists()
                if not exists:
                    raise FileNotFoundError(f"{label} is unavailable: {path}")
            return
        commands = [
            f"test {kind} {shlex.quote(path)} || {{ echo {shlex.quote(label + ' is unavailable: ' + path)} >&2; exit 1; }}"
            for kind, path, label in sorted(checks)
        ]
        result = subprocess.run(ssh_command(self.config, self.machine_name, "; ".join(commands)), capture_output=True, text=True)
        if result.returncode != 0:
            raise FileNotFoundError(f"Machine {self.machine_name!r} path preflight failed: {result.stderr.strip() or result.stdout.strip()}")


def resolve_execution_context(machine_name=None, machine_config=None, *, root_resolver=None):
    """Resolve one selected profile once; pass this context through an operation."""
    if machine_config is None:
        machine_name, machine_config = select_machine(machine=machine_name)
    config = normalize_machine_profile(machine_config)
    configured_results = _absolute(config["results_root"], "Machine results_root") if config.get("results_root") else None
    remote = is_remote_machine(config)
    if remote:
        root = (root_resolver or remote_storage_root_from_config)(config, machine_name)
    else:
        root = str(storage_root())
    root = _absolute(root, "Storage root")
    results = configured_results or str(PurePosixPath(root) / "results")
    software = config.get("software_root") or str(PurePosixPath(root) / "software")
    return ExecutionContext(machine_name, config, root, results, results, remote, software)


def recorded_execution(bundle_path, job_name=None):
    """Read a saved job's logical/resolved paths without current-profile discovery."""
    from .save_load_jobs import load_bundle_from_path

    jobs, _, _ = load_bundle_from_path(bundle_path)
    matches = [job for job in jobs if job_name is None or job["name"] == job_name]
    if len(matches) != 1:
        raise ValueError("Select one exact saved job by name for artifact lookup.")
    evidence = matches[0].get(EXECUTION_METADATA_KEY)
    if not evidence:
        raise ValueError("Saved job has no recorded execution paths; select its original profile explicitly.")
    return evidence


def execution_context_from_snapshot(bundle_path, job_name=None):
    """Use producing roots/transport, with no discovery through today's profile."""
    evidence = recorded_execution(bundle_path, job_name)
    return ExecutionContext(
        evidence["machine"], dict(evidence["transport"]),
        evidence["storage_root"], evidence.get("project_root", evidence["results_root"]), evidence["results_root"], evidence["is_remote"],
        evidence.get("software_root"),
    )


def producing_machine(job, profiles):
    """Interpret provided producing metadata/profiles without discovery or I/O."""
    execution = job.get(EXECUTION_METADATA_KEY)
    name = job.get("machine")
    if not isinstance(profiles, dict):
        raise ValueError("Producing machine profiles are invalid; no local fallback.")
    if EXECUTION_METADATA_KEY in job:
        if not isinstance(execution, dict) or not isinstance(execution.get("is_remote"), bool):
            raise ValueError("Invalid recorded producing machine metadata; no local fallback.")
        transport = execution.get("transport")
        if not isinstance(transport, dict) or execution["is_remote"] != is_remote_machine(transport):
            raise ValueError("Recorded producing transport is unavailable or inconsistent; no local fallback.")
        config = transport if execution["is_remote"] else {}
    elif name is None:
        config = {}
    else:
        if name not in profiles or not isinstance(profiles[name], dict):
            raise ValueError(f"Producing machine {name!r} is unavailable; no local fallback.")
        config = profiles[name]
    transport = {key: config[key] for key in ("hostname", "hosturl", "username", "key_path") if key in config}
    key = json.dumps({"machine": name, "transport": transport}, sort_keys=True)
    return key, config
