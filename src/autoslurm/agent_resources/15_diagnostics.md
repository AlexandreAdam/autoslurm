# Diagnostic foundation and client handling

MVP10.2 implements the foundation. MVP10.3a adopts local configuration read/profile/
setting/selection failures and the config CLI. Other AutoSlurm services/CLI/ACP
have not adopted it universally; `.diagnostic is None` is normal on legacy errors.
MVP10.3b.1 also adopts the authoring boundaries described below.
MVP10.3b.2 adds snapshot/filter selection and per-entry discovery diagnostics.
MVP10.3b.3 adds pure path/render preparation and saved producing-context validation.
MVP10.3c.1 adds phase-aware shared JSON publication diagnostics.
MVP10.3c.2 adopts direct bundle reads and bundle/config mutation boundaries.
MVP10.3c.3 adopts receipt/cache persistence and atomic script publication.
MVP10.4a adds software-update diagnostics, including stale-venv preflight failures.
MVP10.4b adopts root/helper/session diagnostics; MVP10.4c adopts paths/transfers.
Read-only software-status adoption remains MVP10.4d.
Do not promise universal diagnostics based only on the existence of this module.
Retrieve this installed recipe with `asl agent --sections 15_diagnostics`.

## Public contract

```python
from autoslurm.errors import (
    Diagnostic, DiagnosticCause, DiagnosticError, diagnostic_catalog,
    invalid_argument, missing_resource, command_failure,
    ConfigurationError, configuration_failure, InvalidRequestError,
    SelectionError, selection_failure,
    RecordWriteError, RecordCollisionError, record_write_failure,
)
from autoslurm.apps.error_output import render_diagnostic, exit_with_error
```

`Diagnostic(code, operation, stage, ...)` is immutable and accepts known catalogue
codes. `diagnostic_catalog()` returns a detached map of category/default summary/
next action. Operation/stage and effect-step names are 1–64 character identifiers
(letters first; then letters, digits, underscore, dot or hyphen). The category
property comes from the catalogue. Overrides `summary=` and `next_action=` are
supported, with nonempty wording. `invalid_argument` names the bad field;
it also accepts explicit optional `cause=` and `effects=` facts.
`missing_resource` requires an **observed absence**, resource label and path;
`command_failure` requires a nonzero observed return code and explicit effects.
Launch errors, timeouts, malformed responses and unknown acceptance use their
explicit catalogue codes; no generic exception-to-outcome classifier exists.

`context` contains only these selected scalar facts: machine, ssh_alias, project,
bundle, bundle_path, receipt_path, submission_id, job, job_id, task, field, option,
logical_path, resolved_path, path, executable, resource, command, source,
freshness, observed_at, observation_state and storage_root. Values are str/int/bool/None;
integers are signed 64-bit. `with_context(**facts)` returns a copy and refuses
conflicting identity. Never pass an entire config, environment, argv or domain
record. Observation fields retain supplied evidence, not a new state projection.

`DiagnosticCause(kind, detail='', errno=None, returncode=None)` records safe
facts. `from_exception(error, detail=..., returncode=...)` captures type/errno/code
and bounded text without classifying effects. Keep the original exception with
`raise DiagnosticError(diagnostic) from original`. Cause facts are not a traceback
or substitute for that chain. Prefer relevant adapter output to a command's raw
argument vector; arbitrary secret text is not safe merely because it is bounded.

`effects` maps at most 32 named steps to not_started, succeeded, failed, partial
or unknown. No code or exception type chooses these automatically. Per-job IDs,
rejected/blocked states and authoritative history stay in the existing receipt or
operation result; reference its exact path/identity in context. Do not truncate
or replace those records with diagnostic summaries. A failed pip install after
pull cannot be labelled no change. An unknown submit must never trigger retry.

`with_secondary(*diagnostics)` adds up to four leaf diagnostics without changing
the primary cause/effects/context. It rejects nesting or overflow rather than
silently dropping prior failures. Keep evidence-saving catches at effect
boundaries, including interrupts; do not mechanically narrow them to expected
user errors or replace every catch with the same wrapper.

`to_dict()` returns version=1 plus code/category/summary/operation/stage/context/
cause/effects/next_action/secondary as detached JSON-safe facts. This is a new
opt-in diagnostic payload, **not** a new bundle/receipt schema or migration.
Summary/context strings are bounded to 512 UTF-8 bytes, next action to 1024 and
cause detail to 4096. Identity names are bounded too; controls are replaced,
detail permits newline/tab, and known URL-userinfo/credential/key forms are
redacted before bounding. Each diagnostic and its four possible secondary leaves
have these bounds. Do not submit whole records or secrets expecting universal
redaction; original exception objects remain available to trusted debugging.

## Configuration adoption in MVP10.3a

Catch `ConfigurationError` from `autoslurm` or `autoslurm.errors`. Known failures
carry the same Diagnostic. File absence uses resource_missing, denied/unreadable
access uses resource_inaccessible, invalid UTF-8/JSON uses record_invalid, and bad
shape/profile/settings/selection use configuration_invalid. Actual source paths,
including a legacy file when used, and named fields/profiles remain visible.
Overrides are marked source=profile_overrides. JSON causes expose line/column
without embedding raw contents; original Python causes remain available.

`configuration_failure(stage=..., problem=..., context=..., cause=..., effects=...)`
constructs these facts in the shared core; it performs no lookup. Problem is
invalid/missing/unreadable/corrupt. Caller-supplied effects are not inferred; config
read/validation adapters record config_write=not_started. Publication errors have
not been migrated yet; never infer that all writes or other prior actions are
unchanged from this diagnostic.

The class inherits DiagnosticError/RuntimeError and ValueError. This development
release replaces OSError/EnvironmentError for config reads and AttributeError for
missing activation with ConfigurationError; update client catches deliberately.
Validation ValueError catches still work. No JSON schema or data migration is
introduced. The config CLI handles its root/alias/standalone routes with the
shared adapter and optional --debug; usage errors stay exit 2. Unknown code bugs
are re-raised. Raw --view retains its JSON shape. Existing corrupt/unreadable files
and dangling symlinks are preserved; only actual absence enters first-use creation.
Explicit AUTOSLURM_STORAGE_ROOT never enables legacy-file fallback. Without that
selector, only a missing primary file permits the old src/config.json lookup.
No automatic profile/environment switch or submission retry is added.

Bundle authoring/selection/path and bundle/config record diagnostics are adopted
in the sections below. Configuration validation's external commands and universal
CLI/ACP parity remain later work; software-update preflight is adopted in 10.4a.
Invalid storage selectors can still fail during eager package
import before this interface is available. Do not hide those limitations.

## Authoring adoption in MVP10.3b.1

Catch `InvalidRequestError` from `autoslurm` or `autoslurm.errors` for known
command-contract/option/adapter, literal argument, dependency graph, historical
software-intent and bundle input/preparation failures. It inherits DiagnosticError/
RuntimeError and ValueError. Diagnostic code is invalid_argument, operation is
authoring, and stage identifies validate_command, derive_command,
compile_arguments, validate_graph, validate_software, save_bundle, schedule_job
or prepare_bundle. Inspect context.field and, when known, option/job/project/
command/bundle_path/machine. Raw option values, entire jobs and manifests are not
copied into diagnostics. Original shell-tokenizer, repository-parser, import and
cycle exceptions remain in __cause__ and safe cause facts.

Validate through the trusted command before saving. `validate_job` still rejects
missing explicit saved options instead of injecting new defaults. Every setting
remains named/readable in script_args. This error contract does not discover a
command signature for raw jobs, alter boolean/list styles, repair definitions or
resubmit. Graph validation rejects malformed/unknown dependencies and cycles.
Empty drafts remain saveable, but cannot be submitted.

**Dev exception boundary:** these known authoring failures now use
InvalidRequestError, including old TypeError/KeyError save guards and CycleError
from invalid DAGs. Existing ValueError catches work. Cycles are checked by
dependency_graph itself, not only by later sorting. Missing/blank/nonstring
commands are rejected before new save/schedule publication. JSON, filesystem,
external-command and unexpected code failures are not broadly converted. Existing
records are retained; saved JSON formats do not change.

Read/validate/compile services are pure or read-only; they make no blanket effect
claim. Early save/schedule shape/command guards record bundle_write=not_started.
No diagnostic grants permission to retry an earlier submission or implies earlier
actions had no effect. Public preview/submit attaches exact bundle/machine identity
to adopted authoring errors and stops before staging/dispatch. Snapshot selection,
path/render and bundle/config record failures are adopted below; transport and
universal ACP parity remain later slices. The submit CLI also adopts the earlier
broken-snapshot gate and shared preparation/record rendering.

The schedule CLI/root/installed entry point renders adopted errors once to stderr
and exits 1. `--autoslurm-debug` re-raises the original error/cause chain; ordinary
application `--debug` retains its previous forwarding behavior. Parser misuse stays
exit 2 and unexpected programming errors propagate. Its legacy help-text discovery
is unchanged and does not gain typed signature validation or new process diagnostics.

## Snapshot selection in MVP10.3b.2

`SelectionError` is exported at root and in errors. It inherits DiagnosticError/
RuntimeError and ValueError. Known selector/discovery/read failures have operation
selection and codes invalid_argument, resource_missing, resource_inaccessible or
record_invalid. The stdlib-only `selection_failure(stage=..., problem=..., context=...,
cause=..., summary=...)` constructs these facts without lookup or effect inference;
problem is invalid/missing/unreadable/corrupt. Native filesystem/JSON/Unicode
causes remain chained on raised failures; returned diagnostics contain safe facts.
Never infer submission effects from selection errors.

**Dev exception boundary:** missing selections now raise SelectionError rather
than FileNotFoundError, including `nearest_bundle_filename` and name-based loading.
Catch this class and inspect diagnostic.code. Direct bundle file loading also
uses this read family from MVP10.3c.2. Type/selector conflicts,
positive integer indices (excluding bool), and naive datetime reference dates are
validated before discovery. Exact path and prefer_draft=False name/nearest lookup
remain metadata/filename-only; they do not prove payload validity. Unversioned
external files use mtime when explicitly selected (supply their bundle name when
it cannot be inferred); no file is rewritten. Equal timestamp indices have a stable
filename tie-break. Normal index order remains descending timestamp.

Discovery uses one snapshot analysis shared by `list_saved_bundles`, snapshot
state/list helpers, ACP list_bundles/list_experiments and list_runs. These services
do not create storage directories. Missing storage is an empty list; inaccessible
storage is an operation failure, not an empty list. Each readable empty draft has
jobs=[], job_count=0, submitted_count=0 and diagnostic=None. Unreadable/unparseable
contents have jobs=None and unknown counts=None; never coerce those to empty/zero.
Graph-invalid dictionaries can retain observed job names/counts and ID count.
Returned states include ready_to_go/active/broken/unavailable/missing, where the
last means a discovered file disappeared. Returned diagnostic is a plain to_dict()
value or None, not an exception. Missing/unavailable is not scientific job failure.

`bundle_snapshot_state(path, strict=True)` raises the same diagnosis instead of
returning a failed entry, preserving native chains. The submit CLI uses that guard
before selecting a machine or connecting. A newer broken/unavailable/missing
snapshot cannot be bypassed for an older ready draft, and active visibility keeps
the latest failed entry beside submitted history. Unknown-count records are excluded
from automatic stale/unsubmitted cleanup; explicit operator targets retain their
existing behavior. Corruption never authorizes rebuilding or retrying by itself.

Only absent configuration defaults the filter to active. Bad JSON, denied access,
invalid profiles or invalid stored filter modes raise ConfigurationError; they do
not silently change which indices are visible. Set mode explicitly to active/all
after correcting the exact file. Existing healthy filtering/draft/date policy is
otherwise retained.

Filter/submit/status/inspect/logs root/standalone/alias routes render adopted
selection/configuration operation failures with shared text on stderr/exit 1 and
--debug for original chains. Existing --json on status/inspect/logs uses the shared
diagnostic envelope. Parser usage remains exit 2. ACP adds diagnostic to expected
selection/configuration error envelopes and keeps per-entry diagnostics in successful
discovery results. Other ACP catches, observation/log errors and post-dispatch
failures remain their existing policies until later adoption. Discovery state is
separate from the inspection pipeline's scheduler/observation state; this is not
universal observation or CLI/ACP parity. Unexpected bugs at the adopted selection
boundaries propagate; no broad catch converts them into empty/broken records.

## Path/render preparation in MVP10.3b.3

ExecutionContext.resolve_path/resolve_job and preview_bundle/submit_jobs use
InvalidRequestError for known path/role/cwd/log and render validation guards.
Stages include resolve_path, resolve_job, prepare_bundle, render_script and
validate_shell. Context retains field, option where applicable, job, machine and
logical_path/attempted resolved_path when known; preview/submit also retain the
exact bundle_path. A rejected traversal candidate is evidence, not an approved
destination. Correct the named setting and revalidate that exact definition.
No existence, permission or cluster readiness is proved by pure resolution.

Environment/runtime exports and Slurm directive shapes/control characters are
validated without serializing their values. Shared structural guards serve direct
rendering and preparation. Literal quoting and readable argument styles are
unchanged. Bash syntax rejection retains safe line information and observed status
2 without copying stderr's application/environment literals. A checker launch
failure or other return status remains an external process error for MVP10.4.
Unexpected programming exceptions propagate. Pure validation leaves effects empty.

Direct create_slurm_script renders completely before opening its destination;
render validation cannot truncate a previous script or leave a new partial file.
It does not add shell-syntax checking to that legacy direct API. MVP10.3c.3 adds
atomic publication and write diagnostics. Preview/submit still validate generated shell
syntax through their shared existing pipeline before staging/dispatch. Their
external root discovery/readiness checks are not migrated by this slice.

recorded_execution/execution_context_from_snapshot and saved-context result lookup
use SelectionError at read_execution: absent evidence/exact job is resource_missing,
ambiguous selection invalid_argument, malformed producing roots/transport
record_invalid. Known bundle/job/machine/field is retained; native alias-validation
causes remain chained. Legacy producing project/results roots and transport stay
readable and distinct. No current profile, fallback machine or replacement root is
discovered. Loader I/O/JSON failures adopt SelectionError in MVP10.3c.2; observation-side producing
metadata and readiness/existence probes remain their separately planned owners.

`asl submit` and its standalone entry point render adopted preparation diagnostics
once to stderr/exit 1; --debug re-raises the original exception. Schedule keeps its
--autoslurm-debug behavior. Universal ACP/CLI adoption remains MVP10.8. Retain
receipts and original history; never infer a safe resubmission from validation alone.

## Shared JSON publication in MVP10.3c.1

`from autoslurm import RecordWriteError` is the supported client catch. It inherits
DiagnosticError/RuntimeError and OSError. `autoslurm.errors` additionally exports
RecordCollisionError and the pure record_write_failure constructor. No filesystem
operation lives in the error module. **Dev exception-family change:** unsupported/
circular JSON serialization now raises RecordWriteError with invalid_argument,
field record_data and chained TypeError/ValueError; raw serializer exceptions no
longer form that public boundary. Filesystem failures use storage_failed with a
safe original kind/errno and native cause. Neither diagnostic copies record values
or arbitrary serializer/filesystem exception text.

Operation is record_publication. Stages: prepare_directory, create_temporary,
serialize, sync_temporary, close_temporary, publish_record, sync_directory,
close_directory and cleanup_temporary. Context.path is the exact destination.
The shared writer supplies explicit facts:

- record_publication: not_started before destination publication or on an observed
  exclusive collision; unknown after a failed link/replace; succeeded after that
  syscall returned. Parent/temp creation can happen before publication starts.
- record_durability: not_started before publication; unknown until directory fsync
  returns; succeeded afterwards. Successful cleanup does not prove durability.
- Failed cleanup retains the primary diagnosis/effects and adds bounded secondary
  diagnostics. If four secondary slots are already used, native cleanup evidence
  is still retained. Interrupts and unexpected bugs remain the same exceptions;
  safe standard notes are added where supported. record_cleanup_errors contains
  native debug evidence, including secondary causes, and must not be serialized.

RecordCollisionError is also FileExistsError-compatible. Snapshot creation advances
to another timestamp only after a clean collision without cleanup failures.
Other failures stop, including successful publication followed by directory-sync
or cleanup failure. Do not blindly save/append again; inspect the exact destination
and retain the existing evidence. No rollback, implicit deletion or write retry.

Bundle/config/receipt/cache writers using the shared atomic primitive inherit this
failure family. It describes one local record only, never submission acceptance,
dependency state or an atomic transaction across files. Existing cache OSError
handling remains nonfatal, with structured returned diagnostics adopted in c.3.
Domain enrichment/direct bundle reads and config/schedule CLI presentation are
adopted in c.2; c.3 adds receipt/cache/script persistence. SubmissionError.receipt and
SoftwareUpdateError.evidence stay authoritative; their higher-level adapters are
not replaced by catching only RecordWriteError. Do not call private record_files
helpers from scientific clients. Use supported save/config/submission operations.

## Bundle/config records in MVP10.3c.2

Direct load_bundle_from_path and name-based loading use discovery's shared
regular-file, nonblocking UTF-8 JSON reader. Known failure codes: resource_missing
for observed absence, resource_inaccessible for denied/unavailable/special files
(including dangling links), record_invalid for JSON/UTF-8/top-level shape errors.
SelectionError replaces the old direct-loader FileNotFoundError/OSError mix at
this dev boundary. Exact bundle_path and original cause are retained; JSON detail
contains location, not record contents. A replacement appearing after a failed
read is unavailable rather than absent. Unknown programming errors propagate.
Saved job/DAG validation retains InvalidRequestError and exact path/job/field;
there is no generic ValueError-to-corrupt-data catch.

save_bundle/schedule_job append and legacy metadata updates read and validate the
original before mutation/publication. Broken files are never replaced with empty
definitions; missing metadata records do not create directories. Metadata changes
must preserve valid job/dependency identity and cannot replace or clear a known
scheduler ID. Missing target jobs use SelectionError; metadata shape/identity
guards use InvalidRequestError. These helpers do not replace supported receipt/
submission services in scientific clients. Bundle names are file names without
path separators/control characters. Scientific paths retain their existing policy.

Shared write failures remain RecordWriteError, retaining cause and exact
record_publication/record_durability/secondary cleanup facts. context.source names
save_bundle, schedule_job, update_job_metadata or save_config; bundle writes add
bundle/bundle_path and a job only when known, config writes add resource=configuration.
A scheduled append reports its effective suffixed job name. A multi-job batch does
not guess which job caused an opaque serializer failure. Unexpected failures after
publication are never converted to not_started. Writer directory creation owns new
snapshot parents; no separate all-storage setup masks its phase diagnostics.

Config/configuration, filter, initialize, schedule and submit root/standalone paths
render adopted failures once, stderr/exit 1, with --debug retaining the original
exception. Schedule uses --autoslurm-debug and still forwards application --debug.
Parser misuse remains exit 2. ACP's expected-error envelope includes shared write
diagnostics without changing receipt/update payloads. Config validation still uses
ConfigurationError; config publication uses RecordWriteError, not a wrapper that
would falsely imply config_write=not_started after successful publication.

Preview/submit add the selected machine to direct-read diagnostics when known.
Read diagnostics have no inferred side-effect claims. Keep exact retained records,
receipts and scheduler IDs; inspect a possibly published append before repeating it.
External readiness, broader post-dispatch orchestration and universal
observation/CLI/ACP policy remain their later tasks.

## Receipt/cache/script records in MVP10.3c.3

Use supported load_submission/list_submissions/refresh_submission and inspection
services. Do not call private record_files or cache helpers in scientific clients.
Exact receipt reads now raise SelectionError instead of raw file/JSON/protocol
errors: resource_missing after observed absence, resource_inaccessible for denied,
dangling or special-file paths, record_invalid for malformed UTF-8/JSON/receipt
structure. Invalid receipt selectors are invalid_argument. Exact receipt_path and
known submission_id/bundle/machine survive in context. Native causes remain chained;
JSON detail contains parse location, never the record contents. Low-level bundle,
receipt and cache reading shares operation record_read, including close_record
for close failures; earlier selector validation remains operation selection.
Shared regular-file checks and nonblocking open prevent blocking on a FIFO.
Read races recheck absence; close failures cannot mask a primary parse/read error.

Missing receipt directories list as []; denied directories or broken receipts
raise a precise error rather than silently returning a partial list. These local
reads do not create storage or launch commands. In normal run inspection a broken
receipt instead adds a per-item error with diagnostic, retaining snapshot IDs.
Neither absence nor a failed read proves scheduler rejection or permits resubmission.

Receipt and tracking projection writes retain RecordWriteError with resource
submission_receipt/tracking_snapshot, receipt_path, submission_id and known bundle/
machine identity. A tracking identity/ID conflict preserves the original bytes.
Existing SubmissionError wrappers propagate an adopted persistence diagnostic
alongside .receipt, without changing accepted IDs, uncertainty or dispatch policy.
Secondary tracking write evidence can add tracking_diagnostic beside tracking_error.
The receipt stays authoritative: even record_publication=not_started only describes
that local write, and can occur after Slurm already accepted a job. Keep .receipt
and .diagnostic together; never reduce this case to a request safe to retry.

asl submission PATH supports --debug, text stderr/exit1 and a --json diagnostic
envelope for adopted direct-read errors. Failed refresh JSON preserves receipt
fields/IDs and adds diagnostic when available. ACP includes diagnostic plus result
receipt for these failures. External refresh/transport error classification remains
MVP10.4/10.5; a legacy error may still have no diagnostic.

Inspection cache errors retain source/message/path and add plain diagnostic.
A genuine missing cache remains quiet; malformed/inaccessible evidence is reported.
Write errors keep live scheduler states, known IDs and fetched log text, with the
existing partial freshness. This includes publication=unknown and failures after
successful publication. Cache errors do not authorize source-log rereads during
refresh=False, repair, deletion or job submission. Broader observation semantics
remain MVP10.6.

Direct create_slurm_script and submission staging use the existing atomic writer
for UTF-8 text. Stage write_text replaces serialize for the text step; all other
publication/durability/cleanup facts match JSON. RecordWriteError context includes
resource=slurm_script, job and known submission identity. Before publication the
old destination survives; after observed publication the complete new script
survives. Rendering still precedes storage access. A staged set is not a transaction:
earlier complete scripts can exist if a later write fails, and dispatch stops.

## Software updates in MVP10.4a

Use update_software(project=relative_project, machine=selected_machine). Keep
SoftwareUpdateError.evidence and .diagnostic together; evidence.diagnostic is the
same plain JSON diagnostic. Invalid project/profile selectors use existing
InvalidRequestError/ConfigurationError instead of raw validation errors, retaining
ValueError compatibility. Invalid explicit machines never select a default.

Operation is software_update and diagnostic.stage names the failed check:
checkout_root, git_checkout, git_commit_before, git_branch, git_upstream,
git_status, environment_python, git_pull, git_commit_after or editable_install.
Host-side failures use probe_source, ssh_update_launch or ssh_update_response.
Evidence.stage retains its existing preflight/pull/install/transport phase.
Context includes machine/project, operator-owned ssh_alias where known, selected
path/executable, resource and source. Environment failures also name field=venv_path.
Original local causes remain in __cause__; remote native objects are not available,
so validated cause kind/errno/returncode survive as facts. Do not call private
update probes or manually interpret their raw output in scientific clients.

A missing or unlaunchable venv_path/bin/python is command_unavailable, with the
attempted executable recorded before launch. The message explains how to correct
venv_path through asl config and confirms that pull/install did not start.
Interpreter prefix mismatch is compatibility_mismatch; nonzero/timeout/invalid
identity responses retain their separate command_failed/command_timeout/
protocol_invalid facts. No environment, alternative interpreter or host is chosen.

effects.git_pull and effects.editable_install describe separate steps. Preflight
failures retain both not_started. A completed Git pull is succeeded even if later
installation fails. Nonzero pip can leave editable_install=partial; installation
state remains failed and observed commits remain available. A negative process
status or timeout during mutation leaves its effect unknown. Post-pull commit
inspection failure retains the observed pull effect, with after_commit=None.
A failed Git command is not proof of rollback. No code copy, reset, stash, merge,
dependency installation or automatic retry is added by this diagnostic layer.

Missing/unlaunchable local SSH can establish no dispatch. Generic communication
errors, nonzero SSH, timeout/interruption or malformed/mismatched/oversized
responses leave update/install unknown, without guessing authentication causes.
Standalone probes still require only the standard library on the login host.
They send plain failure/effect facts, validated and normalized through the same
host error module as local updates. Legacy failure responses without those facts
retain their evidence with unknown effects; no false proof of no work is invented.
The helper evidence version remains 1 with additive fields, not a persisted-format
migration. Record/protocol versions remain independent of package versions.

Raw Git/SSH output is omitted from diagnostics/evidence errors. Pip's last bounded
output lines remain useful and known credential patterns are redacted before
bounding. Native exceptions and their command/output objects belong only to the
debug chain, not serialized diagnostic payloads. Unexpected probe/programming
errors propagate through the local update path rather than becoming preflight
failures or empty success. Remote invalid output is unknown, not safe to replay.

asl software update prints adopted failures once on stderr/exit1. --json retains
existing evidence plus diagnostic; --debug re-raises the original SoftwareUpdateError
with its native cause where available. Request/profile failures use the shared
diagnostic envelope. Parser usage stays exit2; success output is unchanged.
Read-only software status, general SSH/session/helper/transfer readiness and other
CLI/ACP policies remain their separately planned slices.

## At a client boundary

`DiagnosticError` remains a RuntimeError. SubmissionError and SoftwareUpdateError
inherit it while preserving existing positional constructor arguments, message,
`.receipt`/`.evidence`, and Python causes; optional `diagnostic=` is additive.
Those payloads are kept by identity and are never automatically serialized by the
new adapter. Save authoritative evidence in the client before presenting failure.

```python
# Inside a client CLI's existing SubmissionError handler:
client_record['receipt'] = error.receipt
if error.diagnostic is None:
    raise  # Existing client handling is still needed during staged adoption.
exit_with_error(error, json_output=want_json, debug=debug)
```

`render_diagnostic(d)` returns human text without printing. `exit_with_error`
handles only DiagnosticError with a real Diagnostic: text stderr or JSON stdout
by default (optional stream override), then SystemExit(1) without default traceback.
Its JSON envelope is `{status: 'error', message: summary, diagnostic: d.to_dict()}`.
Existing CLI/ACP envelopes/helper protocols are unchanged until their adoption
tasks. Usage stays parser exit 2. Successful inspection of failed science,
missing/empty logs and returned warnings must not be passed to this failure helper.
Unexpected/undiagnosed errors, KeyboardInterrupt and debug requests are re-raised
unchanged; original traceback/cause/payload remain available. If output fails,
the initiating error is re-raised with the output failure in `__context__`.

The error core is stdlib-only and performs no I/O or recovery. Package-root import
still eagerly loads older services; this module does not claim to fix that
separate boundary. Follow existing exact receipt, producing-machine and bounded
log recipes. Client science functions do not need AutoSlurm imports.

## Remote root/helper readiness (MVP10.4b.1)

Public remote_storage_root_from_config and probe_submission_helper now raise
autoslurm.errors.DiagnosticError for expected process/response/capability
failures; invalid explicit root/venv settings use ConfigurationError. These
retain RuntimeError/ValueError compatibility respectively. Catch the expected
family at a client boundary and retain diagnostic.to_dict(), including machine,
ssh_alias, storage_root, field and attempted executable/path where known.

operation is remote_readiness; stages are select_storage_root, select_helper,
probe_storage_root, probe_helper, read_storage_root, read_capabilities and
check_capabilities. Codes distinguish command_unavailable (local SSH launch),
command_timeout, operation_interrupted (signalled command), transport_failed
(SSH255 or incomplete local communication), command_failed (other remote exit),
protocol_invalid and compatibility_mismatch. Do not turn any of these into an
absent path/environment or a rejected job. Native local causes are chained;
unexpected adapter bugs and KeyboardInterrupt propagate unchanged.

Checks run once, with a 30-second timeout and accepted text capped at 64 KiB.
Root output must be one absolute path without traversal/control characters and
match explicit storage_root selection. Capabilities require a unique-key JSON
object with exact integer submission_protocol/execution_tracking values;
booleans are incompatible. Unknown extra fields remain allowed. Empty/invalid
responses differ from an old helper. Normal diagnostics omit arbitrary SSH,
startup and command output. Keep debug causes instead of leaking raw output.

Effects script_transfer/submission_dispatch/scheduler_submission are not_started
for the check. They do not describe unrelated jobs or arbitrary operator-provided
env_command effects during existing root discovery. No setup/launch policy,
authentication handling, fallback, retry, dependency installation or repair is
introduced. Configured legacy path selection remains no-contact. Verify the
selected alias/environment/helper explicitly and update the helper if needed.

asl submit uses the shared stderr/exit1 renderer; --debug rethrows diagnosed
failures with the native cause. SubmissionError still carries its authoritative
receipt; general post-dispatch and CLI/ACP error adoption remain separate tasks.
SSH session/temp/socket/cleanup is adopted in MVP10.4b.2 below; transfers/filesystem
probes remain 10.4c, software status 10.4d and observation failures 10.6. Do not advertise
this slice as universal transport handling or remote environment readiness.

## Owned SSH sessions (MVP10.4b.2)

ssh_submission_session retains its list interface: None for local, [] for
configured sharing, Control options for an owned master. It validates addressing
before allocation and pins the destination/options. User-owned masters are never
explicitly opened/closed. Optional ssh -G observation is 10 seconds and 64-KiB
accepted UTF-8 text; expected command/read/invalid-output failures fall back once,
while invalid configuration, programming bugs and interrupts propagate.

Owned POSIX sockets use /tmp where available and must be under 100 expanded bytes;
open/close commands use 30/10-second timeouts. A resource owner tracks directory,
open, close and directory-cleanup effects separately. errors.py owns diagnostics:
operation ssh_session, stages create_session_directory, validate_control_path,
open_session, close_session and remove_session_directory. Expect storage_failed,
configuration_invalid, command_unavailable, command_timeout, protocol_invalid,
transport_failed, command_failed or operation_interrupted. A failed close leaves
closure unconfirmed even when its local directory was removed. No scheduler
effects or authentication cause are inferred. Normal diagnostics omit raw output.

Cleanup-only failures are now raised, instead of silently ignored. For tracked
submission, catch SubmissionError before a generic DiagnosticError and retain
its receipt. Known acceptance stays submitted with IDs/execution_finished;
partial/uncertain submission stays distinct. Never retry because cleanup failed.
The optional session_cleanup_diagnostics receipt field is up to four bounded
plain diagnostic objects; the workstation owns it and refresh preserves it when
recovering execution receipts. No historical records are migrated or new helper
protocol required. Inspect it through load_submission/inspect_submission.

If another error/interrupt already exists, that same exception stays primary.
Secondary diagnostics are bounded by the existing four-leaf limit; direct errors
also retain session_cleanup_diagnostics and native session_cleanup_errors for
debugging. Unexpected cleanup bugs remain original errors, reported as internal
cleanup observations rather than reclassified I/O failures. Tracked submission
still wraps/retains original causes under its existing receipt boundary; general
CLI/ACP diagnostic adoption remains 10.5/10.8. Directory cleanup is attempted even
after close failure. No credential/key/config change, automatic install, retry,
alternate connection or scheduler-state mutation is introduced.

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

Legacy sync still mirrors only jobs/slurm/out, using ignore-existing for definitions
and checksums for logs. It returns None/progress text; diagnostics on failure add
sync_jobs/sync_slurm/sync_out effects for completed versus not-started/unknown
copies. Only observed missing directories are skipped. An inaccessible or wrong-kind
source raises, and failed source checks create no local target. Earlier/partial
files stay in place; no final success is printed. Sync CLI renders adopted errors
once with exit1; --debug rethrows with causes. Prefer fetch_run/asl fetch for bounded
selected-run evidence; sync remains unbounded whole-subtree copying. General
receipt-aware/ACP/observation adoption remains the later MVP10 tasks.

Required-input/data-root/working-directory preflight uses this same metadata owner,
with one deduplicated remote batch and no command when there are no checks.
Observed missing required paths raise DiagnosticError/resource_missing; denied,
wrong-kind, failed-transport and malformed batches stay distinct. This replaces
FileNotFoundError from validate_jobs/validate_resolved_jobs. Local native causes,
known logical/resolved paths and labels are retained; public preview/submit add
the exact bundle reference. Batch length/order/path identity are validated within
the same 64-KiB response bound. Failed preflight stops before staging, receipt
creation, helper dispatch or sbatch; no blind retry or missing-input inference.
