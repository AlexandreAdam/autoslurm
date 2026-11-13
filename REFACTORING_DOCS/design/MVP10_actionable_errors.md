# MVP10 Actionable errors with preserved operation evidence

## Status

Scheduled after MVP9 by the user on 2026-11-13. PLAN.1 records this scope; no
runtime implementation yet. Clear, actionable errors are the requested outcome.
Field names and helper APIs below are proposed until their task settles them.
[PLAN.md](../../PLAN.md#mvp10-actionable-failures-with-preserved-evidence) owns tasks.

## Problems and evidence

The reported Gaia resubmit failed before software update because the selected
profile's venv path no longer existed. In `software_update_probe.py`, launching
`<venv_path>/bin/python` can raise FileNotFoundError, but `update_checkout` catches
OSError/timeout/interruption and replaces the cause with a generic preflight
message. It records `installation.python` only after `_environment_python` returns,
so the attempted executable can disappear from evidence too. The existing
missing-Python regression proves pull/install did not run, but does not assert
that the explanation identifies the missing interpreter or correction.

The client then wraps all such errors as 'the pull failed', producing a long
traceback without the useful diagnosis. A pull may not have started, or may have
succeeded before an installation failed; operation and failing stage must remain
distinct. AutoSlurm can expose evidence and guidance; embedding clients must catch
and present expected failures at their own CLI boundary. This task does not
silently change Gaia or the cluster environment.

## Decisions and proposed contract

- **E10.1 Requested:** explain the actual failed check/resource, selected context,
  what is known about effects, and the next safe action. Existing known/unknown
  guarantees remain mandatory; no retry or host/environment fallback.
- **E10.2 Proposed:** a small shared plain-data diagnostic with operation, stage,
  stable cause code, human summary, selected machine/project/job, relevant config
  field/path, bounded cause detail, observed effects and corrective action.
  Set attempted identities before executing external commands. Reuse current
  evidence/receipt objects; do not introduce a parallel error database/hierarchy.
- **E10.3 Proposed:** expected CLI failures show this explanation and return nonzero
  without a default traceback. Python callers retain typed exceptions and their
  evidence/receipts; JSON exposes the same facts. Unexpected bugs remain visible
  through tracebacks/debug output. Do not catch every exception into 'failed'.
- **E10.4 Required limit:** never expose raw credential-bearing Git URLs/config,
  tokens or unbounded command output just to improve diagnosis. Keep safe errno,
  attempted executable/path, return code and bounded relevant diagnostics.

Desired missing-venv explanation (illustrative wording):

```text
Cannot update gaia-asteroseismology: configured environment Python was not found.
Machine: <selected profile>
Setting: venv_path
Attempted executable: <configured venv>/bin/python
Stage: environment preflight
Git pull: not started. Editable install: not started.
Correct venv_path in this profile, verify the environment, then explicitly retry.
```

Do not invent a missing path from the traceback or choose a nearby environment.
The interpreter running the client and the configured job environment can differ;
report both where relevant without assuming they must be the same environment.
'Nothing submitted' belongs to submission/client evidence, not the updater alone.

## Task slices and failure behavior

MVP10.1 handles updater preflight and its retained diagnosis. MVP10.2 extracts the
small common contract/formatter and applies it to priority config, argument/job
preparation, software-update, submission and log CLI boundaries. MVP10.3 adds the
reference client/handoff recipe and completes regression/docs/package checks.
Do not make a complete rewrite of every exception a prerequisite for MVP10.1.

| Failure | Required explanation/evidence | Effect rule |
|---|---|---|
| Missing or nonexecutable venv Python | Attempted executable, selected setting/profile, missing vs permission | Pull/install not started |
| Wrong interpreter prefix | Expected venv and observed prefix | Pull/install not started |
| Probe nonzero, malformed response or timeout | Which probe failed; safe return code/detail or unavailable observation | Pull/install not started |
| Missing Git/checkout, dirty tree, absent upstream | Distinct failed check and relevant path/branch | Preserve preflight no-mutation evidence |
| Pull failure/timeout/lost response | Before/after commits when observed, stage/cause | Unknown effects stay unknown; no implicit reset/retry |
| Pip failure after pull | Pulled commit and install failure/partial environment | Never claim no code/environment changes |
| Submission rejection/partial/uncertain | Existing receipt, accepted IDs and failures | Never erase acceptance or blindly resubmit |
| Log permission/transport/missing/cache failures | Retained good excerpts and specific failed observation | Never relabel unknown as empty/success |

## Open questions and forward constraints

Settle diagnostic field names, compatibility with existing result JSON, and the
small debug interface in MVP10.2. Keep additive fields where possible; an actual
breaking shape needs an explicit release/data policy. Public exception properties
remain readable. Clients should display the provided diagnosis instead of
assembling their own misleading 'pull failed' labels; demonstrate that in the
in-repository reference client and document the external integration change.
An external client change is a separate repository task when authorized.

No environment discovery/creation, automatic package repair, SSH authentication
handling, config synchronization, new deployment system, retry engine or global
logging service. Readiness checks remain explicit observations, not promises that
a profile cannot drift after a check. Existing config editor capabilities and
their optional live validation must be described accurately; no new config flag
is promised here.

## Verification and log

Use fake Git/SSH/subprocess and disposable local fixtures. Reproduce missing and
nonexecutable Python, wrong prefix, malformed/nonzero/timed-out probes, Git launch
failure, pull/install partial/unknown outcomes, scheduler rejection and log errors.
Assert actionable text and equivalent structured evidence as well as absence of
forbidden commands. Verify expected CLI failures, unexpected-bug/debug behavior,
exception/receipt preservation, output bounds and credential redaction. Run the
full offline suite and narrow wheel/reference-client smoke at completion.

2026-11-13, PLAN.1: read the real updater/probe/CLI and missing-interpreter tests;
documented the diagnosed information loss and scheduled MVP10.1–3 after MVP9.
Documentation/link review only. No runtime fix, cluster contact, client/config
change or test rerun. Last full baseline remains 623 passing offline tests.
