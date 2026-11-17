# MVP10.4b remote readiness diagnostics

## Status

b.1 complete locally in 0.2.0.dev8, 2026-11-16. Split before implementation: b.1 selected-root
discovery and submission-helper capabilities; b.2 SSH session ownership/cleanup.
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
