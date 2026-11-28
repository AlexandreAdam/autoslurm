# Understanding failures

A useful failure report explains what failed, which job or machine it concerns,
what may already have happened, and the next safe action. A failed connection
does not prove a file is missing or a job was rejected. A successful inspection
can report a scientifically failed job.

## Remote readiness before submission

When a root-discovery or helper-capability check fails, AutoSlurm now identifies
the selected SSH alias, storage root and attempted environment Python where
known. `asl submit` prints the diagnostic and a corrective action once, exits 1,
and stops before script transfer or scheduler submission. `--debug` retains the
original exception chain. Embedding applications can catch
`autoslurm.errors.DiagnosticError` and inspect `error.diagnostic.to_dict()`.

The codes distinguish `command_unavailable` (local SSH could not start),
`command_timeout`, `operation_interrupted`, `transport_failed`, `command_failed`,
`protocol_invalid` and `compatibility_mismatch`. A remote command failure does
not prove that the venv, helper or path is missing. A generic SSH failure does
not establish a password, gateway or 2FA problem. Normal output omits arbitrary
SSH/startup text; native local causes remain available in debug mode.

Each check runs once with a 30-second timeout and accepts at most 64 KiB of
response text. Roots must be one absolute path without traversal/control
characters, matching explicit storage_root selection. Capability JSON must have
unique keys and exact integer protocols, including execution_tracking; booleans
are incompatible. Older helpers require an explicit operator update.

No fallback, credential handling, package installation or environment repair is
performed. Existing launch commands and trusted env_command setup remain as
configured; arbitrary setup effects are not rolled back or declared read-only.
The diagnostic's not_started effects concern script transfer, submission dispatch
and scheduler submission by this check, not unrelated jobs or prior operations.
Existing configured legacy path selection still needs no discovery. Optional
diagnostic context now includes storage_root, separate from executable/path.

This adopts root/helper checks and the submit terminal boundary. General CLI/ACP
parity remains separately planned work. Filesystem/transfer adoption is described below. SubmissionError still owns its receipt; its
acceptance/uncertainty must never be discarded into a generic readiness error.

## SSH session resources and cleanup

SSH sessions now use the shared diagnostic model for allocation, socket length,
opening, closing and directory removal. `operation=ssh_session` identifies this
boundary; the stage names the failed step. Effects describe `session_directory`,
`ssh_master_open`, `ssh_master_close` and `session_directory_cleanup` independently.
An unknown open/close stays unknown even after successful directory removal.
These resource facts do not infer scheduler acceptance or earlier transfers.

For direct session calls, expected failures raise DiagnosticError (invalid
socket length uses ConfigurationError). The native local cause remains chained;
raw SSH output is omitted. A cleanup-only failure is raised after the body. When
the body already failed, its same exception stays primary with bounded secondary
diagnostics/native cleanup evidence. Unexpected bugs and interrupts are preserved.

For tracked submission, `SubmissionError.receipt` is authoritative. Successful
acceptance retains `state=submitted`, `execution_finished=true` and all IDs even
if closing SSH fails. A partial or uncertain outcome keeps that classification.
Optional `session_cleanup_diagnostics` records up to four cleanup observations
without native exception objects; refresh retains this workstation-owned evidence.
Cleanup notices in the error message point to it. Keep this receipt and inspect
status/logs before deciding on another submission; cleanup is never a reason to
retry automatically. General receipt-aware CLI/ACP presentation remains staged.

Configured shared connections are never explicitly opened/closed. The optional
ssh -G check is bounded to 10 seconds/64-KiB accepted UTF-8 output, falls back
once on expected read/command failures and rejects ambiguous control settings.
Invalid profiles and programming bugs propagate before allocation. Owned open/
close have 30/10-second timeouts and retain their original destination/options.
Only the owned local directory is removed; failure remains explicit. This adds
no password/key/2FA handling, automatic repair or scheduler retry.

## Shared diagnostic contract

MVP10.2 supplies the shared diagnostic foundation. MVP10.3a adopts it for local
configuration reads, profile/setting validation, selection and the config CLI.
MVP10.4a adopts software updates, including stale venv paths. MVP10.4b.1 adopts
remote storage-root discovery and submission-helper capability checks. Other commands
and services are adopting it in later slices. SubmissionError still carries its receipt and
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
behavior until their MVP10.4b–d slices. Software-update preflight now has its own
adopted boundary described below.

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

Software updates now raise `SoftwareUpdateError` with both `.evidence` and
`.diagnostic`; JSON evidence includes the same diagnostic. A missing venv names
the attempted Python executable and the `venv_path` correction in `asl config`.
Its preflight effects confirm pull/install were not started. Other failures
retain their actual check, native local cause or validated remote facts, and
separate Git/install effects. A failed install can follow a successful pull;
lost responses remain unknown and are never retried automatically.
`asl software update --debug` preserves original causes; ordinary text uses
stderr/exit 1, and `--json` keeps evidence with an additive diagnostic. Unexpected
update bugs propagate. See [software updates](software.md) for interpretation.
This does not claim general SSH/helper/transfer/software-status adoption.

Agent developers should read the [packaged diagnostic recipe](../src/autoslurm/agent_resources/15_diagnostics.md)
for supported fields, bounds, classification and integration examples. The
[implementation coverage register](../REFACTORING_DOCS/design/MVP10_api_failure_audit.md)
tracks the remaining adoption work. Scientific computation and output validity
remain application responsibilities.

## Paths, transfers and sync (MVP10.4c)

`path_exists(relative, context=...)` or `path_exists(relative,
bundle_path=exact_submission, job_name=...)` still returns a bool after a valid
metadata observation. False now means ENOENT/ENOTDIR, including a broken symlink;
True follows symlinks and permits any existing path kind. Failed permission/I/O,
SSH, launch, timeout or malformed-response checks raise DiagnosticError instead
of reporting missing. Retain logical_path/resolved_path/machine and the producing
context; never switch to today's profile to reinterpret a saved run.

Local checks use the same stat worker as remote checks. Remote metadata uses
operator SSH config and python3, without importing/installing AutoSlurm or reading
file contents. An unavailable python3 is a failed probe, with no shell fallback.
The metadata protocol is internal version1, with exact selected path/shape and
64-KiB accepted output; commands use a 30-second timeout. No path observation
proves future readability or scientific success.

Expected direct transfer errors use DiagnosticError, missing profile selection
ConfigurationError, and invalid filenames/requests InvalidRequestError. Catch
SubmissionError first for submit_jobs: its receipt remains authoritative and a
staging error stops before helper dispatch/sbatch. Native local causes remain in
__cause__; remote safe errno/exit facts remain in diagnostic.cause. Unexpected
bugs/native interrupts propagate; negative process exits carry interruption facts.
No new public exception or saved receipt/helper version is required.

operation=path_observation has probe_path/read_metadata/stat_path/check_path_kind
stages and path_observation/probe_command effects. operation=file_transfer has
validate_source/prepare_remote_directories/prepare_local_directory/copy_files
stages. Its source_validation or source_observation, destination_preparation and
file_transfer effects are independent. Paths and machine/alias/source/command are
bounded normal context; no raw SSH/SCP/rsync failure output or keys are copied.
A missing/denied local executable proves not_started; a failed started copy is
unknown and may have changed files. A zero exit followed by invalid/oversized
output retains succeeded for the command's copy effect. A failed batch never
claims particular files copied successfully. Inspect exact destinations before
any explicit retry; never retry compute submission to repair a transfer.

Managed filenames and regular local sources are validated before remote mutation;
source metadata does not prove later read access or stop concurrent changes.
Script batches still use one SCP call; empty batches perform no lookup or command.
Remote mkdir/probes use 30-second timeouts, SCP/rsync 300 seconds; accepted command
stdout is at most 64 KiB. Timed-out remote work may still have effects. Capture is
not a streaming memory limit. No credentials, alternate host, rollback or retry.

[Sync](sync.md) stages native tracking and validates exact linked receipts before
publishing controller views by submission identity. Missing/corrupt/conflicting
records retain local evidence; healthy neighbours can import. Verified raw copies
are backed up before repair. Failed imports report partial tracking effects and
raise; interrupted receipt/snapshot publication can be reconciled by explicit sync
after diagnosis. No submission is retried. Scripts/out still transfer in bulk,
with ignore-existing scripts and checksum-refreshed logs.

Success returns None/progress text. Diagnostics retain sync_jobs/sync_slurm/sync_out
effects for completed versus not-started/unknown copies and tracking_import=partial
when item failures remain. Only observed missing directories are skipped. An
inaccessible or wrong-kind source raises, and failed source checks create no local
target. Earlier/partial files remain; no final success is printed on failure.
The CLI renders adopted errors once with exit1; --debug rethrows with causes.
Prefer fetch_run/asl fetch for bounded selected-run evidence. Broader observation/
ACP diagnostic adoption remains in later MVP10 tasks.

Required-input/data-root/working-directory preflight uses this same metadata owner,
with one deduplicated remote batch and no command when there are no checks.
Observed missing required paths raise DiagnosticError/resource_missing; denied,
wrong-kind, failed-transport and malformed batches stay distinct. This replaces
FileNotFoundError from validate_jobs/validate_resolved_jobs. Local native causes,
known logical/resolved paths and labels are retained; public preview/submit add
the exact bundle reference. Batch length/order/path identity are validated within
the same 64-KiB response bound. Failed preflight stops before staging, receipt
creation, helper dispatch or sbatch; no blind retry or missing-input inference.

## Read-only software diagnostics (MVP10.4d)

Use software_expectations(local_project=..., requirements=..., package=...,
expected_version=..., expected_commit=..., dependencies=...) to read declared
important dependencies, then inspect_software(machine=..., project=...,
expectations=...) to inspect one selected machine. Caller-supplied expectation
mappings are validated too, before remote commands. Invalid inputs use
InvalidRequestError; invalid selected profiles use ConfigurationError. Declaration
read/UTF-8/TOML failures use DiagnosticError with the exact file and native cause.
Unsupported pip options, includes/cycles and source URLs remain conservative
warning/unknown checks; directives are never executed and source URLs are not
copied into findings. Existing include limits remain; custom dependency names and
expectation lists are bounded and must use the supported dictionary fields.

Catch DiagnosticError for a failed whole operation and retain .diagnostic and
__cause__. A lost SSH response, local executable failure, timeout, signal, nonzero,
invalid encoding, duplicate JSON keys, oversized response or wrong root is not an
empty or clean software directory. operation=software_status identifies these
errors, with machine/project/path/alias and attempted Python where relevant.
Unexpected bugs/native interrupts propagate. Normal diagnostics omit arbitrary
SSH/Git/interpreter output; --debug is for raised original chains.

A successful API call can return partial or incompatible evidence. Inspect the
root, each projects item, environment and environment.packages[name], not merely
whether the call returned. Their optional diagnostic is a plain version1 object,
not an exception. Safe causes include stage, errno and return code; returned
partial results do not contain native exception objects. errors.py owns wording;
standalone workers emit facts, validated/normalized by the host. Malformed items
become unavailable with protocol_invalid beside healthy neighbours; invalid whole
identity raises. Known commit/version survives a later failed status/source check.
Unknown dirty/source identity cannot become clean or compatible. No record/helper
version or historical migration is introduced by these additive diagnostics.

The selected environment is probed with venv_path/bin/python and its prefix is
verified on that machine, so symlinked environments do not rely on workstation
path resolution. Missing, wrong or unavailable interpreters leave environment
unknown while useful Git evidence survives. There is no system-Python fallback
for environment metadata. Remote discovery still uses one system-python3 payload
without importing/installing AutoSlurm. It activates no modules/setup commands and
imports no scientific packages. Git is read-only with optional locks/prompts off.
Bounds remain: 1..100 projects, 5-second Git queries, 25-second environment query,
35-second soft scan budget including environment time, 60-second outer SSH and
1-MiB accepted status response. Git stdout acceptance is 64 KiB; capture is not a
streaming memory limit. Truncated discovery is not proof about omitted projects.

compatibility.state remains compatible, potential_problem or unknown. Per-check
diagnostics explain mismatch/unknown findings without raising or discarding other
checks. Comparison uses declared constraints and target-machine markers, never
the laptop's installed freeze or platform. Missing/malformed marker facts stay
unknown. Default important metadata targets are numpy/jax/jaxlib/torch/scipy;
--dependency opts in others. A missing distribution becomes a mismatch only when
an applicable requirement or application expectation needs it; do not install all
metadata targets merely because they were queried. A compatibility result is not
proof of upstream/latest code, scientific runtime/GPU support or transitive health.

asl software status --machine NAME --project PATH reports useful evidence and
inline diagnostics. --json preserves the observation with nested diagnostics;
partial/unavailable/unknown/incompatible findings still exit1. Whole-operation
errors now use stderr/exit1 or the shared --json envelope
{status: error, message, diagnostic}; this replaces the old generic unavailable
error envelope. --debug rethrows operation errors with native chains; it does not
turn returned partial observations into exceptions. Empty status still prints help
without contact. Updates remain separate: no pull/install, new checkout/env,
source reset, dependency repair, scheduler action, credential handling or retry.
