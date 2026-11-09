> Archived 2026-11-09. Superseded by the [MVP plan](../../PLAN.md).
> Retained for the original task IDs and full-scope design history; this is not an active task list.

# AutoSlurm refactor plan

Living roadmap for making AutoSlurm a dependable engine for scientific jobs,
operated from a workstation by an agent or from the terminal. This file is the
source of truth for task order, progress, and accepted decisions. Milestone
design documents explain the reasoning and unresolved choices.

## Status

- **Current milestone:** M0, interaction mapping and regression coverage.
- **Stage:** interaction map and agent documentation design drafted for review;
  implementation has not started.
- **Next task:** M0.0b, review the interaction map and client integration guidance
  together with human documentation and installation requirements, before
  choosing backend contracts.
- **Last updated:** 2026-11-09.

## Goals

1. **One engine for both interfaces.** Terminal commands and agent requests use
   the same validation, selection rules, operations, and resolved records.
2. **Submission that accounts for failure.** Preserve successful submissions
   when a later job fails; distinguish rejection from an uncertain outcome;
   never blindly resubmit after losing a response.
3. **Useful local inspection.** After an explicit refresh, inspect saved status,
   array tasks, scripts, and logs offline, with observation time and incomplete
   information visible.
4. **Clear ownership.** Separate job definitions, submission attempts, scheduler
   observations, artifacts, external commands, and presentation.
5. **Reproducible scientific work.** Record requested and observed application
   versions, support per-job environment variables, and retrieve selected
   results. Compute nodes need no internet for AutoSlurm operations.
6. **A manageable refactor.** Keep AutoSlurm's bundle workflow and implementation;
   replace one working slice at a time, with behavior checks and small commits.
7. **Client integration as part of the interface.** Teach an agent developing
   scientific software how to make it portable, observable, and recoverable with
   AutoSlurm, then let a fresh session track every run without private APIs or
   remembered chat context.
8. **Installable and understandable.** Deliver a tested pip-installable
   distribution and human documentation explaining what the package does, why,
   and how its main workflows fit together, with checked examples. The engine's
   supported programmatic interface serves agents; private internals are not a
   public integration contract.

## Scope and constraints

- Agents remain on the workstation. A small remote helper may run through SSH
  on the login node; compute jobs execute already-prepared code and environments.
- Keep existing public commands, aliases, and readable bundle files during
  migration, except for explicitly agreed corrections to defective behavior.
- Keep cluster access behind narrow adapters. A new dependency must remove a
  meaningful responsibility; PySQA is not part of the proposed implementation.
- Package updates remain explicit and manual initially. Record and verify code
  versions without building an automatic deployment system.
- Do not change a shared checkout or environment from an individual job.
- Client application configuration and workload definitions use relative paths.
  AutoSlurm owns discovery of machine-specific roots and execution path
  resolution; applications do not branch on hostname or embed workstation/HPC
  absolute prefixes. The base of each relative path is explicit, never the
  agent's incidental current directory.
- Each application run/bundle targets exactly one selected machine. Existing
  named machine profiles remain useful for selecting that machine; routing a
  run across machines is outside this refactor.
- Keep runtime storage independent of the package installation location in the
  new design, with migration from the current layout defined before changing it.
- Preserve existing user configuration, bundles, and logs. Tests use temporary
  storage and fake external commands; real cluster validation is a distinct step.
- The Gaia requirements are client evidence, not a reason to put study-specific
  logic in AutoSlurm. See [the requirements](../requirements-gaia-asteroseismology.md).

## Architectural direction

Start with [the interaction map](../interaction-map.md) and
[the agent documentation design](../agent-documentation-design.md).
Use [the human documentation and distribution design](../documentation-and-distribution-design.md)
for audience boundaries, installability, and release acceptance.
Review their outcomes, evidence, and failure semantics before defining backend
contracts. Derive the implementation order from the dependencies between these
interactions. Exact types, file layouts, and module names remain unsettled;
the responsibilities below are provisional until checked against the map.

| Responsibility | Owns |
|---|---|
| Bundle definitions | Commands, arguments, resources, environment, dependencies, requested code revision |
| Run records | Stable run identity, target machine, attempts, accepted Slurm IDs, submission receipts, observed code revision |
| Observations | Scheduler state, array tasks, logical/raw IDs, query source, observation time, refresh failures |
| Artifacts | Scripts, logs, declared result paths, local/remote locations, retrieval state |
| Adapters | SSH, Slurm commands, file transfer, environment inspection |
| Services | Scheduling, submission, reconciliation, refresh, cancellation, cleanup |
| Interfaces | Human-readable CLI output and structured agent responses |

The local index stores collected observations; Slurm determines scheduler state.
Cached state always has an age. Missing accounting, a failed query, and a job
that has not been submitted are different conditions.

Dependency direction: data and pure policy first; adapters and persistence use
those contracts; services coordinate them; CLI and agent interfaces call services.
Core code does not import CLI code. Avoid a new catch-all utilities module.

## Milestones

Only the current milestone is planned in detail. Before starting the next one,
open its design document and split its scope into tasks with completion criteria.
Task IDs remain stable; split oversized tasks with letter suffixes.

### M0 Interaction mapping and regression coverage

Design: [M0 baseline](../design/M0_baseline.md).

- [x] **M0.0 Establish the planning workflow.** *Done when:* PLAN.md, agent
  guidance, the design index, and the M0 proposal exist; existing refactor docs
  point to the same task order. Documentation only.
- [x] **M0.0a Draft the interaction map and agent documentation design.** *Done
  when:* the map covers application integration through submission, recovery,
  monitoring, diagnosis, results, and context handoff; each interaction states
  ownership, inputs, outcomes, durable evidence, and failure behavior; the
  documentation design includes client software practices and a current-docs
  audit; human documentation and pip distribution have explicit acceptance
  criteria. These are drafts, not accepted public schemas.
- [ ] **M0.0b Review the interactions before architecture.** *Done when:* the
  user has reviewed I00-I16, the client integration practices, human reading
  path, installation requirements and documentation coverage; omissions and
  priorities are recorded; each interaction maps to a
  milestone, a recipe, and a validation trace. Amend the proposed milestone
  order if the interaction dependencies require it. No backend rewrite starts
  before this review.
- [ ] **M0.1 Review the M0 design.** *Done when:* decisions D1-D7 are accepted
  or amended with the user, blocking questions are resolved, and the Decisions
  log records the outcome.
- [ ] **M0.2 Establish the executable baseline.** *Done when:* unit and existing
  integration tests have recorded results in a documented development
  environment; dependency, Python-version, and CI discrepancies are identified;
  tests cannot write production storage or contact the cluster unexpectedly.
  Inspect packaging, installed documentation resources, runtime paths and the
  current human documentation build; record gaps against I00 without assuming
  an editable install proves release readiness.
  Existing failures are recorded individually, not described as passing.
- [ ] **M0.3 Add representative workflow fixtures.** *Done when:* plain-data
  fixtures cover a single job, a dependency graph, an array with mixed outcomes,
  and repeated snapshots; tests exercise bundle selection, submission ordering,
  and status/log identity without depending on old helper names. Include a
  minimal client integration example and a new-session rediscovery scenario
  derived from the reviewed interactions.
- [ ] **M0.4 Specify the known failure cases.** *Done when:* regression cases
  cover partial submission, lost responses, malformed remote replies, growing
  logs, missing accounting, and logical/raw array IDs. Confirmed defects are
  recorded as strict expected failures with a destination milestone; unproven
  reports remain investigation items. No defects are silently frozen as desired
  behavior.

M0 closes with a reproducible offline baseline and explicit exceptions. It does
not require fixing every defect or connecting to a real cluster. Its reviewed
interaction map and documentation requirements constrain all later milestones.

### M1 Bundle and run contracts

Scope: define the canonical objects, versioned persistence, and their ownership;
implement bundle validation/selection and run storage as the first slice.

The design must settle stable IDs independent of display indices/timestamps;
definition versus attempt history; machine-scoped scheduler identity; atomic
writes and concurrent access; storage-root configuration; legacy JSON import;
and safe handling of unknown schema versions. Define the
[application path contract](../target-architecture.md#application-path-contract):
declared relative path fields and their bases, selected-machine root discovery,
working directory, missing-root errors, and treatment of legacy absolute paths.
Use one resolution policy across preview, execution and artifact retrieval;
do not infer path fields from arbitrary strings. Prefer the simplest storage that
meets these requirements; no database choice is assumed. Start from I02/I04/I08:
show what a client supplies and how another session locates the resulting run.

*Done when:* scheduling and selecting bundles use the new contracts through an
active interface; old fixtures load without loss; writes survive the agreed
failure scenarios; new core code does not depend on legacy implementations.
The supported client contract has a matching integration recipe and example.
Storage and packaged-resource contracts support wheel installation outside a
checkout, with no writes into the installation directory.
The same relative application definition resolves against two different machine
profiles in separate test runs without edits to client code or the definition;
each run still uses one machine. Persist logical and resolved paths separately.

### M2 Reliable submission and execution metadata

Scope: render scripts from validated definitions, including per-job environment
variables; submit locally or through the remote helper; record attempt outcomes
and application provenance through the same service.

The design must settle literal arguments versus explicitly requested Slurm
variable expansion; dependency handling in every submission path; incremental
durable receipts; client/helper protocol compatibility; transport failure before
and after acceptance; and reconciliation before retrying an uncertain submission.
Do not promise exactly-once execution across an unobservable scheduler outcome.

Provenance starts with requested revision, observed installed revision/version,
dirty or unknown status, and environment identity. Define mismatch handling and
what can be verified at submission and job startup. Version checks cannot
freeze a mutable installation; report that limit and leave package preparation
manual. Non-Git installations have an explicit unknown or alternative identity.

*Done when:* the active local and remote paths preserve every known accepted job
ID on partial failure, block unsafe automatic retries, apply dependencies before
submission, render environment/arguments correctly, and preserve provenance
without requiring compute-node internet. Relevant M0 failure cases pass.
I03/I05-I07 and submission diagnostics from I11 have public response contracts
and recipes at this stage; structured outcomes are not deferred to M4.
Execution paths match the validated preview for the selected machine, and no
application-specific root mapping is reimplemented in the submission renderer.

### M3 Refresh and local inspection

Scope: make explicit refresh collect scheduler observations and transfer
artifacts; build one local index for status, array-task identity, and log lookup;
add filtered retrieval of declared scientific results.

The design must settle refresh ownership when both workstation and remote helper
hold metadata, observation precedence, polling batches, retained terminal states,
partial refresh, growing/rotated logs, custom output paths, and result include/
exclude filters. Immutable records and mutable files need different transfer
rules. Log presence alone does not establish job success.

*Done when:* an offline reader reproduces the last refreshed single-job and
array view; status and logs share the same task mapping; refresh failures retain
prior observations with warnings and timestamps; growing logs update; selected
results transfer without pulling excluded partial files. Cached inspection does
not initiate network calls implicitly.
Locate artifacts using the recorded machine/path resolution for their producing
attempt, not today's default machine or a newly changed machine root.
I08-I12 and I16 share evidence and bounded context suitable for an agent that
has lost its previous session. Document the difference between a known scheduler
reason, an inferred cause, and an unavailable observation.

### M4 Terminal and agent interfaces

Scope: route terminal and agent operations through the shared services; provide
stable structured responses and concise human output; move cancel, clean, and
filter onto the canonical records.

The design must settle stable selectors, explicit refresh behavior, error codes,
partial-success responses, bounded log retrieval, and how old ACP actions map
to the service interface. Keep destructive actions based on explicit policy;
stale or unknown state is not sufficient evidence to delete an active run.

*Done when:* both interfaces agree on selected run, task states, artifacts, and
errors; existing public commands remain usable; cleanup previews explain their
selection; installed agent recipes, capability discovery, public schemas, and
examples agree. Verify documentation retrieval outside a source checkout.
Consider terminal watch mode here if the shared refresh service is ready.
The human guide presents purpose, a high-level system map, agent collaboration,
complete examples, and interpretation of failures; detailed internal architecture
stays in contributor docs. Routine terminal operation remains possible without
an agent. Follow the reviewed documentation design rather than turning the main
guide into a private API inventory.

M4 consolidates the interfaces and documentation delivery. It does not postpone
agent usability until late in the refactor: each earlier slice includes its
supported recipe, response contract, and reference-client behavior checks.

### M5 Scientific retries and cluster validation

Scope: add failed-array-task retries with attempt lineage, define downstream
reduce behavior, and provide a small map/reduce convenience API using the same
existing array/dependency primitives.

*Done when:* only selected failed tasks are retried; output ownership and
downstream dependencies are correct across original and retry attempts; a
representative array/reduce workflow is validated on a configured cluster,
including provenance, cancellation, refresh, and selected result retrieval.
Record the real validation separately from emulated tests. Move replaced code
to legacy under the existing policy and document remaining compatibility paths.
The client integration example demonstrates retry/output ownership and can be
continued by a new agent using only saved run references and installed guidance.

### M6 Distribution and documentation release

Scope: verify the combined release as an installable product. Build wheel and
source archives, test installation outside the checkout on supported versions,
and provide a versioned, reproducibly built human documentation site.

The design must settle package index/name ownership, versioning, required and
optional dependencies, included package resources, client/helper compatibility,
upgrade/migration checks, release automation and publication. Reuse existing
documentation tooling unless the reviewed human reading path needs a change.

*Done when:* isolated artifact-install checks pass for entry points, installed
agent guidance and a local reference workflow; runtime state is writable outside
the installation; package contents exclude runtime/private artifacts; the human
guide and examples match the supported version; old tracking history survives
the agreed upgrade path; release artifacts and publication instructions are
ready. Public package/docs publication is recorded separately and performed
through the agreed release workflow, not as part of this planning task.

Installability and both documentation audiences constrain earlier milestones.
M6 is the combined release check, not the start of packaging or documentation.

### Interaction coverage

This is the draft traceability map for M0.0b review. Every interaction also
requires its recipe in the agent documentation design and a behavior check.

| Interaction | Implementation milestone | Validation traces |
|---|---|---|
| I00 Install and understand | M1 storage/resource contracts; M4 guides; M6 artifact install and release | T11 |
| I01 Capabilities and task context | Public contract begins in M1; installed delivery consolidated in M4 | T01, T10 |
| I02 Adapt client software | M0 reference case; contract in M1, environment support in M2 | T01, T13 |
| I03 Machine readiness | M1 path contract, M2 remote readiness | T01, T08, T13 |
| I04 Define workload | M1 | T01, T03, T13 |
| I05 Validate and preview | M1 validation, M2 execution preview | T01, T08, T13 |
| I06 Submit | M2 | T01-T03 |
| I07 Reconcile interruption | M2 | T02, T03 |
| I08 Rediscover runs | M1 identity/lookup, M3 observations | T05, T10 |
| I09 Refresh | M3 | T04-T07 |
| I10 Inspect task | M3 | T04-T07, T10 |
| I11 Diagnose | M2 submission evidence, M3 execution evidence | T02-T04, T06-T08, T10 |
| I12 Retrieve results | M3 | T07, T13 |
| I13 Cancel | M4 | T09 |
| I14 Retry and downstream recovery | M5 | T03, T04 |
| I15 Retain and clean | M4 | T12 |
| I16 Context handoff | M1 stable references, M3 evidence, M4 delivery | T05, T10 |

## Decisions log

Only user-agreed decisions belong here. Proposed technical decisions live in the
current milestone design until reviewed.

| Date | Decision | Reason |
|---|---|---|
| 2026-11-09 | Follow the Gaia planning workflow: living plan, milestone designs, small sequential tasks, completion criteria, and progress logs | Keep the refactor reviewable across sessions |
| 2026-11-09 | Retain AutoSlurm's implementation and customizable bundle workflow; do not adopt PySQA as the refactor backend | Replacing the queue adapter would leave the central workflow responsibilities with AutoSlurm |
| 2026-11-09 | Compute nodes perform no Git/network-based package preparation; package updates stay explicit and manual initially | Match cluster restrictions and limit refactor scope |
| 2026-11-09 | Map high-level interactions before backend redesign; redesign installed agent docs to teach both client software integration and reliable operation | Agents need enough durable context to build compatible clients, track submissions, and explain failures across sessions |
| 2026-11-09 | Make pip distribution and human documentation explicit deliverables; teach purpose, system map, examples and agent collaboration in the human guide, with detailed integration contracts in agent guidance | People need understanding and supervision; agents need precise operational contracts; both use the same supported engine |
| 2026-11-09 | Applications declare relative paths; AutoSlurm discovers and resolves roots for one selected machine per run/bundle | Remove machine-specific path assumptions from client software; multi-machine routing remains outside the refactor |

## Done log

| Date | Task | Validation and commit reference |
|---|---|---|
| 2026-11-09 | M0.0 Planning workflow and initial milestone proposal | Documentation review and local-link checks; commit reference: `git log --grep '^M0.0:'` once committed |
| 2026-11-09 | M0.0a Interaction map, client integration practices, agent documentation audit/design, human guide and pip distribution requirements | Documentation and traceability checks; draft review remains M0.0b; commit reference: `git log --grep '^M0.0a:'` once committed |

## Parking lot

- Automatic package preparation, revision-specific installations, and cleanup.
- Optional locked environments or Apptainer images, subject to cluster support.
- A single bundle routed across multiple machines.
- A persistent monitoring service, web dashboard, or dedicated agent server.
- Package renaming or replacing the workflow engine with another platform.
- Changes to scientific algorithms, study-specific policies, and result formats.

## How we work

### Per task

1. Read Status, the first unchecked task in the current milestone, and its design
   document. Settle decisions that block that task; routine implementation within
   accepted decisions proceeds without a new approval round.
2. Split work larger than about a day into reviewable tasks before implementing.
3. Implement one task. Keep mechanical moves and behavior changes separate.
   Preserve AutoSlurm's legacy policy rather than copying Gaia's deletion policy.
   Link new service contracts to the reviewed interactions and update their
   client/agent recipe and reference example as supported behavior changes.
4. Run focused behavior checks and the fast suite. Run the full offline suite
   for changes to shared contracts, submission, refresh, or compatibility. Fix
   regressions; record pre-existing failures and strict expected failures
   explicitly. Do not silently weaken assertions to make a move pass.
5. Update the task checkbox, Status, Done log, and any affected design decisions
   together. A task with an unmet completion criterion remains unchecked.
6. Keep code, tests, and planning updates in the same small task commit, prefixed
   with its ID, such as `M2.1: persist submission receipts`. Follow the Gaia
   workflow of commits on `main`, unless the user requests a branch. Preserve
   unrelated working-tree changes. Push task commits during an implementation
   session using the configured remote; do not force-push.

### Checks

- Development install: `python -m pip install -e '.[test]'`.
- Fast suite: `python -m pytest -q tests/unit`.
- Full offline suite: `python -m pytest -q tests` after M0.2 verifies isolation.
- Documentation-only tasks: inspect the diff and check relative links; no
  application tests are required unless behavior or configuration changes.
- M0.2 records actual environment and baseline results. Existing CI is not
  assumed to prove support for every Python version declared in packaging.
- Add focused tests for behavior and failure boundaries; avoid tests that merely
  reproduce implementation details. No blanket test requirement for trivial
  helpers or reversible documentation edits.

### Design documents and milestone boundaries

- One living design document per milestone, with Status, Problems, Decisions,
  Open questions, Forward constraints, and Log.
- Propose decisions before implementing them. Record user agreement before
  treating a public contract or migration decision as accepted.
- Amend designs when evidence changes the plan. Keep later milestones broad
  until their dependencies are understood.
- At closure, record validation, mark the design done, create a collision-free
  milestone tag such as `refactor-m0`, and push it during the implementation
  workflow. Never overwrite an existing tag.
- Open the next design and detail its tasks before starting its code. Report
  any deferred completion criteria explicitly.
