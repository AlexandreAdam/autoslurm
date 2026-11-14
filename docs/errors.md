# Understanding failures

A useful failure report explains what failed, which job or machine it concerns,
what may already have happened, and the next safe action. A failed connection
does not prove a file is missing or a job was rejected. A successful inspection
can report a scientifically failed job.

MVP10.2 supplies the shared diagnostic foundation. MVP10.3a adopts it for local
configuration reads, profile/setting validation, selection and the config CLI.
Other commands and services are adopting it in later slices; this release does
**not** fix the stale-venv message or change all CLI errors. SubmissionError still carries its receipt and
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

`ConfigurationError`, available from `autoslurm` and `autoslurm.errors`, carries
the actual source path, named field/profile, safe original cause and next action
for known configuration failures. It is a DiagnosticError/RuntimeError and also
a ValueError for existing validation catches. **Development API boundary:** missing/
unreadable config and missing activation settings now use ConfigurationError,
replacing the old OSError/EnvironmentError/AttributeError mix. Catch it explicitly;
the originating file error remains in `__cause__` with errno in the diagnostic.
This does not change saved JSON or migrate records. Publication failures and invalid
storage-root selectors/package-import errors still await their later slices.

Known authoring failures now raise `InvalidRequestError`, also exported from
`autoslurm` and `autoslurm.errors`. For example, a job whose `count` option has
the wrong type reports field `script_args`, option `count`, job `fit` and the
validation stage. Dependency errors identify the affected job; cycles retain
the original cause and their job names. Correct the named setting and validate
the exact definition again. Saved arguments remain individually readable; missing
saved settings are never filled silently from newer command defaults.

This applies to typed commands/adapter, literal arguments, dependency graphs,
historical software-intent metadata and bundle input/preparation guards. It retains
ValueError compatibility, replacing old TypeError/KeyError authoring guards and
CycleError for invalid DAGs at this dev boundary. Missing/blank/nonstring commands
fail before new save/schedule publication. No saved format or history is rewritten.
Paths/rendering, publication, process and universal CLI/ACP adoption remain separate
tasks. `asl schedule` renders adopted errors to stderr
and exits 1; add `--autoslurm-debug` for original exceptions. Ordinary application
`--debug` still forwards. Unknown code bugs propagate.

`SelectionError` now explains invalid selectors, missing snapshots and unreadable
discovery sources. Catch it instead of FileNotFoundError for missing name/index/
path selections; it remains ValueError/DiagnosticError compatible. The diagnostic
distinguishes absence, access failure and invalid records, with the exact path and
original cause. An inaccessible jobs directory is not an empty directory.

Bundle discovery keeps healthy entries beside failures. Failed entries carry
`diagnostic`; unknown jobs/counts are `None`, while a valid empty draft has an
empty list and zero counts. A newer broken snapshot remains visible and blocks
fallback to an older draft. Unknown counts are excluded from automatic stale/
unsubmitted cleanup. These are discovery states, separate from scheduler states.
Existing files and saved JSON formats are unchanged.

An absent config uses the default active filter. Invalid or unreadable config,
including an invalid stored filter mode, now raises ConfigurationError instead of
silently changing visible indices. Filter/submit/status/inspect/logs render adopted
selection/configuration failures once and support `--debug`; existing JSON modes
return the same facts. `asl submit` checks the exact record before connecting.
Other inspection and post-dispatch error policies remain staged adoption.

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
