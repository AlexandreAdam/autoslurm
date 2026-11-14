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
           "ConfigurationError", "configuration_failure", "InvalidRequestError"]

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
    "source", "freshness", "observed_at", "observation_state"})
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
