# Diagnostic foundation and client handling

MVP10.2 implements the foundation. MVP10.3a adopts local configuration read/profile/
setting/selection failures and the config CLI. Other AutoSlurm services/CLI/ACP
have not adopted it universally; `.diagnostic is None` is normal on legacy errors.
MVP10.3b.1 also adopts the authoring boundaries described below.
MVP10.3b.2 adds snapshot/filter selection and per-entry discovery diagnostics.
MVP10.3b.3 adds pure path/render preparation and saved producing-context validation.
The stale-venv/software preflight correction is still MVP10.4 work. Do not promise
better messages from those services based only on the existence of this module.
Retrieve this installed recipe with `asl agent --sections 15_diagnostics`.

## Public contract

```python
from autoslurm.errors import (
    Diagnostic, DiagnosticCause, DiagnosticError, diagnostic_catalog,
    invalid_argument, missing_resource, command_failure,
    ConfigurationError, configuration_failure, InvalidRequestError,
    SelectionError, selection_failure,
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
freshness, observed_at and observation_state. Values are str/int/bool/None;
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

Bundle authoring/selection/path diagnostics, record publication, configuration
validation's external commands, stale-venv probing and other CLI/ACP parity are
later adoption work. Invalid storage selectors can still fail during eager package
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
path/render failures, file read/publication, transport and ACP parity remain later
slices. The submit CLI uses shared rendering when an adopted authoring error reaches
its preparation boundary; its earlier broken-snapshot gate is not yet migrated.

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
Catch this class and inspect diagnostic.code. Direct bundle file loading retains
its older read exception policy until the record-read slice. Type/selector conflicts,
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
It does not add shell-syntax checking to that legacy direct API. Publication I/O/
atomic replacement remains MVP10.3c. Preview/submit still validate generated shell
syntax through their shared existing pipeline before staging/dispatch. Their
external root discovery/readiness checks are not migrated by this slice.

recorded_execution/execution_context_from_snapshot and saved-context result lookup
use SelectionError at read_execution: absent evidence/exact job is resource_missing,
ambiguous selection invalid_argument, malformed producing roots/transport
record_invalid. Known bundle/job/machine/field is retained; native alias-validation
causes remain chained. Legacy producing project/results roots and transport stay
readable and distinct. No current profile, fallback machine or replacement root is
discovered. Raw loader I/O/JSON failures remain MVP10.3c; observation-side producing
metadata and readiness/existence probes remain their separately planned owners.

`asl submit` and its standalone entry point render adopted preparation diagnostics
once to stderr/exit 1; --debug re-raises the original exception. Schedule keeps its
--autoslurm-debug behavior. Universal ACP/CLI adoption remains MVP10.8. Retain
receipts and original history; never infer a safe resubmission from validation alone.

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
