# MVP10.4b remote readiness diagnostics

## Status

b.1 complete locally in 0.2.0.dev8; b.2 complete locally in 0.2.0.dev9,
2026-11-16. Split before implementation: b.1 selected-root discovery and
submission-helper capabilities; b.2 SSH session ownership/cleanup. Parent b is
complete; 10.4c transfer/filesystem diagnostics are next, parent 10.4 remains open.
The user requested continuing MVP10 and a broader future status refactor. Work
on dev with temporary state and mocked external commands only.

## b.1 implementation contract

Keep SSH vector construction pure in transport.py and preserve the current root
discovery/helper launch commands. One small readiness adapter owns bounded
read-only command observations and strict root/capability response parsing.
errors.py owns diagnostic wording/codes and corrective actions, without I/O.
Use existing DiagnosticError/ConfigurationError; no new exception hierarchy.

Classify missing/denied local SSH launch, timeout, signal, SSH255, other nonzero,
invalid encoding/shape and unsupported helper capabilities separately. Do not
guess password, gateway, 2FA, DNS or account causes from arbitrary stderr. Keep
native local causes chained, safe errno/returncode, selected machine/alias/root,
attempted configured Python and field. Omit raw SSH/startup/config output.
Root output must be one absolute non-traversing path; explicit selection must
match. Capabilities are a bounded JSON object with exact integer protocol values,
not booleans; extra future fields are allowed. A failed command does not prove
that the helper, environment or path is absent. No retries or alternate roots.

Explicit invalid root and missing venv fail locally before any process. Command
observations use 30-second timeouts and bounded accepted responses; these are
pre-submission checks, so scripts, dispatch and sbatch are not started. User-owned
env_command setup may execute during existing root discovery; its arbitrary
effects are not classified as read-only or rolled back. Existing legacy path
selection remains no-contact. No login-shell/module setup policy change, remote
package install or active environment readiness proof.

Expected failures use the shared terminal renderer on submit and current clients
that already handle diagnostics. --debug rethrows the original chain. Preserve
legacy generic errors for boundaries not yet adopted; no broad bug-to-readiness
translation. Submission/receipt errors remain their separate authoritative
payloads and are not routed through a generic exception handler.

## b.2 implementation contract

Implemented locally after explicit user continuation, 2026-11-16. Keep the public
context manager yielding list options, [] for configured sharing and None for
local execution. A focused resource owner holds one pinned destination/options,
local directory and observed open/close/remove effects. Pure diagnostic wording
stays in errors.py. No user connection is explicitly opened/closed, no credential
handling, retry, fallback machine or helper dispatch is added.

Validate addressing before allocation. Optional ssh -G remains a single bounded
10-second observation: expected command/encoding/unreadable output falls back
to an owned connection; programming bugs and invalid profiles propagate. Owned
directories use short /tmp paths where available. Check expanded socket bytes
before SSH. Diagnose local allocation, launch, timeout, exit/signal and cleanup
separately, omitting arbitrary SSH output and retaining native causes. Bound
owned open/close commands to 30/10 seconds. Snapshot the destination so a body
profile edit cannot redirect cleanup. Preserve known versus unknown effects.

After a successful body, failed cleanup raises its diagnosed error. In tracked
submission the existing observed-dispatch boundary retains submitted state and
all accepted IDs in SubmissionError.receipt; a cleanup error is not rejection.
After a body/open failure or interrupt, preserve that same primary exception,
attach bounded cleanup diagnostics (secondary when a primary diagnostic exists),
and retain native cleanup exceptions for debugging. Unexpected cleanup bugs are
not relabelled as expected I/O. Attempt directory removal even if closing fails;
never claim the master closed merely because its local directory was removed.
No blind retry or scheduler-state mutation follows either outcome.

Receipt protocol1 is unchanged. A new optional session_cleanup_diagnostics
field holds up to four plain bounded diagnostic objects observed by the
workstation. Refresh preserves local facts; helper responses cannot invent or
replace them. Existing records remain readable, without historical migration. General submit CLI receipt/diagnostic presentation remains
10.5/10.8; this slice must keep an actionable safe message and accepted receipt
evidence through current clients. Stage/property facts describe session resources,
not scheduler acceptance or previous script transfer. Real cluster checks remain
outside scope. Verify direct session behavior, partial/lost/successful submission,
primary/secondary interruptions, cleanup-only/native/debug cases, isolation,
installed artifacts, public aliases and accurate agent/human guidance.

## Verification

Offline process-fault/root/capability matrices, explicit no-effect guards,
redaction/bounds, no fallback/retry, exact commands and local causes. Exercise
public submission, root/standalone CLI/debug and installed helper/artifact parity;
run the full suite and update inventory/docs/register/version/changelog/plan.
Actual cluster behavior remains unverified. Session teardown is b.2; transfers,
filesystem existence, software status and dispatch/recovery remain later slices.

## Decisions

Shared error ownership and strategic adoption are user requirements. This split,
readiness module and parser limits are implementation choices. No broader
technical proposal is marked accepted without user review.

## b.1 checks and closure

70 new cases cover process faults, native causes, redaction, exact selected root/
Python/alias/effect facts, invalid settings before contact, malformed/traversing/
misdirected roots, capability shape/duplicate keys/nonstandard constants/deep
JSON/booleans/versions, valid command policy, legacy no-contact selection and
unchanged unexpected bugs/KeyboardInterrupt. Root and standalone submit CLI
diagnose once or rethrow with --debug, before any receipt/script/transfer/sbatch.
The previous tracking regression now checks typed incompatibility versus invalid
response, instead of requiring the same wording for both.

1431 full offline tests passed in 11.30 s, 67 expected collision warnings;
`.development/test-runs/readiness-diagnostics.xml`. AST audit still matches
266 routes/138 owners/21 reviewed broad catches. No new catch-all or public route.
Optional storage_root context is additive to diagnostic version1; no receipt,
bundle, cache or helper protocol changed. No-Git/no-runtime-import metadata,
wheel/sdist-to-wheel and installed version/root/helper/causes/effects/CLI/debug/
no-dispatch/guidance smoke pass; direct/rebuilt wheels match. Hashes and source/
installation evidence are in the installation register.

Main/base imports dev8; editable metadata stays 0.1.0 without reinstall. No actual
cluster, daily state/config, base/test dependency install, external client,
historical records or pinned rollback change. User documents/evidence excluded.
MVP11's broadened status scope remains planned, without runtime changes here.
Next: b.2 session lifecycle; parent b/10.4 remain open. No universal CLI/ACP
diagnostic parity or remote environment readiness is claimed by b.1.

## b.2 checks and closure

53 new regressions cover allocation/socket/open/close/remove faults, native causes,
unknown outcomes, optional probe bounds/fallback, invalid profiles before allocation,
pinned destination/options, cleanup-only and primary/secondary bugs/interrupts,
saturated secondary diagnostics, and independent laptop/cluster receipt refresh.
Successful/partial/lost-final/lost-active dispatch retains acceptance/uncertainty
and IDs; refresh recovers execution evidence without replay or losing cleanup.
Remote helper responses cannot invent workstation cleanup observations.

1484 full offline tests passed in 12.12 s with 70 expected collision warnings;
`.development/test-runs/ssh-session-diagnostics.xml`. Inventory matches 266 routes/
138 owners/23 reviewed broad catches. The changed public guard and two new resource
cleanup guards preserve native primary/secondary errors rather than classify bugs.
No new public API. Human SSH/errors and client/installed-agent guidance document
resource effects, receipt metadata and the cleanup-only behavior change.

No-Git/no-runtime-import metadata, direct wheel/sdist-to-wheel rebuild and disposable
installed version/CLI identity/session ownership/native causes/cleanup/accepted
receipt/refresh/no-retry/guidance checks pass for 0.2.0.dev9. Direct/rebuilt wheel
member contents match; archive hashes are in the installation register. Main/base
imports dev9, editable metadata stays 0.1.0 without reinstall. Pinned baseline is
clean at 33bcbd3. No real SSH/cluster, daily config/state, dependency install,
external client, historical migration or rollback change. Unrelated user documents
and evidence remain excluded. General receipt-aware CLI/ACP diagnostic parity
remains 10.5/10.8. Next: 10.4c transfer/filesystem boundaries.
