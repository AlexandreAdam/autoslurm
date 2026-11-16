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
This does not change saved JSON or migrate records. Invalid
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
Process and universal CLI/ACP adoption remain separate tasks.
`asl schedule` renders adopted errors to stderr
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

Path and render preparation now use `InvalidRequestError` too. A rejected input,
output, working directory or custom log path identifies the field, job, machine,
logical path and attempted resolved path where available. A candidate containing
`..` is rejected evidence, not an approved destination. Correct the relative path
under the selected root and preview the exact bundle again. Environment and Slurm
directive validation names the setting without echoing its values. Preview and
submission share these checks; `asl submit --debug` preserves preparation errors.

Shell syntax rejection reports the affected job and line when available, without
copying application or environment literals from Bash's output. Failed or killed
syntax-check processes remain process errors. Direct script creation renders in
memory before publication, so render failures preserve an existing script.
Script publication now shares the atomic record writer described below. Saved execution
lookup reports missing evidence versus malformed roots/transport through
`SelectionError`, retaining the exact file/job and historical producing roots.
It never substitutes today's profile. Pure validation makes no blanket claim about
submission effects. External readiness/SSH/existence errors retain their existing
behavior until MVP10.4; this slice does not fix the stale-venv message.

The opt-in `autoslurm.apps.error_output` adapter renders these same facts as text
or JSON. It exits 1 for a diagnosed operation failure, writes text to stderr or
JSON to stdout, and re-raises unexpected/undiagnosed errors. `debug=True` re-raises
the original error for debugging. Parser usage errors remain exit 2; observation
and warning exit policies remain with their commands. This adapter is not
automatically installed around existing commands.

Shared JSON writes now raise `RecordWriteError`, exported from `autoslurm` and
`autoslurm.errors`. It retains OSError/DiagnosticError compatibility and the
original cause. **Development API boundary:** unsupported or circular JSON data
also uses this family, replacing raw TypeError/ValueError from serialization.
The diagnostic names the exact destination and failed stage without copying
record contents. Bundle/config/receipt/cache writers inherit this shared boundary;
their adopted domain context is described below; broader CLI policies remain staged.

Two effect fields explain a failed write. `record_publication=not_started` means
publication to the destination was not attempted; parent directories or temporary
files may already exist. `unknown` means link/replace failed without proving its
outcome. `succeeded` means the complete record was published. Separately,
`record_durability=succeeded` means the directory sync returned successfully;
`unknown` means durability was not confirmed. This does not establish a transaction
across records or say anything about scheduler acceptance.

Cleanup failures cannot erase the initiating error. Expected cleanup failures
appear as secondary diagnostics; native causes remain available for debugging.
A failure after publication leaves the record in place. Inspect that exact file
before repeating a save or append. Only a clean exclusive-name collision allows
snapshot creation to choose another timestamp; uncertain publication or failed
cleanup stops the operation. No record is rolled back or automatically removed.
JSON and script publication share this same owner and these same effect fields.

Bundle/config record boundaries now adopt these diagnostics too. Direct bundle
loading uses discovery's regular-file UTF-8 JSON reader: `SelectionError` codes
distinguish missing files, inaccessible paths and malformed data. This replaces
the direct loader's earlier FileNotFoundError/OSError mix; the original filesystem,
JSON or Unicode cause remains available through `__cause__`. Invalid saved job/
dependency graphs keep their existing `InvalidRequestError` with exact bundle path.
No unreadable bundle becomes an empty definition. Append and metadata updates
validate existing records before changing them, retaining known scheduler IDs.

`RecordWriteError` now identifies the bundle/job or configuration being written
and the calling operation in `context.source`. It keeps the shared publication,
durability and cleanup facts unchanged. A complete write followed by sync failure
is still a published record; inspect its exact path before repeating an append.
Bundle names are file names, without path separators or control characters.

Config (including `configuration`), filter, initialize, schedule and submit render
adopted record errors once to stderr and exit 1. Use `--debug` for original causes;
schedule uses `--autoslurm-debug`, preserving the application's `--debug` option.
ACP includes shared write diagnostics in its error envelope. Universal
command/ACP error policies remain later work; retain
authoritative receipts and accepted IDs rather than inferring scheduler outcomes
from a local file error.

Receipt reads now use `SelectionError` too: `resource_missing` for observed
absence, `resource_inaccessible` for denied/special/dangling paths, and
`record_invalid` for JSON, encoding or receipt-contract failures. This replaces
raw file/JSON/protocol exceptions at this development boundary. The diagnostic
retains the exact `receipt_path`, known submission identity and original cause.
Bundle, receipt and cache file reads share operation `record_read`; selector
validation remains `selection`. A missing receipt directory lists no items;
an unreadable directory or broken receipt fails explicitly, without silently
returning an incomplete list. Reading/listing creates no directories or jobs.

Receipt and tracking-snapshot writes add `submission_id`, `receipt_path`, bundle
and machine identity where known. A projection identity/ID conflict leaves the
tracking file intact. `SubmissionError.receipt` still owns accepted IDs and
uncertainty; adopted local persistence errors also survive in `.diagnostic`.
A secondary tracking write failure can add `tracking_diagnostic` beside its
existing `tracking_error`. These facts never imply scheduler rejection or permit
an automatic retry. Broader orchestration/interruption adoption remains MVP10.5.

`asl submission PATH` shows adopted read errors on stderr and exits 1; `--json`
returns a diagnostic envelope and `--debug` preserves the native cause. A failed
refresh retains the existing receipt/ID fields, with additive `diagnostic` when
available. ACP follows the same diagnostic-plus-receipt rule for these failures.

Cache errors retain their existing `source`, `message`, `path` fields and add
`diagnostic`. Missing caches remain quiet; inaccessible or malformed evidence is
reported. A cache write failure keeps live job states, IDs, task observations and
fetched log text, with partial freshness as before. A failed receipt overlay is
per-item evidence and does not discard IDs already in the selected snapshot.
Broader scheduler/log observation policy remains MVP10.6.

Direct and staged scripts are published atomically after rendering. Failures
before replacement retain old bytes; failures after observed replacement retain
the complete new script. `RecordWriteError` identifies `slurm_script`, job and
submission context where known. Multi-script staging is not a transaction: earlier
complete scripts may exist when a later write fails, and dispatch does not start.

Agent developers should read the [packaged diagnostic recipe](../src/autoslurm/agent_resources/15_diagnostics.md)
for supported fields, bounds, classification and integration examples. The
[implementation coverage register](../REFACTORING_DOCS/design/MVP10_api_failure_audit.md)
tracks the remaining adoption work. Scientific computation and output validity
remain application responsibilities.
