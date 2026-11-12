# MVP2 Submission safety

## Status

Complete locally, 2026-11-11; closure tag `mvp2`. Implements the authorized next
MVP in the isolated development checkout, with mocked scheduler/transport only.
Stable source stays pinned. Task commit: `git log --grep '^MVP2.3:'`.

## Problems

Before MVP2, bulk response loss triggered legacy submission again, and a later
job's failure discarded earlier IDs. Local submission and the helper used
different dependency paths, with no durable exact submission outcome for agents.

## Decisions

- **D1 Shared execution.** Reuse the existing DAG driver for both local and remote
  submission. Validate job names, dependencies, all rendered scripts and declared
  paths before the first scheduler call. Remove automatic legacy fallback.
  Remote operation requires a receipt-capable helper and prepared `venv_path`;
  probe capability before dispatch. No automatic deployment.
  Graph validation now retains dependency edges regardless of definition order.
  Generated scripts are rendered and shell-syntax checked before dispatch;
  helper execution verifies all referenced script files before its first call.
- **D2 Incremental receipt.** Each operation gets a random submission ID and an
  exact new tracking snapshot. A JSON sidecar under `submissions/` records planned
  and actual paths, machine/transport, per-job states, IDs, errors and timestamps.
  Write atomically before each scheduler call and after each acceptance. A
  persistent exclusive claim prevents replay of the same helper identity.
  Bundle snapshots are created exclusively rather than overwriting colliding
  second-resolution names. Script names use the random submission identity;
  existing inspection uses the shared name helper to find them.
- **D3 Outcomes.** Overall states distinguish submitted, rejected, partial and
  uncertain. These describe submission, never scientific completion. On a known
  failure, stop; descendants are blocked and unrelated jobs remain not submitted.
  A missing/malformed scheduler response is uncertain. On lost transport, preserve
  known IDs and label unobserved work uncertain: a remote helper may still run.
- **D4 Client contract.** `submit_jobs` returns a plain receipt or raises
  `SubmissionError` carrying that receipt. Public list/load/refresh operations,
  CLI summaries/JSON and ACP reads expose the same record. Refresh fetches only
  that receipt, using recorded transport; it never submits, adopts or retries.
  Keep IDs projected into existing bundle jobs. Preserve receipt-bearing records
  against ordinary cleanup and refuse resubmitting a submission snapshot.
  Readiness failures before receipt creation raise ordinary validation errors;
  post-creation submission errors retain the receipt. Remote receipts must match
  the exact identity/jobs and cannot discard or replace a known ID. An observation
  failure is recorded separately from a known submission outcome.
- **D5 Environment.** Job `environment` maps valid shell variable names to
  literal scalar values, quoted without expansion. Separate `runtime_environment`
  maps names to a single runtime variable name; export from that variable only
  after environment activation, requiring it to exist. No arbitrary shell
  interpolation, command substitution or application-specific thread policy.

## Validation

**295 offline tests passed in 2.62 s**, with 28 expected second-resolution
snapshot-collision warnings. Report: `.development/test-runs/mvp2-final.xml`
under the original repository. Coverage includes same-level and later rejection,
interruption/malformed output, response loss after final/unfinished execution,
execution-side ID persistence and in-memory evidence after receipt storage failure,
capability and helper replay guards, late graph/script errors before submission,
read-only refresh using producing transport after profile removal, rejected
identity/ID changes, cleanup protection and literal/runtime environment exports.
The existing single/array scientific client still passes. Local shell syntax
and export checks execute only local bash/Python fixtures; Slurm/SSH/transport
are mocked, including the actual helper-module smoke check with fake Slurm.

Development import and state identity remain separate; both persistent config
files are absent. Base Conda still imports the untouched baseline source;
stable runtime directories contain no non-dot files. CLI receipt help and
documentation links were checked. No cluster access, push or promotion occurred.

## Open questions

No automatic reconciliation/resume or exactly-once scheduler guarantee. A crash
between scheduler acceptance and receipt persistence remains uncertain. Version
enforcement, status/log consolidation and distribution are separate increments.

Prepared/submitting receipts are last-recorded intermediate evidence, not proof
of a live helper. Unknown results require receipt/scheduler investigation in the
owning lane before any explicit new operation. The original draft can still be
submitted as a new operation by an explicit user decision; helper identity replay
and submitted-snapshot reuse are refused, without a global deduplication ledger.

## Forward constraints

Receipts remain plain data, not a new database or workflow engine. Never change
environments or source referenced by queued/running jobs. Keep original records
and known IDs available after every failure; no cancellation or retry on failure.
The existing `sync` command still skips existing files; receipt refresh is an
explicit separate exact fetch. Task/log evidence and scientific completion are
not derived from submission receipts. The pinned stable version retains its old
interfaces; a prepared matching helper is required before eventual promotion.
No package/version enforcement, automatic reconciliation, retention policy or
general concurrent-writer guarantee is added.

## Log

| Date | Event |
|---|---|
| 2026-11-11 | MVP2.0 bounded around shared submission, incremental receipts and exact read-only recovery inspection |
| 2026-11-11 | MVP2.1 shared graph driver, exclusive operation identity and incremental execution receipts implemented; unsafe fallback retired |
| 2026-11-11 | MVP2.2 Python/CLI/ACP receipt reads and explicit refresh, known-ID projections and evidence protection implemented |
| 2026-11-11 | MVP2.3 295 offline tests passed; guides/schema updated and local tag `mvp2` closes the milestone without promotion |
