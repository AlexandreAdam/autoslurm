# MVP10 API-wide error handling with isolated diagnostic ownership

## Status

Scheduled after MVP9 by the user on 2026-11-13. **PLAN.2 expands PLAN.1's narrow
scope:** review the entire public API and its possible failures, centralize error
handling in its own maintainable module, and integrate it strategically. This
broader scope and dedicated ownership are explicit user requirements. It is no
longer a one-to-two-day updater/message patch. No runtime implementation yet;
exact field/helper/type names remain proposed until MVP10.1–2 settle them.
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

Representative source review for PLAN.2 also found different failure shapes
across the interface: plain ValueError/AttributeError, typed exceptions carrying
evidence/receipts, inspection lists of per-item errors, CLI SystemExit and ACP
string messages. `path_exists` returns `returncode == 0` for both local `test`
and SSH, conflating transport failure with absence. ACP catches general Exception
and returns only its string. Submission's broad catch, by contrast, also protects
receipts and accepted IDs: narrowing it mechanically would lose critical evidence.
The audit must examine purpose and effect at each catch, not replace all catches
with one decorator or require every negative observation to become an exception.

## Decisions and proposed contract

- **E10.1 Requested:** explain the actual failed check/resource, selected context,
  what is known about effects, and the next safe action. Existing known/unknown
  guarantees remain mandatory; no retry or host/environment fallback.
- **E10.2 Requested:** one dedicated error module owns the shared contract,
  categories/codes and diagnostic construction. Integration belongs at selected
  boundaries with meaningful context, rather than ad hoc text throughout the
  implementation or a catch-all around every function. Proposed layout is below.
- **E10.3 Proposed:** a shared plain-data diagnostic with operation, stage,
  stable cause code, human summary, selected machine/project/job, relevant config
  field/path, bounded cause detail, observed effects and corrective action.
  Set attempted identities before executing external commands. Reuse current
  evidence/receipt objects; do not introduce a parallel error database.
- **E10.4 Proposed:** expected CLI failures show this explanation and return nonzero
  without a default traceback. Python callers retain typed exceptions and their
  evidence/receipts; JSON exposes the same facts. Unexpected bugs remain visible
  through tracebacks/debug output. Do not catch every exception into 'failed'.
- **E10.5 Required limit:** never expose raw credential-bearing Git URLs/config,
  tokens or unbounded command output just to improve diagnosis. Keep safe errno,
  attempted executable/path, return code and bounded relevant diagnostics.

## Dedicated module and dependency rules

Proposed concrete starting layout (these are future files, not current imports):

```text
src/autoslurm/errors.py
    diagnostic model and stable code/category catalogue
    common exception contract and named diagnostic constructors
    context/cause enrichment and bounded safe serialization

src/autoslurm/apps/error_output.py
    shared terminal presentation and CLI exit policy
    consumes diagnostics; does not inspect private backend state
```

`errors.py` is the single owner, with isolated unit/contract tests. It must use
only dependency-light/plain-data helpers and never import config, transport,
Slurm, persistence, scientific libraries or CLI modules. It performs no I/O,
printing, process exit, environment lookup, retry or repair. Backends depend on
it; it never calls them to rediscover missing context. A small related package is
an option only if real size requires it, with the same single public boundary.

Centralize code definitions, shared wording/correction rules and error facts;
keep terminal layout outside the core. Human output, JSON/ACP and Python
exceptions consume the same diagnostic. Domain services still own validation,
classification inputs and effects. A generic translator cannot infer whether a
job was accepted from an OSError, or whether a shell exit code means a missing
path rather than failed SSH. Reuse the catalogue through named constructors with
facts instead of concatenating new messages in each caller.

Preserve `SoftwareUpdateError.evidence` and `SubmissionError.receipt`, along with
exception chaining for debugging. A shared base/diagnostic property may be added,
but do not erase existing domain payloads or introduce a class for every string.
Do not classify unexpected TypeError/KeyError/programming bugs as ordinary user
errors just because a public call caught them.

Standalone SSH probes still require no remote AutoSlurm installation. Return
validated standard-library facts (attempted path, errno, phase, return code and
known effects); normalize/render through the shared host module. Reuse the same
normalization for local results. Do not copy a separate human-message catalogue
into every remote worker. Preserve older plain error fields as explicitly planned
compatibility, with unknown codes/details rather than fabricated classifications.

## Diagnostic contract and failure families

The proposed diagnostic separates these facts:

| Part | Purpose |
|---|---|
| Stable code/category and summary | Agents classify a failure without parsing English; humans see the concrete problem |
| Operation and stage/check | Updating software differs from submitting; an environment probe differs from Git pull |
| Selected context | Machine/alias, project, bundle/receipt, job/task, field/option, logical and resolved path as applicable |
| Cause and provenance | Originating adapter/probe, safe exception kind/errno, return code and bounded diagnostic; retain original cause for debug |
| Effects/outcome | Per affected step: not started, observed success/failure, partial or unknown; references to authoritative receipts/observations |
| Corrective action | Specific operator/client action based on known evidence, without unconditional retry advice |
| Observation quality | Freshness, timestamp, absent/stale/unavailable distinctions; keep per-item scope and secondary diagnostics |

Category does not determine outcome: a timeout before dispatch and a timeout
after dispatch may have the same cause family and different effects. An empty
log, valid 'path absent', pending job, or missing cache is often a normal
observation. A scientifically failed job is an inspected outcome, not evidence
that the inspection API itself failed. Warnings/potential problems and unavailable
checks need explicit result policies, not exceptions for every non-success value.

Initial failure families to refine in the audit:

- Usage/selection: conflicting selectors, ambiguous/moved indices, unknown run,
  job or sparse array task, unsupported action/CLI capability.
- Configuration/environment: missing/malformed profile, conflicting roots, invalid
  SSH alias, stale venv, wrong interpreter, missing command/build dependency.
- Definition/argument/path validation: unknown option, type/default/encoding
  mismatch, missing input/cwd, root escape, dependency cycle, invalid Slurm setting.
- Local storage/state: missing/corrupt/unsupported JSON, collision, permission,
  disk/inode/quota exhaustion, read-only filesystem, failure after publication.
- Process/transport/protocol: launch failure, timeout, interrupted session,
  authentication/access failure when evidenced, malformed/oversized/helper-version
  response; preserve ambiguity when the actual cause is not known.
- Software preparation: missing/dirty/detached checkout, absent upstream,
  non-fast-forward pull, incompatible dependency evidence, pip/build/install error.
- Scheduler/submission: account/partition/resource rejection, missing/unparseable
  scheduler response, partial DAG acceptance, uncertain dispatch, tracking failure.
- Observation/artifact: query failure/retention gaps, missing/empty/denied/changed
  log, invalid path pattern, cache absence/staleness/corruption/write failure.
- Lifecycle mutations: partial or unobserved cancellation, cleanup/delete or sync
  failures, confirmation/ownership conflicts and filesystem changes during work.
- Internal defects/interruption: invariant violation or unexpected exception,
  cancellation by the operator, and a secondary failure while preserving evidence.
  These cannot be silently downgraded to 'invalid config' or 'nothing happened'.

## Initial API failure and placement map

This is a source-grounded seed, **not completion of MVP10.1's per-callable audit**.
Inventory every `__all__` export, root action/alias, console entry point and ACP
action; include lower-level exported helpers, not only the preferred high-level
workflow. Each final row needs exact entry/owner, failure modes, present behavior,
translation site, diagnostic codes, effect/observation policy, next action and a
test reference. Aliases point to an owner rather than creating duplicate handlers.

| API family / current owners | Failures to examine | Strategic translation / evidence rule |
|---|---|---|
| Config/root selection: `config`, `storage`, config/filter CLI | Missing/bad JSON, unknown default/profile, invalid alias/roots/env, save failure | Validate field with profile/config path; config writes distinguish pre/post publication |
| Discovery/navigation: `bundle_selection`, `list_runs`, submission lists | Missing/ambiguous/index/date selection, broken records, mixed healthy/broken entries | Resolve once; never silently select a neighboring run or hide all good entries |
| Authoring: `schedule_job`, `save_bundle`, dependency/manifest helpers, MVP9 | Bad names/types/defaults, unknown options, cycles, unsupported command/runtime | Attach named option/job/source and dependency edge; fail before saving or dispatch |
| Paths/readiness: execution contexts, `remote_fs`, preparation/preview | Missing inputs/cwd, permission, root escape, invalid producing metadata, failed existence probe | Keep logical and resolved paths; transport failure is unknown availability, not False |
| Persistence: `record_files`, bundle/receipt loading and cache | Decode/version/permission/collision/quota/fsync/cleanup errors | Report intended vs published record and retained evidence; do not claim atomic rollback after publication |
| Transport/transfers: `transport`, `file_transfer`, SSH sessions/helpers | Launch/auth/connect/session/transfer/protocol/timeout errors | Capture safe external facts with operation phase; borrowed-session cleanup must not mask outcomes |
| Software: manifests/requirements/status/update and standalone probes | Unknown compatibility, wrong/missing Python, dirty Git, pull/build/pip/lost response | Separate readiness evidence from update effects; retain actual paths and before/after commits |
| Submission: `job_runner`, submission operation, local/remote bulk drivers | Preflight/staging/dispatch rejection, malformed acceptance, partial DAG, lost receipts | Preserve accepted IDs and uncertainty in the existing receipt; no submit fallback/retry |
| Recovery evidence: load/list/refresh submission, saved execution lookup | Missing/corrupt/mismatched/stale receipt, interrupted helper, failed projection | Exact identity, latest known effects, missing evidence remains unknown |
| Status/inspection/context: scheduler, inspection collection/state, public context helpers | Query failure, unknown/expired task, unavailable profile, partial batch, internal projection bug | Per-machine/job/task diagnostics; keep healthy evidence and distinguish collection from job failure |
| Logs/scripts/cache: inspection artifacts, log reader/probe/cache | Missing/empty/denied/special/rotated/truncated files, protocol/cache errors | Preserve bounded excerpts and time/source; failure of one file/cache does not erase others |
| Cancellation: cancel CLI/adapters | Invalid selection, inaccessible machine, scancel rejection/timeout, mixed targets | Preview rules retained; request accepted differs from observed cancellation; report each affected target |
| Cleanup/sync: clean CLI, sync/transfer APIs | Unsafe/stale selection, changed ownership, missing source, denied delete/write, partial mirror | Per-item retained/deleted/copied/unknown effects; no silent cleanup or replay |
| Integration/discovery: root/standalone/alias CLI, ACP, agent/scan/context utilities | Bad action, optional adapter unavailable, docs/app discovery failure, swallowed bugs, formatting failure | One outer presentation; common diagnostic plus result/receipt; unknown bugs remain debuggable |

## Strategic catch and propagation rules

1. Validate at the nearest owner before a side effect. Add option/field/job context
   there; do not attempt to reconstruct it from a generic exception later.
2. Translate external failures at the adapter where command identity, exit status
   and phase are known. Maintain explicit facts about commands that actually
   started. Do not infer a remote auth or missing-file diagnosis from a generic
   nonzero exit without supporting evidence.
3. At orchestration boundaries, enrich once with operation identity, effect and
   authoritative evidence. Existing typed errors pass through with context;
   avoid repeated nested 'operation failed' strings or new generic wrappers.
4. Collect per-item observation failures in the result when good evidence remains;
   raise a domain failure when the requested operation cannot provide its contract.
   Specify that choice for every audited entry. Error codes never replace run state.
5. At the outer CLI/client/ACP boundary, render expected errors once, apply the
   agreed exit/envelope policy and preserve the structured payload. Internal
   libraries do not print/exit just to report an error. Help/usage remains distinct
   from failed operations; JSON results stay machine readable.
6. Evidence-saving catches around side effects remain even for unexpected bugs or
   KeyboardInterrupt. Persist known IDs/effects first, then retain the original
   cause/debug visibility. Cleanup, cache, presentation or tracking failures become
   secondary diagnostics and cannot overwrite the initiating failure/evidence.

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

The user's expanded scope supersedes the old three-task updater-first sequence:

| Task | Deliverable |
|---|---|
| MVP10.1 | Complete public API/action/entry-point failure and catch-site register; agree result/exception and effect contracts |
| MVP10.2 | Dedicated error module, isolated tests, shared terminal adapter and JSON/Python/ACP conventions |
| MVP10.3 | Config, selection, arguments/paths, bundle/preflight and persistence adoption |
| MVP10.4 | External transport/readiness/software adoption, including the stale-venv regression |
| MVP10.5 | Submission/receipt/interruption/secondary-failure adoption with retained acceptance evidence |
| MVP10.6 | Status/inspection/log/cache adoption with explicit observation quality and partial data |
| MVP10.7 | Cancel/clean/sync and discovery/context adoption with per-target/per-file effects |
| MVP10.8 | Consistent public Python, root/standalone/alias CLI, ACP and client contracts/docs |
| MVP10.9 | Close coverage register, systematic failure injection, full offline/artifact/reference-client gates |

Each slice is independently usable with focused tests and its affected public
presentation wired in; MVP10.8 checks consistency rather than leaving all
presentation until the end. Broad MVP10 completion requires all audited interfaces
covered, not just a better updater message. Re-estimate effort after the full
inventory; the original one-to-two-day estimate no longer applies.

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

Settle diagnostic field names, compatibility with existing result JSON, exact
error module exports and the debug/CLI exit conventions in MVP10.1–2. Keep additive fields where possible; an actual
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

Changing a boolean/exception/result contract such as `path_exists` must be
explicitly released and reflected in agent guidance; do not quietly keep the
incorrect False behavior merely to avoid a boundary decision. Persisted old
records retain their evidence and remain interpretable according to that release's
policy. No unrelated command renames, new workflow engine or blanket module moves.

## Verification and log

Use fake Git/SSH/subprocess and disposable local fixtures. Reproduce missing and
nonexecutable Python, wrong prefix, malformed/nonzero/timed-out probes, Git launch
failure, pull/install partial/unknown outcomes, scheduler rejection and log errors.
Assert actionable text and equivalent structured evidence as well as absence of
forbidden commands. Verify expected CLI failures, unexpected-bug/debug behavior,
exception/receipt preservation, output bounds and credential redaction. Run the
full offline suite and narrow wheel/reference-client smoke at completion.

Maintain coverage by API inventory, not just by a line-coverage percentage. For
each public callable/action, assert code/context, cause preservation, rendering/
structured equivalence, next action, effects/evidence and the absence of forbidden
commands. Test both local and mocked remote implementations where supported.
Specifically inject record-save and cleanup failures after scheduler acceptance,
SSH existence-check failure versus genuine absence, mixed observation batches,
partial cancellation/sync, unknown post-dispatch outcomes, unexpected bugs and
user interrupts. Exercise direct/standalone/alias entry points and ACP envelopes.
Unit tests for the error module run without backends or external commands; catalogue
and serialization tests catch missing context, malformed facts and redaction/bounds.

MVP10 is complete only when every inventory row has an adopted policy and a
verified test/owner. No silent exclusions or undocumented message-only fallbacks.
Rare platform-specific behavior that cannot be exercised offline needs a clearly
recorded limitation; mocks do not establish live cluster compatibility.

2026-11-13, PLAN.1: read the real updater/probe/CLI and missing-interpreter tests;
documented the diagnosed information loss and scheduled MVP10.1–3 after MVP9.
Documentation/link review only. No runtime fix, cluster contact, client/config
change or test rerun. Last full baseline remains 623 passing offline tests.

2026-11-13, PLAN.2: user explicitly requested an API-wide review and isolated error
module. Reviewed public exports, root/standalone/ACP surfaces and representative
boundary implementations; seeded the failure map and expanded to nine staged
tasks. This does not claim the per-callable audit is complete. Dedicated ownership
and the larger scope are requested; exact model/API names remain proposed.
Documentation review only; no implementation, environment or runtime-state change.
