# MVP11 Readable dependency-aware status

## Status

Requested by Alexandre on 2026-11-13; MVP11.0 interaction map complete on
2026-11-27. MVP11.1a is implemented in 0.2.0.dev17; remaining broader gates
stay planned. The requested
outcome is a reason column in the normal job table, with understandable waiting
categories and dependency job names. Contracts and module names below are
proposed. [PLAN.md](../../PLAN.md#mvp11-readable-dependency-aware-status) owns
delivery order and task completion.

Alexandre expanded the scope on 2026-11-16: refactor the status workflow and
implementation substantially, beyond adding a reason column. MVP11.0 first maps
the interface and responsibility boundaries; MVP11.1–3 deliver interpretation and
layout, then MVP11.4 consolidates adoption and verifies performance/consistency.
This is a planning amendment; MVP10 diagnostic implementation continues first.

## Broader refactor direction

The current inspection layer already separates collection, pure state projection,
caches and artifacts. Reuse it. Remaining status paths mix concerns: status_views
contains convenience functions that load bundles or obtain observations, the CLI
reloads definitions after inspection to build rows, and status.py combines public
convenience/compatibility queries with ANSI formatting and state display. Map
actual callers before extracting or retiring any path. Keep mechanical extractions
separate from new semantics; avoid a parallel read model or scheduler engine.

Proposed everyday interaction:

- Overview: runs needing attention and active work, machine, job/task progress,
  last observation and whether it is stale/unavailable; define filters and default
  history scope explicitly rather than silently scanning every artifact.
- Run detail: stable job indices/names, scheduler state, clear array counts,
  dependency waits, relevant resource/time fields and significant failure evidence.
- Task detail: original array index/ID, full reason/exit/source/freshness and a
  direct supported transition to the same task in logs/fetch.

Submission acceptance, observed scheduler state and application/scientific success
are separate concepts. Unknown observations cannot become finished/failed jobs.
Mixed arrays must expose counts rather than hide pending or failed tasks behind
one aggregate label. Structured output and human output use the same observations.
Plain text/non-TTY output must be useful; compact/wide tables should have explicit
column priorities, without relying on a full-screen terminal to prevent wrapping.

MVP11.0 will settle examples and the supported filters before implementation.
Track exact file/query costs and reuse batched machine observations. Cached status
must not discover hosts, read source logs or contact Slurm. One failing machine or
record must preserve the rest of the view, with usable evidence and visible errors.
Preserve status/log/fetch index semantics and exact receipt/attempt identity on
both workstation and cluster. Assess existing cache compatibility before adding
stored explanation fields. MVP10.6 owns diagnostic translation for observations;
MVP11 consumes that contract. A watch service, queue ETA, automatic retry and
scientific-result validation remain outside this refactor.

## Problems and evidence

`status_views.bundle_jobs_context_from_rows` currently appends a separate
`reason=... exit=...` line whenever either field exists. Even completed jobs
with exit `0:0` acquire a second line. Reasons are difficult to associate with
their jobs in a dependency graph. The scheduler adapter already collects queue
reasons and accounting exit codes; another scheduler query is unnecessary.

The reported bundle is the acceptance example:

| Job | Scheduler state | Proposed reason column |
|---|---|---|
| set | COMPLETED | — |
| shards | RUNNING (2/4 array tasks) | — |
| merge | PENDING | Waiting for shards |
| summary | PENDING | Waiting for merge |

The summary job declares dependencies on both merge and set. When fresh evidence
shows set completed, it should name only merge as the outstanding direct
dependency. An array parent is not complete because some indices completed.
The array progress meaning must remain explicit and consistent with inspection.

## Decisions and proposed contract

- **S11.1 Requested:** reasons belong in the normal row; readable names explain
  dependency waits and distinguish other main reasons for pending.
- **S11.2 Proposed:** retain Slurm's scheduler state and raw reason. Add a
  separate normalized waiting category and concise explanation. A reason is an
  observation, not a new scheduler state, queue position, or start-time estimate.
- **S11.3 Proposed:** one pure interpretation owner, tentatively
  `pending_reasons.py`, supplies structured explanations to inspection and
  presentation. It consumes existing snapshots and the saved graph; it performs
  no commands, refreshes, persistence or terminal formatting. `status_views`
  handles layout. Reuse existing task/state/graph owners.
- **S11.4 Required:** preserve missing, stale, failed and unknown observations.
  An explanation must not convert missing evidence into completion or turn an
  ordinary pending job into a submission failure.

Use [Slurm's reason-code reference](https://slurm.schedmd.com/job_reason_codes.html)
as the source for scheduler meanings. Slurm can report one encountered reason
even when several constraints apply. Initial categories should cover:

| Raw reason family | Proposed interpretation |
|---|---|
| Dependency | Dependency wait; use graph names when evidence supports it |
| DependencyNeverSatisfied | Dependency cannot be satisfied; needs attention |
| Priority | Waiting for scheduling priority |
| Resources | Waiting for requested resources |
| JobArrayTaskLimit | Waiting for the array concurrency limit |
| JobHeldUser / JobHeldAdmin | Held by user / administrator |
| Assoc* / QOS* limits | Waiting on an allocation or policy limit; retain exact code |
| BeginTime | Waiting for its eligible start time |
| Invalid account/QOS, partition or constraint problems | Configuration/availability issue; retain precise reason |
| Missing or unrecognized reason | Unknown, with raw code when available |

Normalize known queue parentheses without destroying raw text. A missing reason
or `None` does not establish that no scheduling constraint exists. Interpret
terminal failures separately; do not label every reason as a pending cause.

## Dependency and array evidence

Name only declared direct dependencies, not an inferred transitive chain. Use
the exact attempt's accepted IDs and original array indices. A satisfied parent
can disappear from the waiting explanation only when sufficient current evidence
supports that conclusion. With stale/missing parent observations, use qualified
wording such as “Waiting for dependencies; last observed: merge” rather than
asserting a current blocker. External/unmapped IDs retain their IDs.

Distinguish ordinary dependency wait from an impossible dependency. Do not infer
that every failed parent makes every Slurm dependency impossible without checking
the actual dependency condition. A mismatch between the saved graph and observed
reason is evidence to expose, not silently repair.

Mixed arrays can contain running, completed, failed and pending tasks together.
An aggregate row summarizes pending categories/counts without inventing one
reason for every task; expanded rows retain each observed reason. Preserve the
index selection contract shared by `asl status` and `asl logs`.

## Presentation and public routes

Add a bounded reason column; normal rows should not acquire raw diagnostic
continuation lines. Full raw reasons, exit codes and observation sources remain
available through supported detail/structured output. Keep significant terminal
failure information discoverable, while avoiding pending `exit=0:0` clutter or
claims of scientific success from a scheduler exit code.

Define wide/narrow terminal layouts and deterministic non-TTY output. Account
for ANSI color width, long names and reason truncation; provide a clear supported
route to the unabridged detail. Do not rely on a fullscreen terminal preventing
wrap. Review the pending time field too: a requested walltime is not time until
start and must not be presented as a queue ETA.

The same explanation data must reach supported Python inspection, CLI JSON/text
and ACP context. Settle additive fields and historical snapshot behavior before
changing stored data. Human docs explain the table; agent docs explain categories,
raw evidence, freshness and safe follow-up. This does not add an automatic retry.

## Open questions

- Exact normalized field names and how old cached snapshots derive explanations.
- Compact-width column priorities and the command/option for full detail.
- Array aggregation wording and how to qualify partially stale parent evidence.

Resolve these in MVP11.1; do not require a new record hierarchy or scheduler
engine to deliver a clearer table.

## Forward constraints and checks

Mock queue/accounting data for the reported graph, completed and unknown parents,
Priority, Resources, impossible dependencies, holds, policy limits, future starts
and unfamiliar codes. Include sparse/mixed arrays, stale refresh failures and
dependency-condition differences. Verify normal rows, wide/narrow ANSI output,
untruncated structured reasons and unchanged status/log task selection. No extra
cluster calls; full offline regressions when shared inspection projection changes.

## Log

- 2026-11-13, PLAN.3: recorded the user's status example and proposed shared
  explanation/presentation boundaries. No runtime or saved-record changes.
- 2026-11-16: user requested a larger status refactor. Added interface/responsibility
  mapping and consolidated workflow/performance gates around existing reason
  tasks. All remain planned; runtime implementation continues with MVP10.4b.1.

## MVP11.0 implementation map — 2026-11-27

| Interaction | Current owner and cost | Refactor boundary |
|---|---|---|
| `asl status` overview | apps/status selects visible bundle snapshots, inspect_bundles reads each exact run and batches scheduler requests across producing identities | Keep selectors/order; summary_text renders supplied views only |
| `asl status NAME/INDEX --array` | Same batch collector, then reloads each definition for row resources/dependencies | Keep exact array indices; remove repeat loading in a later mechanical extraction |
| Python inspect_bundle(s), ACP inspect_run | inspection coordinates load/receipt overlay, profiles, scheduler, pure projection, caches and optional artifacts | One explanation owner applied to returned evidence; no second query path |
| inspect/list/context/cancel previews | status_views convenience wrappers or rows_from_resolved; some load/query explicitly | Keep routing and selectors, share explanations/layout; preserve cancellation producing metadata |
| Logs/fetch | inspection_artifacts, log_files and existing bounded caches | Same job/task identities; no scientific-result fetch |
| Campaigns | campaigns composes ordinary views; campaign_projection bounds output | Inherit member explanations; never cross-machine dependency inference |
| Cached inspection | validated fingerprinted sidecars, no scheduler/source-log access or cache writes | Derive explanations on read; old caches remain valid |

One scheduler observation consists of queue + accounting queries; remote mode
combines them in one SSH command per producing identity. inspect_bundles shares
that observation across selected runs. It reads definitions/receipt evidence and
validates sidecars; explanation/layout must add zero external calls. Source-log
reads happen only when explicitly requested by log/fetch operations.

First vertical runtime slice MVP11.1a delivers reason classification, conservative
named default-afterok dependency explanations, mixed-array pending summaries and
bounded job tables together so the result is usable immediately. This draws from
MVP11.1–3, whose broader gates remain separate; it creates no parallel status
engine. Runtime-derived explanation fields are not persisted, so no record/cache
version change or migration is needed. Raw scheduler state/reason/exit stay intact.

Selectors remain name/index/range, exact bundle file and original array indices.
Default discovery/history visibility stays unchanged. --details will retain raw
text evidence; --json is the complete structured route. Cached explanations are
explicitly last-observed. Requested walltime is a limit, never a pending start ETA.
User amendment on 2026-11-27 brings the simplified overview, colors, failure
classification and --head into MVP11.1a. Definition-load extraction and further
filters/consolidation remain MVP11.4.

## MVP11.1a delivered contract — 2026-11-27

The user approved the simpler overview/job layout and requested --head. Existing
array_status owns corrected aggregates: failures beat cancellations; active work
beats cancellation elsewhere, and missing states prevent declaring completion.
Explicit array-parent cancellation cannot hide known failed tasks. Raw Slurm
parent/task facts remain unchanged. Compatible older cached aggregates and prior
jobs are recalculated in memory by inspection_state, without migration or writes.

status_explanations is the pure owner of disposable job/task explanation fields.
inspection applies it after cache I/O; supplied-data convenience callers share it.
Default bundle afterok dependencies name direct parents only, qualify unverified
parents and omit freshly completed parents only with complete task evidence and
a completed aggregate. Custom Slurm conditions stay generic. Failed arrays retain
attention even with pending tasks. No new query path or persisted explanation
fields. Mixed-array task reasons remain individually available.

status_views owns summaries/rows; status_table owns terminal-safe bounded layout.
Overview is idx/run/status/tasks, plus a data qualification when needed, and a
checked timestamp. Human labels include UNSUBMITTED/QUEUED while JSON retains
existing states. Counts include supporting jobs, not unique scientific outputs.
Job rows are idx/id/job/status/tasks/reason; completed historical reasons and
routine zero exits move to details. Resource/walltime limits remain in details,
not mislabelled as pending remaining time. NO_COLOR and --color auto/always/never
control text colors; JSON remains plain. --width bounds tables and signals
abbreviation. --details exposes full evidence and overview saved/exact references.

--head defaults to 10 or accepts N, over the newest currently visible runs before
inspection; no extra scheduler calls for excluded runs. It is overview-only,
compatible with --cached/--json, and preserves normal ordering/indices. Invalid
counts and array selectors fail before observation. No default history/filter
change, cross-machine prerequisites, watch, queue ETA or scientific inference.

Verification: 49 new regression cases; 1848 full offline tests passed in 18.84 s,
84 expected collision warnings. Tests cover the reported 50-failed/1-cancelled
case, cached old aggregates, defaults/custom dependencies, mixed arrays, pure
no-I/O explanation, raw preservation, CLI/ACP parity, colors/NO_COLOR/JSON,
wide/narrow Unicode tables, cached no-write/no-query, stable selectors and
pre-query --head limits. Installed package/metadata/build evidence is recorded
in the installation register. Broader MVP11.1–4 closure stays open; in particular,
legacy convenience loading and the status CLI's repeated definition read are
not claimed removed. MVP10.6 diagnostic adoption remains separate.
