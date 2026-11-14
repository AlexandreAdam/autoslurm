# Understanding failures

A useful failure report explains what failed, which job or machine it concerns,
what may already have happened, and the next safe action. A failed connection
does not prove a file is missing or a job was rejected. A successful inspection
can report a scientifically failed job.

MVP10.2 supplies the shared diagnostic foundation. Existing commands and services
are adopting it in later MVP10 slices; this release does **not** fix the stale-venv
message or change all CLI errors. SubmissionError still carries its receipt and
SoftwareUpdateError its update evidence. Keep those objects, particularly accepted
job IDs and unknown outcomes, even when displaying an error.

The new Python interface lives in `autoslurm.errors`. A `Diagnostic` describes
operation/stage, stable code/category, summary, selected context, cause, effects,
next action and secondary failures. `to_dict()` returns detached JSON-safe data.
Effects are supplied by the operation: a timeout can occur before work starts
or after its result becomes unknown. The diagnostic module performs no discovery,
environment repair, retries or external commands.

Clients can use `DiagnosticError(diagnostic)` for explicitly diagnosed failures.
Existing SubmissionError(message, receipt) and SoftwareUpdateError(message,
evidence) accept an optional `diagnostic=` while retaining their original payloads
and normal Python exception chaining. A missing diagnostic means that operation
has not adopted the new interface; keep its existing handling.

The opt-in `autoslurm.apps.error_output` adapter renders these same facts as text
or JSON. It exits 1 for a diagnosed operation failure, writes text to stderr or
JSON to stdout, and re-raises unexpected/undiagnosed errors. `debug=True` re-raises
the original error for debugging. Parser usage errors remain exit 2; observation
and warning exit policies remain with their commands. This adapter is not
automatically installed around existing commands.

Agent developers should read the [packaged diagnostic recipe](../src/autoslurm/agent_resources/15_diagnostics.md)
for supported fields, bounds, classification and integration examples. The
[implementation coverage register](../REFACTORING_DOCS/design/MVP10_api_failure_audit.md)
tracks the remaining adoption work. Scientific computation and output validity
remain application responsibilities.
