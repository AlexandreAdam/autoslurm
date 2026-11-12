# MVP3 Shared inspection

## Status

Complete locally, 2026-11-11. Development only; Slurm/SSH/transport are mocked.
Stable source and production routing remain pinned. Task commit is located with
`git log --grep '^MVP3.3:'`; local tag `mvp3` closes this milestone.
The decisions below describe the implemented MVP boundary; broader designs
remain provisional.

## Problems

Before MVP3, status, array expansion, bundle aggregation and logs re-derived identity
and could hide failed queries or manufacture states for missing tasks. Previous
sync skipped growing files; remote log fallback parsed human Markdown and can use
an edited profile rather than producing locations.

## Decisions

- **D1 One observation pipeline.** A scheduler adapter batches queue/accounting
  queries once per producing machine/operation. Preserve per-query errors and
  source/time metadata. Existing status/terminal adapters consume the shared task
  view; retire duplicate active queries and task aggregation.
- **D2 Canonical tasks.** One array parser defines concrete indices and logical
  `parent_index` IDs, separate from accounting steps and raw scheduler IDs. Missing
  tasks stay unknown; parent evidence does not manufacture individual failures or
  completion. Counts and states use the same tasks everywhere.
- **D3 Exact structured inspection.** `inspect_bundle` accepts an exact bundle or
  receipt path; `list_runs` rediscovers local saved runs. Keep receipt outcomes
  separate from scheduler state and scientific validity. A small observation
  sidecar supports explicit cached reads and labels stale or failed evidence.
- **D4 Bounded logs.** Resolve stdout/stderr from producing metadata and the same
  logical/raw task identity. Read only bounded tails, with full path/size/error
  references. Explicit remote refresh uses recorded transport and batches selected
  files; never parse human output or resubmit. Support `%x`, `%j`, `%A`, `%a`, `%%`;
  unsupported substitutions fail explicitly. Preserve immutable definitions on
  sync; mutable logs can refresh, including replacement/truncation.
- **D5 Shared interfaces.** Terminal status/inspect, Python and ACP render the same
  observation result. Existing name/date/index convenience selection resolves to
  an exact path first. Provide a short human overview and revised agent handoff.

## Validation

Run the small scientific array with completed, failed, running and absent task
observations. Compare terminal/agent states and log identities, preserve unknowns
after empty/failed queries, retain failure/exit reasons, and fetch growing logs
twice without changing definitions or submitting work. Count machine queries;
test profile edits, custom patterns, raw IDs, step rows and cached observations.
Retain the full offline suite and installation separation.

The final full offline suite passed **313 tests in 3.87 s**, with 29 expected
snapshot-collision warnings. Report: `.development/test-runs/mvp3-final.xml`.
The new integration suite runs the installed scientific application through
mocked submission, compares exact task IDs/states/reasons/exit codes across
Python/ACP/CLI, and retains unchanged definition/tracking/receipt bytes.
Other checks cover empty/failed/partial scheduler replies, queue precedence,
transport/malformed responses, missing profiles without local fallback, step
exclusion, declared noncontiguous tasks, saved producing transport after profile
edits, raw `%j` IDs and custom stdout/stderr patterns, bounded/omitted logs,
remote replacement/append refresh and profile-based sync through truncation.
Cached reads issue no network calls, including conflicting refresh overrides;
changed/removed definitions cannot reuse an old observation as current evidence.

The exercised remote operation uses **one scheduler SSH and one selected-log
SSH**, with no separate raw-ID query. Multiple local runs share two scheduler
commands. These command counts are mock measurements, not a real-cluster latency
benchmark. Former duplicated query/array/log orchestration is retired; status
wrappers render the shared view. Historical context entry points now delegate
to inspect; full/unbounded dumps and same-name unsubmitted log adoption are
intentionally removed. The terminal labels scheduler completion `COMPLETED`.

Human overview, current client recipe, ACP metadata and task-specific context
were updated. CLI help, relative documentation links and stable/development
import/root separation were checked. No dependencies added, cluster access,
source promotion or public release performed.

## Open questions

No automatic diagnosis from log text, scientific success inference, retries,
adoption, general persistent index or concurrent-writer guarantee. Scheduler
history availability and real cluster validation remain outside local scope.
Numeric job IDs can be reused by Slurm; no historical incarnation disambiguation
or durable event ledger is added. Legacy remote records without producing path
metadata can query their named profile, but log lookup refuses path guessing.
Remote tails rely on standard login-node bash/base64/tail utilities. Sync is
profile-based and covers the default storage directories, not custom application
results; use exact inspection for run-specific bounded log evidence.

## Forward constraints

Read-only means no scheduler mutation. Observation/log caches may be written in
the selected development state; saved definitions and receipts are not rewritten
by status inspection. Bounded excerpts never replace full remote artifacts.

## Log

| Date | Event |
|---|---|
| 2026-11-11 | MVP3.0 bounded around shared task/query evidence, exact inspection and bounded log refresh |
| 2026-11-11 | MVP3.1 one queue/accounting adapter, canonical task view and local receipt overlay implemented |
| 2026-11-11 | MVP3.2 Python/ACP/CLI share exact inspection, observation caches and bounded producing log tails; mutable sync fixed |
| 2026-11-11 | MVP3.3 313 offline tests passed; human/agent guides and local `mvp3` checkpoint close the milestone without promotion |
