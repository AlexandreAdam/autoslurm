"""Shared machine, working-directory and application-path policy."""

from dataclasses import dataclass, replace
import json
from pathlib import Path, PurePosixPath
import shlex
import subprocess

from .storage import storage_root
from .config import machine_config as select_machine, is_remote_machine, normalize_machine_profile, recorded_transport, absolute_machine_path as _absolute
from .transport import remote_storage_root_from_config, ssh_command
from .errors import InvalidRequestError, SelectionError, selection_failure, ConfigurationError, DiagnosticCause

__all__ = ["ExecutionContext", "resolve_execution_context", "execution_context_from_snapshot", "recorded_execution"]
EXECUTION_METADATA_KEY = "_autoslurm_execution"


def _names(value, label):
    if value is None:
        return set()
    if not isinstance(value, (list, tuple)) or any(not isinstance(name, str) or not name for name in value):
        raise InvalidRequestError(f"{label} must be a list of argument names.", field=label, stage="resolve_job")
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
        return self._resolve_path(value, base, relative_only=relative_only, field="path")

    def _resolve_path(self, value, base, *, relative_only=False, field, option=None):
        facts = {"machine": self.machine_name}
        if option is not None:
            facts["option"] = option
        if isinstance(value, str):
            facts["logical_path"] = value
        def invalid(message):
            return InvalidRequestError(message, field=field, stage="resolve_path", context=facts)
        if not isinstance(value, str) or not value.strip():
            raise invalid("Application paths must be nonempty strings.")
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise invalid("Application paths must not contain control characters.")
        path = PurePosixPath(value)
        if not isinstance(base, str) or base not in {"project", "results", "storage"}:
            raise invalid("Unknown path base; use project, results or storage.")
        roots = {"project": self.project_root, "results": self.results_root, "storage": self.storage_root}
        root = roots[base]
        if path.is_absolute():
            facts["resolved_path"] = str(path)
        elif isinstance(root, str) and PurePosixPath(root).is_absolute():
            facts["resolved_path"] = str(PurePosixPath(root) / path)
        if relative_only and path.is_absolute():
            raise invalid("Application path must be relative to its declared root.")
        if ".." in path.parts:
            raise invalid("Application path must not traverse its declared root.")
        if path.is_absolute():
            return str(path)
        if root is None:
            raise invalid("Saved execution has no root for this path base.")
        if (not isinstance(root, str) or not PurePosixPath(root).is_absolute()
                or ".." in PurePosixPath(root).parts
                or any(ord(char) < 32 or ord(char) == 127 for char in root)):
            raise invalid("The selected path base needs an absolute root without traversal or control characters.")
        return str(PurePosixPath(root) / path)

    def resolve_job(self, job):
        try:
            return self._resolve_job(job)
        except InvalidRequestError as error:
            error.diagnostic = error.diagnostic.with_context(
                machine=self.machine_name,
                job=job.get("name") if isinstance(job, dict) and isinstance(job.get("name"), str) else None)
            raise

    def _resolve_job(self, job):
        if not isinstance(job, dict):
            raise InvalidRequestError("Every job must be a dictionary.", field="job", stage="resolve_job")
        for field in ("script_args", "slurm"):
            if job.get(field) is not None and not isinstance(job[field], dict):
                raise InvalidRequestError(f"{field} must be a mapping.", field=field, stage="resolve_job")
        arguments = dict(job.get("script_args") or {})
        slurm = job.get("slurm") or {}
        inputs = _names(job.get("input_args"), "input_args")
        results = _names(job.get("path_args"), "path_args") | {"output_dir"}
        if inputs & results:
            raise InvalidRequestError("An argument cannot be both a required input and a result path.", field="input_args", stage="resolve_job", context={"option": sorted(inputs & results)[0]})
        rooted = bool(self.config.get("results_root") or self.config.get("software_root"))
        strict = rooted or bool(inputs) or "working_directory" in job
        logical = {}
        resolved = {}
        for name in sorted(inputs | results):
            value = arguments.get(name)
            if name not in inputs and value in (None, ""):
                continue
            logical[name] = value
            resolved[name] = self._resolve_path(value, "project" if name in inputs else "results", relative_only=strict, field="script_args", option=name)
            arguments[name] = resolved[name]
        working_directory = None
        if rooted or inputs or "working_directory" in job:
            working_directory = self._resolve_path(job.get("working_directory", "."), "project", relative_only=True, field="working_directory")
            if slurm.get("chdir") is not None:
                raise InvalidRequestError("Use working_directory rather than a separate Slurm chdir directive.", field="slurm.chdir", stage="resolve_job")
        transport = recorded_transport(self.config)
        log_pattern = slurm.get("output")
        if log_pattern is not None and log_pattern != "":
            # Resolve against cwd for custom logs, retaining legacy unrooted paths.
            if working_directory:
                log_context = replace(self, results_root=working_directory)
                log_pattern = log_context._resolve_path(log_pattern, "results", relative_only=True, field="slurm.output")
            else:
                if not isinstance(log_pattern, str) or any(ord(c) < 32 or ord(c) == 127 for c in log_pattern):
                    raise InvalidRequestError("Slurm output must be a path string without control characters.", field="slurm.output", stage="resolve_path")
        else:
            log_pattern = str(PurePosixPath(self.storage_root) / "out/%x-%j.out")
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
    facts = {"bundle_path": str(bundle_path), "job": job_name if isinstance(job_name, str) else None}
    if job_name is not None and (not isinstance(job_name, str) or not job_name):
        raise InvalidRequestError("Select a nonempty saved job name.", field="job_name", stage="read_execution", context={"bundle_path": str(bundle_path)})
    matches = [job for job in jobs if job_name is None or job["name"] == job_name]
    if len(matches) != 1:
        raise SelectionError(selection_failure(stage="read_execution", problem="missing" if not matches else "invalid", summary="Select one exact saved job by name for artifact lookup.", context={**facts, "field": "job_name"}))
    facts["job"] = matches[0]["name"]
    evidence = matches[0].get(EXECUTION_METADATA_KEY)
    if EXECUTION_METADATA_KEY not in matches[0]:
        raise SelectionError(selection_failure(stage="read_execution", problem="missing", summary="Saved job has no recorded execution paths; select its original profile explicitly.", context={**facts, "field": EXECUTION_METADATA_KEY}))
    _validate_recorded_execution(evidence, facts)
    return evidence


def _validate_recorded_execution(evidence, facts):
    """Validate producing context data before lookup, never through today's profile."""
    facts = dict(facts)
    if isinstance(evidence, dict) and (isinstance(evidence.get("machine"), str) or evidence.get("machine") is None):
        facts["machine"] = evidence.get("machine")
    def invalid(field):
        paths = {"resolved_path": evidence[field]} if isinstance(evidence, dict) and field.endswith("root") and isinstance(evidence.get(field), str) else {}
        return SelectionError(selection_failure(stage="read_execution", problem="corrupt",
            summary="Saved execution paths or transport are invalid; retain the exact record and inspect its producing setup.",
            context={**facts, **paths, "field": f"{EXECUTION_METADATA_KEY}.{field}"}))
    if not isinstance(evidence, dict):
        raise invalid("context")
    if "machine" not in evidence or (evidence["machine"] is not None and not isinstance(evidence["machine"], str)):
        raise invalid("machine")
    for field in ("storage_root", "results_root", "project_root", "software_root"):
        value = evidence.get(field)
        if value is None and field in {"project_root", "software_root"}:
            continue
        if (not isinstance(value, str) or not PurePosixPath(value).is_absolute()
                or ".." in PurePosixPath(value).parts
                or any(ord(c) < 32 or ord(c) == 127 for c in value)):
            raise invalid(field)
    transport = evidence.get("transport")
    if not isinstance(evidence.get("is_remote"), bool) or not isinstance(transport, dict):
        raise invalid("transport")
    if evidence["is_remote"] != is_remote_machine(transport):
        raise invalid("transport")
    for field in ("ssh_alias", "hostname", "hosturl", "username"):
        if field in transport and (not isinstance(transport[field], str) or not transport[field].strip()):
            raise invalid("transport")
    try:
        recorded_transport(transport)
    except ConfigurationError as error:
        raise SelectionError(selection_failure(stage="read_execution", problem="corrupt",
            summary="Saved execution transport is invalid; retain its original evidence.",
            context={**facts, "field": f"{EXECUTION_METADATA_KEY}.transport"},
            cause=DiagnosticCause.from_exception(error, detail="Invalid producing SSH alias."))) from error


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
    transport = recorded_transport(config)
    key = json.dumps({"machine": name, "transport": transport}, sort_keys=True)
    return key, config
