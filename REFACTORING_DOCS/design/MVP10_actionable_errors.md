# MVP10 API-wide error handling with isolated diagnostic ownership

## Status

Scheduled after MVP9 by the user on 2026-11-13. **PLAN.2 expands PLAN.1's narrow
scope:** review the entire public API and its possible failures, centralize error
handling in its own maintainable module, and integrate it strategically. This
broader scope and dedicated ownership are explicit user requirements. It is no
longer a one-to-two-day updater/message patch. **MVP10.1 is complete:** the
[full audit](MVP10_api_failure_audit.md) and
[coverage register](MVP10_api_inventory.json) account for 233 routes, 112 owners
and all 18 broad catches. **MVP10.2 is implemented locally:** stdlib-only errors.py,
the opt-in terminal adapter and additive diagnostics on existing domain exceptions.
**MVP10.3a is implemented locally:** configuration read/profile/selection validation
and the config CLI adopt the shared core. **MVP10.3b.1 is implemented locally:**
authoring adopts InvalidRequestError. **MVP10.3b.2 is implemented locally:**
snapshot/filter selection and per-entry discovery use shared diagnostics.
Current coverage is 256 routes/132 owners/16 remaining broad catches; two masking
handlers were removed. Other service adoption remains pending.
MVP10.3 was split before implementation into configuration (a), authoring/selection/
paths (b) and publication (c); b was then split into authoring (b.1), snapshot
selection (b.2) and pure path/render preparation (b.3) before its implementation.
The current API/policy is documented below without claiming formal acceptance
of every proposed technical decision or universal CLI/ACP migration.
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
MVP10.1 now records that review, including per-owner contracts, 18 concrete findings,
regression anchors and a read-only AST coverage check. The initial family map below
remains a design reference; the linked register owns exhaustive surface coverage.

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

Current layout (configuration adoption is implemented; other domains follow):

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

### MVP10.2 implemented foundation

Public imports are explicit in `autoslurm.errors`: Diagnostic, DiagnosticCause,
DiagnosticError, diagnostic_catalog, invalid_argument, missing_resource and
command_failure. Root reexports remain unchanged. The core imports only stdlib
dataclasses/re/types/typing and performs no I/O or recovery. Normal package-root
import still eagerly loads older services; that separate import boundary is not
claimed fixed by isolated leaf-module tests.

Diagnostic has code, operation, stage, scalar identity/observation context,
optional cause, explicit step effects, summary/next-action overrides and up to four
leaf secondary diagnostics. Category/default wording have one catalogue owner.
Mappings and children are detached/immutable; enrichment refuses conflicting
identity. Effects are never inferred from codes, timeouts or errno. Cause captures
kind/detail/errno/returncode; original exceptions remain in native Python chains.
Known URL-userinfo/credential/key forms are redacted before UTF-8 bounding; unknown
secrets are not universally detectable, so raw config/environment/argv are excluded.

to_dict() returns detached version=1 diagnostic facts, not a new persisted record.
Summary/context strings are 512 bytes, next action 1024, detail 4096; numeric facts
are signed 64-bit and effect steps are bounded to 32. The existing receipt/update
payload is preserved by identity and referenced rather than serialized wholesale.
SubmissionError(message, receipt) and SoftwareUpdateError(message, evidence) still
behave as RuntimeError subclasses with the same messages/payloads/causes; optional
diagnostic= and the shared base are additive. Legacy errors have diagnostic=None.

apps.error_output supplies render_diagnostic and exit_with_error. The opt-in failure
adapter renders text to stderr or JSON to stdout, then exits 1. Its envelope is
status=error, message=summary, diagnostic=to_dict(). Existing parser usage exit 2
and observation/warning exit behavior remain command-owned. Unknown/legacy errors,
KeyboardInterrupt and debug=True re-raise the original exception; output failure
also re-raises the initiating error and keeps the write failure in __context__.
No global catch hook, ACP-envelope migration or new debug CLI flag was added.
Backends do not use the adapter. See the [installed recipe](../../src/autoslurm/agent_resources/15_diagnostics.md)
and [human guide](../../docs/errors.md) for exact fields and staged adoption.

### MVP10.3a implemented configuration boundary

`ConfigurationError` is exported from `autoslurm` and `autoslurm.errors`;
`configuration_failure` lives in the latter with the shared code/wording owner.
It uses existing configuration_invalid, resource_missing, resource_inaccessible
and record_invalid codes. The backend supplies actual config path, machine/field,
original cause and config_write=not_started for read/validation failures. It never
passes the raw document into diagnostics. JSON errors retain safe line/column;
Unicode errors explain UTF-8. Legacy lookup requires actual primary absence and
no explicit AUTOSLURM_STORAGE_ROOT; denied/corrupt primary files never fall back.

This is an explicit **dev exception-contract boundary**: configuration failures
formerly exposed as OSError/EnvironmentError, JSONDecodeError or missing-activation
AttributeError now raise ConfigurationError. ValueError validation compatibility
remains, as does RuntimeError/common DiagnosticError compatibility. Original
exceptions remain in __cause__; clients should catch ConfigurationError or
DiagnosticError. No saved format or historical record migration is introduced.

Config root/alias/standalone commands share stderr text/exit 1, parser exit 2 and
an explicit --debug that re-raises original chains. Unexpected programming errors
are not converted. Raw --view output remains JSON. The editor starts first-use
setup only after actual absence, preserving unreadable/corrupt/invalid files,
dangling links and entries that appeared during a failed read. This read guard
does not claim to solve publication races. Explicit root/profile edits and optional
existing post-save validation retain their behavior; tests mock validation.

MVP10.3b owns command/graph/manifest validation, snapshot/filter selection and
path preparation. MVP10.3c owns atomic publication/serialization/fsync/cleanup
diagnostics, record reads outside config and import-time storage-root validation.
The stale-venv executable check and external validation/probes remain MVP10.4.
No repair, alternate profile/environment, automatic retry or broad CLI/ACP
migration is added by configuration adoption.

### MVP10.3b.1 implemented authoring boundary

`InvalidRequestError`, exported at root and errors module, is a DiagnosticError/
RuntimeError and ValueError subclass. Its constructor accepts an explicit field,
stage, scalar context and optional DiagnosticCause/effects. It reuses invalid_argument
and the existing catalogue. `invalid_argument` now also accepts explicit cause/
effects; these remain caller facts. No new code catalogue, generic exception
translation, I/O or backend dependency is introduced in the shared error module.

Known CommandOption/CommandContract, literal compiler and Typer capability guards
use the type. Job construction and exact saved-job validation attach job/command
identity; no scientific callback executes and saved settings/defaults remain
explicit. Shell tokenization and missing optional imports retain native causes.
Graph validation checks container/job/name/dependency shapes and cycles at its own
public boundary; original CycleError and named cycle remain available. Historical
software-intent checks attach field/project/job; repository parsing has generic
safe diagnostic detail while retaining its original cause for debugging. It never
reintroduces runtime selection or deployment.

Save/schedule known input guards replace old TypeError/KeyError failures with this
explicit **dev exception-family boundary**. Missing/blank/nonstring commands now
fail before new publication. Empty draft saving remains supported. Existing
ValueError catches work; direct graph callers now receive InvalidRequestError
for cycles rather than waiting for consumer sorting. Original records/schemas and
readable argument/render styles are unchanged. Unexpected TypeError/KeyError/
ValueError code bugs, raw serialization/publication and external process failures
are not broadly converted. Invalid dependency scalars no longer pass as an empty list.

Pure/read-only functions make no blanket effect claim; early save/schedule
shape/command guards explicitly report bundle_write=not_started. Preview/submit
adds exact bundle/machine identity to adopted authoring failures before staging/
dispatch. Schedule root/standalone routes use shared stderr/exit 1 and an explicit
--autoslurm-debug, preserving application --debug forwarding. The submit CLI adopts
errors reaching preparation; its earlier broken-snapshot gate remains b.2 work.
Help-text discovery, arbitrary signature inference and broader CLI/ACP parity are
unchanged. Nested enrichment compares identities in their stored redacted/bounded
representation so repeated long identifiers do not mask the original failure;
genuinely different represented identity still raises a programming error.

MVP10.3b.2 covers snapshot/filter selection and per-entry broken/unavailable data;
MVP10.3b.3 covers pure paths/rendering. Local record reads/publication stay 3c;
external readiness/transport/software and stale-venv checks stay 10.4. Lower-level
bulk submission callback/accepted-ID mapping errors remain 10.5.

### MVP10.3b.2 implemented selection boundary

`SelectionError` (root/errors exports) and `selection_failure` (errors export)
use the existing catalogue. Expected invalid selectors, absent matches, inaccessible
paths/directories and malformed records have distinct codes, fields/paths, safe
causes and next actions. No effects, retry or repair are inferred. Native chains
remain available; unexpected code bugs propagate at the adopted boundaries.
Missing selections explicitly change from FileNotFoundError to SelectionError,
which retains ValueError/DiagnosticError compatibility. Name-based loaders inherit
this selection boundary; direct loader read errors remain with 3c.

One snapshot analysis now owns list/state interpretation and reuses dependency_graph
validation, replacing repeated validation and failure-to-empty branches. Read models
add state/diagnostic and explicitly allow unknown jobs/counts=None rather than
[]/zero. Healthy neighbours survive a broken/unavailable/missing entry; a valid
empty draft remains []/zero. Graph-invalid dictionaries retain observed names,
count and known ID count. These are discovery states, not scheduler outcomes.
This is an explicit dev **returned-data boundary**, with no persisted format,
historical record rewrite or migration. Raw documents never enter diagnostics.

Discovery no longer creates directories. Absent storage is empty; denied/invalid
directories fail visibly. Nonregular files are rejected; the POSIX reader checks
the opened descriptor and uses nonblocking open to avoid waiting on a replaced
FIFO. Exact/nearest filename selection stays payload-free and explicit external
files retain mtime fallback. Indices sort by timestamp with a deterministic filename
tie-break; references must be naive datetime values. Typed selector conflicts fail
before discovery. A newest failed entry blocks older-draft fallback and remains
visible beside submitted history. Unknown-count entries no longer qualify for
automatic stale/unsubmitted cleanup; explicit operator targets retain old policy.

Only absent configuration defaults filter reads to active. The config module
owns active/all validation; invalid stored/requested modes and unreadable/corrupt
profiles raise ConfigurationError without rewriting or silently changing indices.
Internal new/append snapshot fallback checks only selection resource_missing;
directory access failure never authorizes a new snapshot.

Filter/submit/status/inspect/logs CLI roots/standalone/aliases present adopted
selection/config errors through the shared adapter, exit 1 and --debug. Existing
status/inspect/logs JSON modes expose the same diagnostic; parser usage stays exit 2.
Submit uses strict snapshot validation before machine selection/connection. ACP
expected selection/config errors add diagnostic; list_bundles/list_runs and ACP
listings retain per-entry state/diagnostic. Broader observation/post-dispatch/ACP
bug policies are still later slices. Removing broad get-filter and submit-snapshot
catches leaves 16 broad handlers; receipt-saving safeguards remain untouched.

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
| MVP10.1 complete | Exhaustive public API/action/entry-point and broad-catch register; current effects/outcomes and recommended translation contracts; exact model decisions remain in MVP10.2 |
| MVP10.2 complete | Dedicated diagnostic module, isolated tests, opt-in terminal adapter and additive exception/JSON conventions; service/ACP-wide adoption pending |
| MVP10.3a complete | Config read/profile/selection validation, retained-file protection and config CLI aliases/standalone/debug |
| MVP10.3b.1 complete | Typed/raw authoring guards, graphs/software intent, bundle preparation and schedule CLI diagnostics |
| MVP10.3b.2 complete | Snapshot/filter selection and per-entry broken/unavailable evidence |
| MVP10.3b.3 | Pure paths/render preparation diagnostics |
| MVP10.3c | Record read/publication diagnostics, including config writes and pre/post-publication effects |
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

MVP10.2 supplies the implemented diagnostic fields/exports and opt-in debug/exit
conventions above. Settle each service's result/observation policy when adopting
it; existing CLI/ACP and helper protocol envelopes remain unchanged. Keep additive
fields where possible; an actual
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

2026-11-13, MVP10.1: completed source audit against `6104372`, including new typed
authoring exports, every explicit Python export/reexport, nine public methods,
all root/alias/software subaction/console/helper routes and eight ACP actions.
233 routes resolve to 112 owners with 24 inherited failure contracts; all 18 broad
handlers have individual reviews. E01–E18 identify translation and regression work,
while retaining existing receipt/accepted-ID safeguards. Read-only AST check and
four negative drift controls pass. Full offline suite: 761 passed, 43 expected
collision warnings, 10.53 s; `.development/test-runs/error-inventory.xml`.
Documentation links/diff reviewed. No package runtime, persisted-format, daily
state/config, environment, cluster or external-client change. MVP10.2 follows;
diagnostic adoption remains pending. Audit effort allowance is 7–13 focused days
for remaining model/adoption/parity work, with per-slice re-estimation and separate
deployment; it supersedes any narrow updater-only estimate.

2026-11-13, MVP10.2: implemented the foundation, 17 catalogue codes, named fact
constructors, detached/bounded/redacted serialization, immutable identity/effects,
secondary diagnostics and opt-in terminal/JSON/debug behavior. Existing domain
exception positional messages/payloads/causes retained with optional diagnostic=.
36 focused tests pass; full offline suite 797 passed, 43 expected collision warnings,
10.62 s; `.development/test-runs/error-core.xml`. Clean-source wheel smoke verifies
API, legacy payloads, JSON and installed recipe/CLI/ACP without Typer; artifact
SHA256 `f6734a18963e0f64b64cd4c0365bcd0ba1572e96bae795e80402f939e53ae2cc`.
Coverage register expanded to 248 routes/127 owners with foundation tests; all
18 existing broad catches retained. Human/agent guides and relative links reviewed.
No cluster contact, base install, daily state/config or persisted-format change;
domain operation translation, stale-venv fix and universal presentation are pending.
MVP10.3 configuration/authoring/persistence adoption is next.

2026-11-13, MVP10.3a: split MVP10.3 before implementation; completed configuration
read/profile/selection validation with shared codes/causes/context and the config
CLI/alias/standalone/debug policy. Preserved unreadable/corrupt/invalid existing
files and actual legacy source paths. Explicit ConfigurationError boundary is
documented for Python clients; ValueError compatibility and original causes remain.
Full offline suite: 851 passed, 43 expected collision warnings, 9.87 s;
`.development/test-runs/configuration-diagnostics.xml`. Clean-source offline wheel/
temporary-target API/config routes/debug/retained-file/installed-recipe smoke
passed; SHA256 `0c3529f9e3af49e3b0674a611af7878a26c4568d7b3476419e75eb363b43e3de`.
AST register matches 251 routes/129 owners/18 retained broad catches. No base
install, daily state/config, cluster, external client, persisted-format or rollback
change. Publication effects and general authoring/selection/path diagnostics stay
open in MVP10.3b/c; stale-venv remains MVP10.4.

2026-11-14, MVP10.3b.1: split b before implementation, then adopted authoring
guards with InvalidRequestError, field/option/job/project/native-cause context,
unchanged readable settings and exact bundle/machine identity. Graph cycles and
malformed jobs now diagnose at their owner; known save guards stop publication.
Schedule CLI/root/standalone uses shared stderr/exit 1 and --autoslurm-debug;
unexpected bugs remain visible. 54 new contract cases; full offline suite 905
passed, 43 expected collision warnings, 11.45 s;
`.development/test-runs/authoring-diagnostics.xml`. Clean-source offline wheel/
temporary-target API/graph/retained-record/root/standalone/debug/optional-Typer/
installed-recipe smoke passed, SHA256
`5d8685e83105132dc763100306945e286444d796a020738296adba27e5fa0187`.
AST register matches 253 routes/130 owners/18 retained broad catches. No actual
cluster commands, daily state/config, dependency installation, saved-format,
external-client or rollback changes. Snapshot selection b.2 is next; b.3 paths/
rendering, 3c publication and 10.4 stale-venv remain open.

2026-11-14, MVP10.3b.2: implemented shared snapshot analysis, typed selectors,
strict submit record gate, absence-only filter default, per-entry diagnostics and
unknown counts, no older-draft fallback after newer failure, stable index tie-breaks
and unknown-count cleanup protection. Root/standalone/alias CLI text/JSON/debug
and ACP discovery retain adopted facts; two masking catches removed. 60 new
regressions; 965 full offline tests passed in 10.00 s, 43 expected collision
warnings; `.development/test-runs/selection-diagnostics.xml`. Clean-source offline
wheel/temporary-target discovery/selection/retained-record/CLI/JSON/debug/ACP/
installed-recipe smoke passed; SHA256
`b0b224f02f50fa2154b2f50349297e0263ff691e1e3d98ac73259d46cf2202cc`.
AST register: 256 routes/132 owners/16 remaining broad catches. Human/agent docs
and installation register updated; no actual cluster commands, base dependency
installation, daily config/state, persisted-format, external client or rollback
changes. b.3 paths/rendering is next; other domain/observation adoption remains open.
