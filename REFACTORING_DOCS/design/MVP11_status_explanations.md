# MVP11 Readable dependency-aware status

## Status

Requested by Alexandre on 2026-11-13; **planned, not implemented**. The requested
outcome is a reason column in the normal job table, with understandable waiting
categories and dependency job names. Contracts and module names below are
proposed. [PLAN.md](../../PLAN.md#mvp11-readable-dependency-aware-status) owns
delivery order and task completion.

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
