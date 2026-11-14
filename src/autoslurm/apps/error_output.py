"""Thin opt-in terminal boundary for diagnostics; no domain operations/recovery."""

import json
import sys

from ..errors import Diagnostic, DiagnosticError

__all__ = ["render_diagnostic", "exit_with_error"]


def render_diagnostic(diagnostic):
    """Render the same bounded facts exposed by Diagnostic.to_dict()."""
    if not isinstance(diagnostic, Diagnostic):
        raise TypeError("Expected a Diagnostic.")
    lines = [f"{diagnostic.summary} [{diagnostic.code}]",
             f"Operation: {diagnostic.operation}; stage: {diagnostic.stage}"]
    for key, value in diagnostic.context.items():
        if value is not None:
            lines.append(f"{key.replace('_', ' ').capitalize()}: {value}")
    if diagnostic.cause:
        cause = diagnostic.cause
        facts = [f"{key}={value}" for key, value in (("errno", cause.errno), ("returncode", cause.returncode)) if value is not None]
        lines.append(f"Cause: {cause.kind}" + (f" ({', '.join(facts)})" if facts else ""))
        if cause.detail:
            lines.append("Detail: " + cause.detail.replace("\n", "\n  "))
    if diagnostic.effects:
        lines.append("Effects: " + "; ".join(f"{step}={state}" for step, state in diagnostic.effects.items()))
    lines.append(f"Next: {diagnostic.next_action}")
    for secondary in diagnostic.secondary:
        lines.append("Secondary:\n" + "\n".join("  " + line for line in render_diagnostic(secondary).splitlines()))
    return "\n".join(lines)


def exit_with_error(error, *, json_output=False, debug=False, stream=None):
    """Render an explicitly diagnosed failure once, then exit 1.

    Unknown/legacy exceptions and debug requests re-raise the original exception
    with its cause/traceback. Usage exit 2 remains the parser's responsibility.
    Returned observations/warnings are not passed to this operation-failure helper.
    JSON uses stdout, text stderr, unless the caller supplies a stream.
    """
    if debug or not isinstance(error, DiagnosticError) or not isinstance(error.diagnostic, Diagnostic):
        raise error
    diagnostic = error.diagnostic
    output = json.dumps({"status": "error", "message": diagnostic.summary,
                         "diagnostic": diagnostic.to_dict()}, ensure_ascii=False) if json_output else render_diagnostic(diagnostic)
    try:
        print(output, file=stream if stream is not None else sys.stdout if json_output else sys.stderr)
    except (OSError, UnicodeError, ValueError):
        # Re-raise the initiating error with its payload/cause intact. Python keeps
        # the output failure in __context__; it cannot replace the domain error.
        raise error
    raise SystemExit(1) from None
