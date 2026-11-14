# Diagnostic foundation and client handling

MVP10.2 implements the foundation only. Existing AutoSlurm services/CLI/ACP have
not yet adopted it universally; `.diagnostic is None` is normal on legacy errors.
The stale-venv/software preflight correction is still MVP10.4 work. Do not promise
better messages from those services based only on the existence of this module.
Retrieve this installed recipe with `asl agent --sections 15_diagnostics`.

## Public contract

```python
from autoslurm.errors import (
    Diagnostic, DiagnosticCause, DiagnosticError, diagnostic_catalog,
    invalid_argument, missing_resource, command_failure,
)
from autoslurm.apps.error_output import render_diagnostic, exit_with_error
```

`Diagnostic(code, operation, stage, ...)` is immutable and accepts known catalogue
codes. `diagnostic_catalog()` returns a detached map of category/default summary/
next action. Operation/stage and effect-step names are 1–64 character identifiers
(letters first; then letters, digits, underscore, dot or hyphen). The category
property comes from the catalogue. Overrides `summary=` and `next_action=` are
supported, with nonempty wording. `invalid_argument` names the bad field;
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
