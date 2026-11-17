# MVP10.4d software-status diagnostics

## Status and scope

Complete locally in 0.2.0.dev11 on dev after explicit continuation, 2026-11-17. Read-only
inspect_software/software_expectations and software status CLI adopt shared errors.
Keep supported result shapes/states, important dependencies and machine markers;
no scientific imports, setup/module activation, Git fetch/pull, install, SSH/auth
management, source copies, new saved formats or historical migration.

## Contract

Validate request/profile/expectations before dispatch. Known invalid requests use
InvalidRequestError, invalid selected profile ConfigurationError; unreadable or
invalid local declarations use shared diagnostics with exact file/field and native
cause. Requirement include/cycle/unsupported-option warnings stay conservative
unknown checks; never run directives or expose credential-bearing source URLs.
Caller-supplied expectation dictionaries must satisfy the same contract.

Whole-operation launch/timeout/signal/SSH/nonzero/encoding/bounded-response or
protocol failures raise DiagnosticError with selected alias/root/project/Python,
native local causes and no mutation effects. Remote discovery remains one SSH
system-python3 payload, no AutoSlurm install required. Keep 60-second outer timeout,
1-MiB accepted response and bounded per-Git/environment checks. Strictly validate
identity, states and types, including bool-versus-int, unique keys and commit IDs.
Malformed per-project/per-package evidence becomes an unavailable item with a
protocol diagnostic while valid neighbours survive; invalid whole identity fails.

Standalone workers return safe plain failure facts; errors.py owns diagnostic
wording/actions, host normalization owns mapping facts to per-root/project/
environment/package/check diagnostics. Local partial-result failures retain safe
cause facts, not native exception objects in JSON; raised boundary errors chain
native causes. Expected filesystem/metadata/process errors stay distinct from
unexpected bugs/interrupts. Avoid broad TypeError/AttributeError catch masking.
Missing versus inaccessible paths and packages remain different. Retain known
commit/version even if a later check fails; never convert unknown dirty/source
identity into clean/compatible. No automatic retries or fallback interpreter.

Compatibility remains a finding with compatible/potential_problem/unknown and
per-check details, not an exception. Add diagnostics to actionable mismatch/unknown
checks without discarding healthy checks or replacing machine marker policy.
The status CLI retains nonzero on unavailable/partial/unknown/mismatch outcomes,
prints reasons beside useful evidence, supports --json diagnostic payloads and
--debug for raised native chains. Unexpected bugs propagate. Public route/ACP
parity outside software status remains later MVP10 tasks.

## Verification

Offline native/process/protocol/schema/partial matrices; declaration errors and
unsafe inputs; independent Git/environment/package outcomes; exact selected venv,
no science imports/writes/retries, CLI/root/JSON/debug, standalone temporary local
Git/venv worker regression, full suite and no-Git installed-artifact smoke.
Update inventory, version/changelog, recipes, installation evidence and task log.

## Checks and closure

86 new cases cover native SSH failures/cause identity, timeouts/signals/nonzero,
encoding/size/JSON/duplicates/types/root identity, malformed neighbour projects/
packages, root permission/I/O/loop failures, each Git stage and retained commit,
missing/wrong/unavailable environment and exact attempted interpreter, package
lookup/version/source metadata failures, local declarations and invalid requests,
unknown target markers, mismatch findings and CLI text/JSON/debug/partial evidence.
Contradictory missing-plus-failure evidence becomes unavailable; it cannot turn
a denied read into observed absence. Git diagnostics name the attempted Git
executable. Unexpected bugs/interrupts stay native. Existing status expectations now assert
typed diagnostics or partial item results rather than generic RuntimeError;
remote mocks include the explicit interpreter-verification facts.

1669 full offline tests passed in 13.41 s, 73 expected collision warnings;
`.development/test-runs/software-status-diagnostics.xml`. This includes the actual
standalone payload against temporary local Git/venv/dist-info fixtures, no package
installation, no scientific import and unchanged Git index timestamp. Audit
matches 266 routes/138 owners/23 broad catches; no new broad handler/public route.
Normal software status error JSON now uses the shared envelope at the dev11
boundary. Returned observations/checks add plain diagnostics; no saved records,
helper capability or historical migration changes. Unknown/partial is not a clean
or compatible runtime, and compatibility remains metadata-only.

No-Git/no-runtime-import metadata, direct wheel/sdist rebuild and disposable
installed version/API/CLI/JSON/debug/partial-cause/symlinked identity/mismatch/
no-write/no-fallback/guidance checks pass. Wheel member contents match; hashes are
in the installation register. Base imports this checkout at dev11; distribution
metadata remains 0.1.0 without reinstall. Rollback remains clean at 33bcbd3.
No live cluster, daily config/state, scientific imports/dependency install,
external client, history or rollback edits; unrelated user documents/evidence
excluded. Parent 10.4 is complete. Review/split MVP10.5 submission/recovery next;
MVP11 job-status refactor stays planned.
