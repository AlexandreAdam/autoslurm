# Diagnostic foundation and client handling

MVP10.2 implements the foundation. MVP10.3a adopts local configuration read/profile/
setting/selection failures and the config CLI. Other AutoSlurm services/CLI/ACP
have not adopted it universally; `.diagnostic is None` is normal on legacy errors.
MVP10.3b.1 also adopts the authoring boundaries described below.
The stale-venv/software preflight correction is still MVP10.4 work. Do not promise
better messages from those services based only on the existence of this module.
Retrieve this installed recipe with `asl agent --sections 15_diagnostics`.

## Public contract

```python
from autoslurm.errors import (
    Diagnostic, DiagnosticCause, DiagnosticError, diagnostic_catalog,
    invalid_argument, missing_resource, command_failure,
    ConfigurationError, configuration_failure, InvalidRequestError,
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
