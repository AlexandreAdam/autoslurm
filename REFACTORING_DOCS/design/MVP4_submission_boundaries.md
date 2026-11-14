# MVP4 Submission responsibility boundaries

## Status

Complete locally, 2026-11-11. The user requested implementation modularity and careful
review of brittle concepts. Implemented in the isolated checkout; no cluster
access, promotion, dependency installation or new persisted format. Task commit:
`git log --grep '^MVP4.3:'`; local tag `mvp4` at closure.

## Problems

`submit_jobs` implements validation/rendering, operation identity/record creation,
script writes, transport, dispatch, outcome classification, persistence and output.
Preview duplicates only part of its validation, so a preview can approve a job
that submission rejects. Local submission mutates dependency directives after
shell validation; remote submission supplies command arguments instead. These
are concrete responsibility and consistency problems, not file-size targets.

Inspection also mixes query/state/cache/artifact responsibilities and bundle
storage includes transfer. Those are follow-up MVP5/MVP6 scopes, not prerequisites.

## Decisions (implementation scope; reviewable)

- **D1 Shared preparation.** Internal `PreparedJob`/`PreparedBundle` values carry
  copied definitions, resolved execution metadata, rendered script text and the
  existing graph. One preparation function performs data validation/rendering
  with an already resolved context, without filesystem writes/network/processes.
  Path preflight and shell checks are an explicit subsequent validation stage.
- **D2 Explicit stages.** `job_runner` selects/loads a definition and coordinates
  preparation/validation and execution. A submission operation owns transient
  dispatch progress, tracking references and evidence. Small functions create
  records, stage scripts, dispatch and persist outcomes; avoid replacing one
  large function with another large function in a different file.
- **D3 Stable scripts.** Dependencies use `sbatch --dependency afterok:...` for
  local and remote execution. Validated/rendered scripts remain byte-identical
  through execution. Dependency graph rules remain in the existing graph driver.
  **FIX.DEPENDENCY.1 amendment (2026-11-13):** Alexandre requests dependent jobs
  default to `#SBATCH --kill-on-invalid-dep=yes`. The shared renderer adds it for
  nonempty declared dependencies, preserving explicit Slurm overrides (including
  `kill_on_invalid_dep: "no"`). Root jobs gain no implicit option. Defaults are
  applied to a copy, not saved definitions; IDs still bind at dispatch. Slurm
  cancellation of impossible dependencies is separate from submission rejection
  or automatic retry. Historical/queued scripts are unchanged.
- **D4 Evidence before progress.** Preserve the driver's per-job receipt writes,
  exclusive claim, known-ID guards, no fallback/retry and uncertainty window.
  Failure after dispatch remains distinct from failure before dispatch; a final
  observed receipt survives later cleanup/persistence errors. Initial receipt
  persistence failure must carry evidence and never reach the scheduler.
- **D5 Bounded change.** Keep public preview/submit signatures and receipt JSON.
  Preview intentionally rejects invalid/submitted definitions with the same
  preparation rules as submission. Internal test patches follow the extracted
  adapter owners; no compatibility aliases solely for private test patches.

## Validation

Reproduce preview/submission disagreement first. Add behavior checks for invalid
late jobs/empty or submitted definitions, pure preparation with no external calls,
shared preview/script/evidence paths, unchanged dependent scripts, staging and
initial receipt failure before dispatch, lost responses/partial acceptance and
failure after a final observed response. Retain full offline science/submission
coverage; inspect stable/development imports and preserve unrelated user edits.

The initial regressions reproduced four preview/submission disagreements:
empty bundles, missing commands, invalid names and already-submitted definitions.
Both entry points now reject them through shared preparation. A second reproduced
bug showed a `KeyboardInterrupt` during accepted-ID persistence losing that ID
from the raised error. The driver now carries its current evidence out through
`SubmissionError`, stops subsequent jobs and lets workstation persistence retain
known IDs. Initial receipt-write failures also carry in-memory evidence.

**333 offline tests passed in 3.22 s**, with 39 expected snapshot-collision
warnings. Report: `.development/test-runs/mvp4-review.xml`. The 313-test baseline
passed before changes; new checks exercise preparation without file/process
operations, copies of mutable inputs, malformed mapping rejection, shared preview/
execution metadata and byte-identical scripts, dependency arguments in both
lanes, receipt/script/transfer/session failures before dispatch, lost responses,
cleanup and final tracking errors after acceptance, and persistence interruption.
Existing single/array/reducer scientific tests, remote helper mocks, per-job
partial failures and stale inspection remain passing.

`submit_jobs` is reduced from 116 to 20 lines including its signature; it
coordinates selection, shared preparation, capability checks and execution.
The two internal modules have explicit stage functions; no client must construct
these objects. Preparation performs no effects with an already-resolved context;
validation/preflight and dispatch remain explicitly effectful. This is a boundary
change, not a claim that every large function or dictionary contract is solved.

Stable source/import/runtime remain pinned and unchanged; persistent stable and
development configs are absent. Updates stay in the development checkout.
No push, cluster access, source promotion or installation changes performed.

## Open questions and forward constraints

Prepared values are internal snapshots containing copied dictionaries; no claim
of deep immutability or durable plan format. Preparation does not freeze input
files, environments or scheduler availability; preflight is point-in-time. File
storage transactions, comprehensive receipt state modeling, safe shell argument
encoding, broad public API cleanup and inspection/persistence decomposition are
separate tasks. Maintain truthful exceptions and do not promise exactly-once.

## Log

| Date | Event |
|---|---|
| 2026-11-13 | FIX.DEPENDENCY.1 adds a nonmutating dependent-job kill-on-invalid-dep=yes render default; explicit overrides/root jobs and dispatch-time ID binding retained. 741 offline tests passed in 9.69 s (42 expected warnings); clean wheel/default/actual-shell smoke passed. No actual cluster or historical/queued script change |
| 2026-11-11 | MVP4.0 scopes shared preparation and submission stage boundaries; follow-up inspection/persistence MVPs added |
| 2026-11-11 | MVP4.1 shared preparation and explicit preflight implemented; preview parity regressions pass |
| 2026-11-11 | MVP4.2 operation stages and dispatch phases extracted; dependencies no longer mutate scripts; persistence interruption retains known IDs |
| 2026-11-11 | MVP4.3 333 offline tests passed; public recipe and follow-up MVP5/MVP6 boundaries updated; local `mvp4` closure |
