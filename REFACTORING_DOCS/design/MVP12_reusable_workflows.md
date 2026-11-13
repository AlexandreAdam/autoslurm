# MVP12 Reusable scientific workflow services

## Status

Requested by Alexandre on 2026-11-13 after supplying the
[Gaia workflow proposal](../proposal-generic-workflow-from-gaia.md). **Planned,
not implemented.** The requirement is to reimplement reusable behavior in
AutoSlurm, expose supported APIs and make the features discoverable to humans
and agents in everyday work. Specific names, storage formats and orchestration
defaults in the proposal remain proposals. [PLAN.md](../../PLAN.md#mvp12-reusable-scientific-workflow-services)
owns the independently deliverable slices.

The source reference is Gaia `8eaffec67a683bcff9c72363aaf7f8f740564b1a`.
Planning inspected the proposal and representative bundle/command/registry/run
code read-only. This is not a complete porting audit or verification of the
proposal's line-count estimate. Do not copy the entire workflow implementation.

## Problems and ownership

Clients currently rebuild resource summaries, review/confirmation, run grouping,
retry selection and task execution glue. That spreads policy and leaves agents
dependent on client-private files. AutoSlurm already owns most underlying
scheduler, transport, graph, path, receipt, software-update and log operations.
New services must compose those owners rather than create a second engine.

| Proposal area | Existing owner / planned treatment |
|---|---|
| Named typed arguments and rendering | MVP9; share its contracts and compiler |
| Consistent failure diagnostics | MVP10; new services join its audit/contracts |
| Status, array inspection and log tails | Reuse inspection/MVP8/FIX.LOGS.1; waiting explanations belong to MVP11 |
| Git pull, editable install, module setup | Reuse MVP7 and completed FIX.SOFTWARE.1; do not reimplement those fixes |
| Resource view, offline plan, review flow | New submit-side services in MVP12.1–3 |
| Named run grouping, retry plan | New services over existing bundles/receipts in MVP12.4/6 |
| Dependency-change check/update evidence | Extend existing software service in MVP12.5 |
| Task registry, markers and provenance | Optional node-side layer, MVP12.7–8 |
| Scientific pipelines, studies, GPU readiness, figures and layout | Stay client-owned |
| Filtered scientific-result retrieval | Separate decision gate; current logs-only scope remains |

## Decisions and proposed service contracts

- **W12.1 Requested:** reuse proven generic workflows through public APIs,
  accurate documentation and discoverable agent capabilities. An internal module
  alone does not finish a feature.
- **W12.2 Proposed:** deliver submit-side conveniences first, one usable slice
  at a time. Keep the optional compute-side runtime independently importable.
  Do not require adopting a workflow framework to submit an ordinary command.
- **W12.3 Required:** application paths stay relative; machine profiles own
  software/results roots. Preserve existing receipt safety and unknown outcomes.
  No network preparation in compute jobs or hidden remote work during planning.
- **W12.4 Proposed:** provide an explicit higher-level review/prepare/submit
  workflow while retaining low-level service boundaries. Existing `submit_jobs`
  does not silently acquire a Git pull, prompt or dependency installation.

The following are capability sketches, **not available imports or commands**.
Settle exact names at each slice and publish them only with working behavior.

### Resource summary and offline planning (MVP12.1–2)

A pure resource view accepts a validated bundle and returns plain rows/totals:
job names, original array cardinality and concurrency cap, partition/constraint,
GPU/CPU/memory/walltime requests and dependencies. A formatter/CLI consumes it.
Reuse shared array/time/resource interpretation; Gaia's helper functions are
examples, not an additional parser to copy. Account for task count, CPUs per
task and supported GPU request forms. Unsupported/default resources remain
unknown; label partial totals. Requested allocation-hours are upper bounds from
specified walltimes, not predicted usage or queue-time estimates. Array caps
limit concurrency, not the total requested work.

Offline planning may read selected local configuration and records, validate
arguments/graph and save a logical bundle plus context. It must perform no
SSH, rsync, scp, Git fetch or remote path/environment discovery. An unresolved
remote root or unchecked input is recorded as unresolved/not checked; readiness
is a later explicit action. Reuse the existing resolver's policy without calling
its remote-discovery path. Show exactly what is known in an offline preview.

### Review before effects (MVP12.3)

The human workflow presents purpose/context, selected machine, named arguments,
resources and intended software action, then obtains confirmation before any
pull, remote staging or submission. Declining has no remote or submission-record
effects. Define any local planning writes explicitly. Non-interactive execution
requires an explicit supported authorization flag or caller decision; a prompt
must never hang an agent. A confirmation hook belongs at the orchestration
boundary; pure services neither print nor prompt. The Gaia recipe's human-only
submission policy must be respected by that integration, without inventing a
new global authorization system for every existing AutoSlurm API.

Context can be a Markdown sidecar linked to an exact saved bundle; publication,
missing-context and retention semantics must be defined. Resource caps/force
overrides and new submit defaults need a separate decision before adoption.

### Run grouping and durable handoff (MVP12.4)

A named run groups exact planned bundle references, context/resource view,
submission attempts/labels/receipt references, software evidence and warnings.
Extend current listing/discovery and experiment context. Receipts remain the
owner of submission outcomes; do not duplicate mutable scheduler truth in a
new run index. Record links and original machine/path evidence so a changed
profile cannot redirect a historical run. Relative record-file paths have an
explicit run-folder base.

Before adding persisted data, agree a small record/release boundary, atomic
publication, name collisions, retention and compatibility with existing records.
Use temporary fixtures; no migration of daily records or new database is implied.
A fresh agent must rediscover a run through supported listing/load APIs.

### Explicit software preparation (MVP12.5)

Compose the existing single-checkout updater and editable `--no-deps` install.
Show bounded local dirty/unpushed warnings when a local source mapping is known;
do not assume every project tracks `main`. Record planned, before and observed
after revisions without claiming a shared mutable checkout is frozen.

Compare normalized declared runtime dependencies before/after the selected
update. If they change, stop before editable installation/submission and explain
what changed and what preparation is required. If the pull already happened,
record that effect; do not claim nothing changed or automatically roll it back.
Identical hashes do not establish that installed dependencies satisfy them;
reuse existing major-dependency/environment checks. Decide extras, markers,
non-pyproject projects and acknowledgement/resume semantics before coding.
Machine-owned scientific packages remain operator-managed. Build isolation and
setup-before-activation are already fixed, not new completion items here.

### Explicit retry planning (MVP12.6)

A pure planner uses exact bundle/attempt observations to select confirmed failed
or never-submitted work and affected downstream stages. Preserve original sparse
array indices. Drop satisfied upstream edges only with adequate evidence for
their actual dependency conditions. Running, pending, stale/unknown or uncertain
acceptances are not automatically retried. A pending impossible dependency needs
explicit treatment, not classification as safely never run.

Return a readable proposed bundle and reasons/lineage, or a clear no-work or
unsafe-to-plan result. Validate the graph and original index/count semantics.
Client checks must establish whether prior outputs/checkpoints are reusable,
especially after code/input changes. Scheduler COMPLETED alone proves no
scientific validity. Review and explicit submission use existing receipts; no
automatic resubmission loop, replacement of live reducers or hidden deletion.

### Optional task runtime and bridge (MVP12.7–8)

First prove the contract with Gaia-shaped and independent second-client fixtures.
The plain runtime is scheduler-free and imports without CLI/scientific/backend
dependencies; optional Typer/JAX integrations are lazy and separate. Today's
`autoslurm.__init__` eagerly imports submit-side modules: adding `autoslurm.tasks`
alone does not meet this boundary. Resolve packaging/lazy import ownership or
a sibling distribution explicitly, with import-denial artifact tests.

Potential reusable behavior includes validated Run/Stage data, typed registry,
per-index execution, atomic completion markers, code/dependency/timing evidence
and reducer missing-index checks. Reuse MVP9's option semantics rather than
creating a competing validator/CLI generator. A submit-side bridge converts
plain run data into existing readable named-argument bundles. Science remains
ordinary client functions; no encoded run/config payload in `script_args`.

Hash and marker contracts must specify inputs/code identity, changed options,
output readiness, mismatched partial results and concurrent/repeated execution.
A marker alone cannot guarantee scientific idempotence or intact large outputs.
Keep metadata reads bounded; no recursive dataset scans. Generic gather/echo and
failure fixtures can demonstrate the boundary. JAX timing/device metrics are
optional follow-up, not a core runtime dependency or universal GPU readiness test.

## Public adoption gate for every slice

Each slice delivers these items together, not as a late documentation task:

1. A supported Python contract, intentional exports, plain outcomes/evidence,
   effect/failure semantics and tests through the public route.
2. CLI help/examples and structured output for operational capabilities; expose
   equivalent ACP actions/context where appropriate, or explicitly document the
   supported Python/CLI route and ACP limits. No private module/file knowledge.
3. Version-matched agent recipe discoverable through existing context selection:
   inputs, local/remote effects, outcomes, freshness, failures and safe next action.
4. Human purpose/system-map/example material showing what can be reviewed and
   delegated; update the reference client and public capability inventory.
5. Offline behavioral checks, including no-contact planning and preserved
   partial/uncertain receipts; a narrow wheel smoke verifies public imports and
   included guidance for the added capability outside the source tree.

MVP12.9 checks the combined workflow and removes documentation gaps; it does not
defer public exposure until the whole milestone finishes. Migrate a real client
only in an explicitly scoped adoption task after replacements pass; do not edit
Gaia or delete its working implementations during AutoSlurm planning.

## Open questions and deferred extensions

- Result fetching conflicts with the earlier explicit logs-only boundary. Keep
  application-owned scientific retrieval until a separate scope decision defines
  exact selections, transfer limits, preview and evidence. No generic subtree
  mirror or recursive dataset discovery is authorized by this plan.
- Final API names, persisted run/context format, preparation policy and runtime
  packaging require decisions at their corresponding slices. None is accepted
  merely because the Gaia proposal provides an example signature.
- The node-side proof follows submit-side services and a second-client use case;
  it may ship independently. This broad milestone is not a short single task.

## Forward constraints and checks

Use cheap local science plus mocked SSH/Slurm and temporary repositories. Cover
unknown/partial resource totals, no-contact plans, decline-before-update,
dependency changes after pull, restart/rediscovery, mixed failed/unknown arrays,
code/output incompatibility and runtime import isolation. Keep original records
and the pinned rollback untouched. Audit actual Gaia code/tests before each
port; preserve current AutoSlurm behavior outside the chosen public boundary.

## Log

- 2026-11-13, PLAN.3: preserved the supplied proposal, mapped overlaps and scoped
  independently deliverable services with a per-slice API/discovery/docs gate.
  No public capability, runtime, stored data or external client changed.
