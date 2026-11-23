"""Diagnostic facts and expected exceptions. No I/O, backend imports or recovery.

Callers own classification, operation effects and authoritative result/receipt
objects. Only bounded, redacted plain facts cross the diagnostic boundary.
"""

from dataclasses import dataclass, field, replace
import re
from types import MappingProxyType
from typing import Mapping

__all__ = ["Diagnostic", "DiagnosticCause", "DiagnosticError", "diagnostic_catalog",
           "invalid_argument", "missing_resource", "command_failure",
           "ConfigurationError", "configuration_failure", "InvalidRequestError",
           "SelectionError", "selection_failure", "RecordWriteError",
           "RecordCollisionError", "record_write_failure"]

# code -> (category, summary, next action). Effects never come from this catalogue.
_CATALOG = {
    "invalid_argument": ("validation", "An argument is invalid.", "Correct the named argument and validate again."),
    "configuration_invalid": ("configuration", "The selected configuration is invalid.", "Correct the identified setting in the selected profile."),
    "resource_missing": ("resource", "The selected resource was not found.", "Verify the identified path and configuration."),
    "resource_inaccessible": ("resource", "The selected resource cannot be accessed.", "Verify access to the identified resource; availability is unknown."),
    "record_invalid": ("storage", "The selected record is invalid.", "Inspect the exact record and retain the original evidence."),
    "storage_failed": ("storage", "A storage operation failed.", "Inspect the destination and publication evidence before repeating a write."),
    "command_unavailable": ("process", "The requested executable could not be started.", "Verify the configured executable and its permissions."),
    "command_failed": ("process", "An external command failed.", "Inspect the command detail and recorded effects before deciding what to do next."),
    "command_timeout": ("process", "An external command timed out.", "Inspect retained evidence before deciding whether to repeat any action."),
    "transport_failed": ("transport", "Communication with the selected machine failed.", "Verify access through the operator-owned SSH configuration and inspect retained evidence."),
    "protocol_invalid": ("protocol", "The helper response could not be interpreted.", "Check helper compatibility and inspect retained evidence before repeating an action."),
    "scheduler_rejected": ("scheduler", "The scheduler rejected the request.", "Review the scheduler detail and selected resource settings; preserve any earlier accepted IDs."),
    "outcome_unknown": ("outcome", "The operation outcome has not been observed.", "Inspect the exact receipt or destination before deciding whether to repeat any action."),
    "observation_unavailable": ("observation", "The requested observation is unavailable.", "Retain last-known evidence and explicitly check the selected source."),
    "compatibility_mismatch": ("compatibility", "Observed software does not match the requested setup.", "Review expected and observed software; environment preparation remains explicit."),
    "operation_interrupted": ("interruption", "The operation was interrupted.", "Inspect retained effects and evidence before taking another action."),
    "internal_error": ("internal", "An internal operation failed.", "Retain evidence and inspect the original exception through the debug interface."),
}
_CONTEXT_KEYS = frozenset({"machine", "ssh_alias", "project", "bundle", "bundle_path",
    "receipt_path", "submission_id", "job", "job_id", "task", "field", "option",
    "logical_path", "resolved_path", "path", "executable", "resource", "command",
    "source", "freshness", "observed_at", "observation_state", "storage_root"})
_EFFECT_STATES = frozenset({"not_started", "succeeded", "failed", "partial", "unknown"})
_URL_USERINFO = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)[^\s/]*@")
_CREDENTIAL = re.compile(
    r"(?i)(\b(?:password|passwd|token|access_token|api[_-]?key|authorization|secret|x-amz-signature)"
    r"\s*(?:=|:)\s*)(?:\"[^\"]*\"|'[^']*'|[^\s&;,]+)")
_PRIVATE_KEY = re.compile(r"-----BEGIN [^-]*PRIVATE KEY-----.*?(?:-----END [^-]*PRIVATE KEY-----|$)", re.S)
_AUTHORIZATION = re.compile(r"(?im)(\bauthorization\s*:\s*)[^\r\n]*")
_SECRET_OPTION = re.compile(r"(?i)(--(?:password|token|api-key|secret)\s+)(?:\"[^\"]*\"|'[^']*'|[^\s,\]]+)")


def _text(value, limit=512, *, multiline=False):
    if not isinstance(value, str):
        raise TypeError("Diagnostic text must be a string.")
    # Redact before bounding: truncation must not leave half a credential URL.
    value = _PRIVATE_KEY.sub("[redacted private key]", value)
    value = _URL_USERINFO.sub(r"\1[redacted]@", value)
    value = _AUTHORIZATION.sub(r"\1[redacted]", value)
    value = _SECRET_OPTION.sub(r"\1[redacted]", value)
    value = _CREDENTIAL.sub(r"\1[redacted]", value)
    value = "".join(char if (multiline and char in "\n\t") or char.isprintable() else "?" for char in value)
    encoded = value.encode("utf-8", errors="replace")
    if len(encoded) > limit:
        return encoded[:limit - 3].decode("utf-8", errors="ignore") + "..."
    return encoded.decode("utf-8")


def _label(value, name):
    if not isinstance(value, str) or re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,63}", value) is None:
        raise ValueError(f"Diagnostic {name} must be a short identifier.")
    return value


def _integer(value, name):
    if value is not None and (type(value) is not int or not -(2**63) <= value < 2**63):
        raise ValueError(f"Diagnostic {name} must be a signed 64-bit integer or None.")
    return value


def diagnostic_catalog():
    """Return detached code/category/default wording, never live mutable policy."""
    return {code: {"category": row[0], "summary": row[1], "next_action": row[2]}
            for code, row in _CATALOG.items()}


@dataclass(frozen=True)
class DiagnosticCause:
    kind: str
    detail: str = ""
    errno: int | None = None
    returncode: int | None = None

    def __post_init__(self):
        _label(self.kind, "cause kind")
        object.__setattr__(self, "detail", _text(self.detail, 4096, multiline=True))
        _integer(self.errno, "errno")
        _integer(self.returncode, "returncode")

    @classmethod
    def from_exception(cls, error, *, detail=None, returncode=None):
        """Capture safe facts, not an outcome or a replacement exception chain.

        Callers pass relevant command detail rather than whole configs/environments.
        The original exception remains attached with Python's ``raise ... from``.
        """
        if not isinstance(error, BaseException):
            raise TypeError("A cause must originate from an exception.")
        return cls(type(error).__name__, str(error) if detail is None else detail,
                   getattr(error, "errno", None),
                   getattr(error, "returncode", None) if returncode is None else returncode)

    def to_dict(self):
        return {"kind": self.kind, "detail": self.detail,
                "errno": self.errno, "returncode": self.returncode}


@dataclass(frozen=True)
class Diagnostic:
    code: str
    operation: str
    stage: str
    context: Mapping = field(default_factory=dict)
    cause: DiagnosticCause | None = None
    effects: Mapping = field(default_factory=dict)
    summary: str | None = None
    next_action: str | None = None
    secondary: tuple = ()

    def __post_init__(self):
        if self.code not in _CATALOG:
            raise ValueError(f"Unknown diagnostic code: {self.code!r}")
        _label(self.operation, "operation")
        _label(self.stage, "stage")
        if not isinstance(self.context, Mapping) or set(self.context) - _CONTEXT_KEYS:
            raise ValueError("Diagnostic context must use the documented identity/observation fields.")
        context = {}
        for key, value in self.context.items():
            if value is not None and type(value) not in (str, int, bool):
                raise TypeError("Diagnostic context values must be strings, integers, booleans or None.")
            if type(value) is int:
                _integer(value, "context integer")
            context[key] = _text(value) if isinstance(value, str) else value
        if self.cause is not None and not isinstance(self.cause, DiagnosticCause):
            raise TypeError("Diagnostic cause must be DiagnosticCause or None.")
        if not isinstance(self.effects, Mapping) or len(self.effects) > 32:
            raise ValueError("Diagnostic effects must contain at most 32 named steps.")
        effects = {}
        for key, value in self.effects.items():
            _label(key, "effect step")
            if not isinstance(value, str) or value not in _EFFECT_STATES:
                raise ValueError("Diagnostic effect must be not_started, succeeded, failed, partial or unknown.")
            effects[key] = value
        if not isinstance(self.secondary, (tuple, list)):
            raise TypeError("Secondary diagnostics must be a plain tuple or list.")
        children = tuple(self.secondary)
        if len(children) > 4 or any(not isinstance(child, Diagnostic) or child.secondary for child in children):
            raise ValueError("Select at most four leaf secondary diagnostics.")
        summary = _CATALOG[self.code][1] if self.summary is None else self.summary
        action = _CATALOG[self.code][2] if self.next_action is None else self.next_action
        if not isinstance(summary, str) or not summary.strip() or not isinstance(action, str) or not action.strip():
            raise ValueError("Diagnostic summary and next action must be nonempty strings.")
        object.__setattr__(self, "context", MappingProxyType(context))
        object.__setattr__(self, "effects", MappingProxyType(effects))
        object.__setattr__(self, "summary", _text(summary))
        object.__setattr__(self, "next_action", _text(action, 1024))
        object.__setattr__(self, "secondary", children)

    @property
    def category(self):
        return _CATALOG[self.code][0]

    def with_context(self, **context):
        """Add known identity; refuse to redirect or replace existing context."""
        for key, value in context.items():
            # Stored identities are already redacted/bounded. Re-enrichment of
            # the same long identity must compare using that same representation.
            compared = _text(value) if isinstance(value, str) else value
            if key in self.context and self.context[key] != compared:
                raise ValueError(f"Diagnostic context conflicts for {key}.")
        return replace(self, context={**self.context, **context})

    def with_secondary(self, *diagnostics):
        """Retain primary diagnosis/effects while adding bounded secondary failures."""
        return replace(self, secondary=self.secondary + diagnostics)

    def to_dict(self):
        """Detached JSON-safe facts. Never serializes exceptions or domain payloads."""
        return {"version": 1, "code": self.code, "category": self.category,
                "summary": self.summary, "operation": self.operation, "stage": self.stage,
                "context": dict(self.context), "cause": self.cause.to_dict() if self.cause else None,
                "effects": dict(self.effects), "next_action": self.next_action,
                "secondary": [child.to_dict() for child in self.secondary]}


class DiagnosticError(RuntimeError):
    """Expected operation error; original causes use normal exception chaining.

    Legacy subclasses may carry only a message and diagnostic=None during adoption.
    Such errors are deliberately not handled by the new terminal adapter yet.
    """

    def __init__(self, message, *, diagnostic=None):
        if isinstance(message, Diagnostic):
            if diagnostic is not None:
                raise TypeError("Provide one diagnostic.")
            diagnostic, message = message, message.summary
        if diagnostic is not None and not isinstance(diagnostic, Diagnostic):
            raise TypeError("Provide an optional Diagnostic, or one Diagnostic as the message.")
        self.diagnostic = diagnostic
        super().__init__(message)


class ConfigurationError(DiagnosticError, ValueError):
    """Known configuration read/validation failure, carrying a Diagnostic.

    ValueError compatibility remains for validation callers. File read failures
    now use this family too; their original OSError remains in __cause__.
    """


class SelectionError(DiagnosticError, ValueError):
    """Known selection/record-read failure; unavailable is distinct from absent.

    Missing selections use this same family rather than FileNotFoundError.
    Native filesystem causes remain chained; codes distinguish failure kinds.
    """


class RecordWriteError(DiagnosticError, OSError):
    """Expected JSON/text publication failure with filesystem effect facts.

    OSError compatibility lets existing evidence-preserving callers retain their
    policy. Serialization failures also use this family at this dev boundary;
    the original TypeError/ValueError remains chained, never copied as payload.
    """


class RecordCollisionError(RecordWriteError, FileExistsError):
    """Exclusive publication observed an existing destination.

    Only a collision without secondary cleanup errors permits selecting another
    snapshot name. Other publication failures may already have changed the file.
    """


def record_write_failure(*, stage, path, effects, cause, problem="storage"):
    """Describe caller-observed writer facts; no I/O or inferred rollback/retry."""
    if problem not in {"storage", "serialization", "collision"}:
        raise ValueError("Unknown record publication problem.")
    summary = {
        "storage": f"Local record publication failed during {stage}.",
        "serialization": "Record data cannot be encoded for publication.",
        "collision": "Exclusive record publication found an existing destination.",
    }[problem]
    return Diagnostic("invalid_argument" if problem == "serialization" else "storage_failed",
        "record_publication", stage, context={"path": path, "field": "record_data"} if problem == "serialization" else {"path": path},
        effects=effects, cause=cause, summary=summary,
        next_action="Inspect the exact destination and publication/durability facts before repeating any write; retain existing records and original evidence.")


def _software_update_failure(*, problem, check, context, effects, cause=None, summary=None):
    """Describe validated update facts; never infer effects from an error code."""
    if problem not in {"invalid_argument", "resource_missing", "resource_inaccessible",
            "command_unavailable", "command_failed", "command_timeout", "operation_interrupted",
            "protocol_invalid", "compatibility_mismatch", "transport_failed", "outcome_unknown"}:
        raise ValueError("Unknown software update failure.")
    action = "Inspect the existing checkout and before/after commit evidence before repeating an update; do not reset or merge automatically."
    if check == "environment_python":
        executable = context.get("executable", "the configured environment Python")
        if problem == "command_unavailable":
            summary = f"Cannot start the configured environment Python at {executable}; correct venv_path in asl config. Pull and installation were not started."
        elif problem == "compatibility_mismatch":
            summary = f"Python at {executable} does not identify the configured virtual environment; pull and installation were not started."
        elif summary is None:
            summary = f"Could not verify the configured environment Python at {executable}; pull and installation were not started."
        action = "Correct venv_path for the selected machine with asl config --interactive; verify that environment's bin/python before updating again."
    elif check == "editable_install":
        if problem == "command_unavailable":
            summary = f"Cannot start editable installation with {context.get('executable')}; Git pull completed but installation did not start."
        action = "Inspect the retained pulled commit, selected environment and pip output tail; installation may be partial. Do not submit jobs until the environment is verified."
    elif check.startswith("git_") and problem == "command_unavailable":
        summary = "Git could not be started for the selected checkout."
        if all(value == "not_started" for value in effects.values()):
            summary += " Pull and installation were not started."
    elif check.startswith("ssh_update"):
        action = "Check access using the operator-owned SSH alias, then inspect the checkout and selected environment; a lost response may follow a completed update, so do not retry blindly."
    elif check == "probe_source":
        action = "Verify the identified installed AutoSlurm helper source file; no update was dispatched."
    return Diagnostic(problem, "software_update", check, context=context, effects=effects,
                      cause=cause, summary=summary, next_action=action)


def _record_read_failure(*, path, code, stage, context=None, cause=None, summary=None):
    """Pure local-read facts; absence never implies a scheduler outcome."""
    if code not in {"invalid_argument", "resource_missing", "resource_inaccessible", "record_invalid"}:
        raise ValueError("Unknown record read failure.")
    return Diagnostic(code, "record_read", stage, context={"path": path, **(context or {})},
        cause=cause, summary=summary,
        next_action="Inspect the exact record path and retain its original contents; unavailable evidence is unknown, not permission to repeat a submission.")


def selection_failure(*, stage, problem="invalid", summary=None, context=None, cause=None):
    """Construct explicit selection facts without lookup, recovery or effect inference."""
    problems = {
        "invalid": ("invalid_argument", "The bundle selector is invalid.",
                    "Correct the named selector and select the exact saved bundle again."),
        "missing": ("resource_missing", "No matching saved bundle was found.",
                    "Verify the exact selector and storage root; do not automatically choose another bundle."),
        "unreadable": ("resource_inaccessible", "The selected snapshot or directory cannot be read.",
                       "Check the identified path and permissions; retain existing records and treat contents as unknown."),
        "corrupt": ("record_invalid", "The saved bundle is invalid.",
                    "Inspect the exact saved bundle and retain its original contents; rebuild a definition explicitly if needed."),
    }
    if problem not in problems:
        raise ValueError("Unknown selection problem.")
    code, wording, action = problems[problem]
    return Diagnostic(code, "selection", stage, context={} if context is None else context,
                      cause=cause, summary=wording if summary is None else summary, next_action=action)


def configuration_failure(*, stage, problem="invalid", summary=None, context=None,
                          cause=None, effects=None):
    """Construct known configuration facts; caller supplies actual effect evidence."""
    problems = {
        "invalid": ("configuration_invalid", "The selected configuration is invalid.",
                    "Correct the named setting in the selected profile or exact configuration file; preserve existing evidence."),
        "missing": ("resource_missing", "Configuration file not found.",
                    "Create a profile with `asl config --interactive` in the selected storage root."),
        "unreadable": ("resource_inaccessible", "The configuration file could not be read.",
                       "Check the selected configuration path and access permissions; preserve the existing file."),
        "corrupt": ("record_invalid", "The configuration file is not valid JSON text.",
                    "Correct the exact configuration file after retaining its original contents."),
    }
    if problem not in problems:
        raise ValueError("Unknown configuration problem.")
    code, wording, action = problems[problem]
    return Diagnostic(code, "configuration", stage,
                      context={} if context is None else context, cause=cause,
                      effects={} if effects is None else effects,
                      summary=wording if summary is None else summary, next_action=action)


def _module_detection_failure(problem, context, cause):
    codes = {"missing": "resource_missing", "transport": "transport_failed",
             "timeout": "command_timeout", "unavailable": "command_unavailable",
             "response": "protocol_invalid"}
    summary = ("No readable module initializer was found among the known site paths."
               if problem == "missing" else "Module initializer detection could not finish; configuration was not changed.")
    return Diagnostic(codes[problem], "configure_environment", "detect_module_init",
        context=context, cause=cause, summary=summary,
        effects={"config_write": "not_started"},
        next_action="Use asl config --machine NAME --module-init /absolute/site/init.sh for a site-specific path; verify access if detection failed. Detection never sources files or runs env_command.")


def _environment_setup_failure_message(field):
    """Wording embedded in generated Bash; no runtime Python dependency in jobs."""
    messages = {"module_init": "module initialization failed (module_init)",
                "env_command": "environment activation failed during setup (env_command)",
                "venv_path": "environment activation failed (venv_path)"}
    return f"AutoSlurm {messages[field]}; application not started."


def _receipt_fetch_failure(problem, context, cause=None):
    facts = {
        'identity': ('record_invalid', 'The execution receipt has no valid recorded transport; no host fallback was attempted.'),
        'missing': ('resource_missing', 'The recorded execution receipt is missing.'),
        'unreadable': ('resource_inaccessible', 'The execution receipt cannot be read; availability is unknown.'),
        'not_regular': ('record_invalid', 'The execution receipt path is not a regular file.'),
        'read': ('observation_unavailable', 'Reading the execution receipt failed.'),
        'changed': ('observation_unavailable', 'The execution receipt changed during reading; the previous evidence is retained.'),
        'transport': ('transport_failed', 'SSH could not fetch the recorded execution receipt.'),
        'command': ('command_failed', 'Execution receipt reader failed; verify python3 on the recorded machine.'),
        'timeout': ('command_timeout', 'Fetching the execution receipt timed out.'),
        'launch': ('command_unavailable', 'The execution receipt transport could not be started.'),
        'protocol': ('protocol_invalid', 'Execution receipt response is invalid, incomplete or exceeds 1 MiB.'),
    }
    code, summary = facts[problem]
    return Diagnostic(code, 'fetch_evidence', 'read_execution_receipt', context=context,
        cause=cause, summary=summary, effects={'remote_mutation': 'not_started', 'receipt_refresh': 'failed'},
        next_action='Retain known scheduler IDs and inspect their status/logs. Verify the recorded receipt path, SSH alias and python3; explicitly refresh again when available. Do not resubmit because fetching failed.')


def _readiness_failure(problem, stage, context, cause=None):
    """Describe pre-submission probe facts without guessing SSH/authentication causes."""
    summaries = {
        'configuration_invalid': 'Remote readiness configuration is invalid.',
        'command_unavailable': 'The local SSH executable could not be started for the readiness check.',
        'command_timeout': 'The remote readiness check timed out.',
        'operation_interrupted': 'The remote readiness command was interrupted.',
        'transport_failed': 'SSH could not complete the remote readiness check.',
        'command_failed': 'The remote readiness command failed; helper availability is unverified.',
        'protocol_invalid': 'The remote readiness response is invalid or exceeds its supported size.',
        'compatibility_mismatch': 'The remote helper does not match the selected readiness contract.',
    }
    summary = summaries[problem]
    action = 'Verify access through the operator-owned SSH alias and check the selected environment/helper; no credential handling, alternate host or automatic retry is attempted.'
    if context.get('field') == 'storage_root':
        if problem == 'configuration_invalid':
            summary = 'Machine storage_root must be a nonempty absolute POSIX path without traversal or control characters.'
        elif problem == 'compatibility_mismatch':
            summary = 'Remote storage root mismatch: the helper reported a different storage root than requested.'
        action = 'Check storage_root, env_command and venv_path in the selected asl config profile; verify that environment imports the matching AutoSlurm helper. Do not switch to another storage root implicitly.'
    elif context.get('field') == 'venv_path':
        if problem == 'configuration_invalid':
            summary = 'Remote submission requires a prepared venv_path with an absolute path to its environment.'
        elif problem == 'compatibility_mismatch':
            summary = 'Remote helper capabilities are incompatible; update AutoSlurm in the configured venv_path before submitting.'
        action = 'Verify the identified venv_path/bin/python and update AutoSlurm there explicitly if its helper is outdated; verify SSH access through the configured alias. No environment is installed or repaired automatically.'
    if problem == 'command_unavailable':
        action = 'Verify the local ssh executable and its permissions first; the remote helper and environment have not been verified. Then check the selected SSH alias/profile explicitly.'
    return Diagnostic(problem, 'remote_readiness', stage, context=context, cause=cause,
        summary=summary, next_action=action,
        effects={'script_transfer': 'not_started', 'submission_dispatch': 'not_started', 'scheduler_submission': 'not_started'})


def _ssh_session_failure(problem, stage, context, effects, cause=None):
    """Owned local session facts only; never infer scheduler effects or auth causes."""
    summaries = {
        'create_session_directory': 'AutoSlurm could not create its local SSH control-socket directory.',
        'validate_control_path': 'AutoSlurm\'s SSH control-socket path is too long for a safe Unix socket.',
        'open_session': 'AutoSlurm could not confirm opening its owned SSH session; submission was not dispatched through this session.',
        'close_session': 'AutoSlurm could not confirm SSH session cleanup; retain the submission receipt and do not resubmit because of this cleanup failure.',
        'remove_session_directory': 'AutoSlurm could not remove its local SSH socket directory; retain the submission receipt and inspect local cleanup.',
    }
    return Diagnostic(problem, 'ssh_session', stage, context=context, effects=effects, cause=cause,
        summary=summaries[stage],
        next_action=('Use a short writable local temporary directory (normally /tmp); verify its permissions and available space. No submission was dispatched through this session.'
                     if stage in {'create_session_directory', 'validate_control_path'} else
                     'Check the operator-owned SSH alias and retained session effects. Cleanup does not change scheduler acceptance; preserve known IDs and inspect the exact receipt/status before any new submission. An unconfirmed owned master may persist until ControlPersist expires.'))


_SSH_SESSION_CLEANUP_NOTICE = 'SSH session cleanup issues are retained in session_cleanup_diagnostics; preserve the receipt and do not resubmit because cleanup failed.'


def _file_operation_failure(problem, operation, stage, context, effects, cause=None):
    """Pure file-operation diagnosis; the adapter supplies observed effects."""
    summary = ('Path availability could not be established; a failed check does not mean the path is missing.'
               if operation == 'path_observation' else
               'File transfer stopped; inspect the source, destination and recorded stage before repeating it.')
    if stage == 'validate_source':
        summary = 'The local transfer source is missing, inaccessible or not a regular file.'
    elif stage == 'prepare_local_directory':
        summary = 'The local transfer destination directory could not be prepared.'
    elif operation == 'path_observation' and problem == 'resource_missing':
        summary = 'A required path is missing on the selected machine.'
    elif stage == 'check_path_kind':
        summary = 'The selected path has an unexpected file type.'
    action = ('Verify the exact resolved path, permissions and input preparation on the selected machine. Check the producing roots/configuration without switching profiles implicitly. A metadata snapshot does not prove future readability or scientific success.'
              if operation == 'path_observation' else
              'Verify the identified path, permissions and selected SSH alias/executable. A failed started copy may have left partial files; no automatic retry or rollback is performed. Retain any submission receipt and known IDs. Path observations are metadata snapshots, not readiness guarantees.')
    return Diagnostic(problem, operation, stage, context=context, effects=effects, cause=cause,
        summary=summary, next_action=action)


def _software_status_failure(problem, stage, context, cause=None, *, summary=None):
    """Read-only software observations/findings; never imply runtime readiness."""
    summaries = {
        'invalid_argument': 'The software observation request is invalid.',
        'configuration_invalid': 'The selected software profile needs correction.',
        'resource_missing': 'The software resource was not found on the selected machine.',
        'resource_inaccessible': 'Software metadata cannot be accessed; availability is unverified.',
        'record_invalid': 'The local software declaration could not be parsed.',
        'command_unavailable': 'The executable for software inspection could not be started.',
        'command_timeout': 'Software inspection timed out; retained observations remain useful.',
        'command_failed': 'A software inspection command failed.',
        'transport_failed': 'SSH could not complete software inspection.',
        'operation_interrupted': 'A software inspection command was interrupted.',
        'protocol_invalid': 'Software inspection returned invalid evidence.',
        'observation_unavailable': 'The requested software observation is unavailable.',
        'compatibility_mismatch': 'Observed software does not satisfy the declared expectation.',
    }
    return Diagnostic(problem, 'software_status', stage, context=context, cause=cause,
        summary=summary or summaries[problem],
        next_action='Check the named declaration, project, selected SSH alias or venv_path/bin/python and retained evidence. Missing, inaccessible and unverified are different. Update software explicitly if needed; this inspection never pulls code, installs dependencies, activates modules or retries automatically.',
        effects={'git_pull': 'not_started', 'editable_install': 'not_started'})


class InvalidRequestError(DiagnosticError, ValueError):
    """Known authoring validation failure; original causes remain chained.

    Only explicit validation guards construct this error. Effects are supplied
    by the boundary that knows them, never inferred from an invalid request.
    """

    def __init__(self, message, *, field, stage="validate_definition", context=None,
                 cause=None, effects=None):
        super().__init__(invalid_argument(operation="authoring", stage=stage,
            field=field, explanation=message, context=context, cause=cause, effects=effects))


def invalid_argument(*, operation, stage, field, explanation, context=None, cause=None, effects=None):
    """A known local validation error; no assertion about other operation effects."""
    _required_text(field, "field")
    return Diagnostic("invalid_argument", operation, stage,
                      context=_context_with(context, field=field), summary=explanation,
                      cause=cause, effects={} if effects is None else effects,
                      next_action=f"Correct {field} and validate the exact request again.")


def missing_resource(*, operation, stage, resource, path, context=None, cause=None, effects=None):
    """Use only after observing absence, never after a failed existence query."""
    _required_text(resource, "resource")
    _required_text(path, "path")
    return Diagnostic("resource_missing", operation, stage,
                      context=_context_with(context, resource=resource, path=path),
                      cause=cause, effects={} if effects is None else effects, summary=f"{resource} was not found.")


def command_failure(*, operation, stage, command, cause, effects, context=None):
    """A command returned failure; caller supplies phase-specific effects explicitly.

    Launch failure, timeout and lost response use their own explicit catalogue code.
    This function never classifies a transport error as scheduler rejection.
    """
    if not isinstance(cause, DiagnosticCause) or cause.returncode is None or cause.returncode == 0:
        raise ValueError("Command failure requires a nonzero observed return code.")
    _required_text(command, "command")
    return Diagnostic("command_failed", operation, stage,
                      context=_context_with(context, command=command), cause=cause, effects=effects)


def _context_with(context, **facts):
    if context is not None and not isinstance(context, Mapping):
        raise TypeError("Diagnostic context must be a mapping.")
    context = {} if context is None else dict(context)
    if any(key in context and context[key] != value for key, value in facts.items()):
        raise ValueError("Conflicting diagnostic identity facts.")
    return {**context, **facts}


def _required_text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Diagnostic {name} must be a nonempty string.")


def _connection_failure(code, machine, alias, *, stage='probe_connection', cause=None):
    return Diagnostic(code, operation='connection_check', stage=stage,
        context={'machine': machine, 'ssh_alias': alias, 'command': 'ssh'}, cause=cause,
        summary='The selected connection could not be verified from this controller.',
        next_action='Check the selected profile and operator-owned SSH route/authentication from this host. An interactive gateway shell does not automatically provide a laptop connection. Authentication need is unknown unless separately verified.')
