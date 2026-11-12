# MVP6 Persistence and transport boundaries

## Status

Complete locally on `dev`, 2026-11-12. Base daily commands import main;
verification uses `.development/python` with temporary state and mocked external
commands. Baseline: 366 offline tests passed (38 expected collision warnings).
Final verification: 392 offline tests passed in 3.27 s (39 expected warnings).
Task commit: `git log --grep '^MVP6.3:'`; local tag `mvp6` at closure.
No cluster access, dependency installation, storage migration or push.

## Problems

Bundle storage contains selection policies, configuration access and SCP calls.
`utils` mixes machine normalization, SSH addressing/root probes, script naming
and bundle writes. The configuration CLI duplicates serialization. Wildcard
package imports leak implementation helpers. Existing writes and snapshot name
collisions need focused failure checks before changing their behavior.

## Decisions (implementation scope; reviewable)

- **D1 Owners.** Extract existing selection/discovery to `bundle_selection`,
  profile normalization/selection/storage to `configuration`, SSH addressing and
  root discovery to `transport`, and file movement to `file_transfer`. Local
  persistence remains in `save_load_jobs`; historical import paths use explicit
  aliases, with one active implementation per operation.
- **D2 Persistence.** Move the existing atomic receipt writer to a shared local
  record module. Use it for configuration and bundle updates. Add complete,
  exclusive snapshot publication so repeated timestamp collisions cannot replace
  earlier work. Existing JSON shapes and selection semantics stay intact.
- **D3 Effects.** Configuration reads never query hosts; transfer adapters own
  copy/probe commands. Preserve explicit contexts and dispatch uncertainty rules.
  Consolidate CLI configuration writes and SSH command/address construction.
- **D4 Exports.** Explicit package imports and `__all__` retain intentional
  callable contracts while removing accidental typing/dataclass/import leaks.
  Internal modules remain private integration surfaces.

## Validation

First verify the mechanical extraction with existing tests. Reproduce persistence
failure/collision and transport boundary bugs before fixes; verify old bytes,
exact selection/identity, bounded copy batches, quoting, no hidden network in
local operations and unchanged scientific/submission/inspection behavior.

The first extraction passed all 366 existing tests (3.52 s). Seven failing
regressions then demonstrated configuration/metadata serialization corrupting
existing records, failed new saves leaving visible partial JSON, rapid scheduling
clobbering snapshots, explicit transfer profiles being replaced by discovery,
identity paths with spaces splitting into multiple arguments, and SSH failure
being reported as missing directories followed by successful sync.

These now pass. The final 392-test suite adds 26 checks over the baseline,
including interruption/flush/replace failures, cleanup, exclusive collision races,
post-publication directory-sync failure, atomic multi-job append/empty append,
blocked storage directories, no process effects for local persistence/profile
reads, staged transfer failures without retries, batched SCP with saved contexts,
rechecking directories, sync copy failure, explicit exports and pure SSH arguments. Session cleanup is also checked for malformed SSH profiles.
Full scientific reference, receipt, CLI, ACP and inspection coverage is retained.
Report: `.development/test-runs/mvp6-final-reviewed.xml`.

Local persistence is 219 lines, selection/discovery 383, configuration 150,
transport 98, file movement 160, shared record writer 38 and compatibility utils
17. `schedule_job` now coordinates normalization and shared snapshot/append
storage rather than independently implementing collision-prone writes. Sync is
32 lines of profile/context selection and presentation around the transfer adapter.
Internal callers use the owning modules; historical aliases share implementations.
Observation caches import the shared writer directly, without a receipt dependency.

Existing JSON names/shapes and intended root exports are retained (63 explicit
public names). Accidental typing/dataclass/import exports are removed. Appending
multiple jobs is one atomic update; empty append returns an exact saved path.
Staging directories are checked each operation and created in one batch for script
staging; no global stale existence cache. Explicit transfer profiles/contexts take
precedence over profile discovery. SSH identity paths are quoted consistently;
SSH hostname aliases keep their historical SSH-config behavior.

The shared writer flushes data before replace/exclusive publication and syncs the
parent directory. A pre-publication error preserves the old file and cleans the
temporary; a directory-sync error after publication can leave the complete new
record visible and is still reported. Exclusive publication uses a hard link on
the same local filesystem; unsupported publication fails without a truncating
fallback. No claim is made about arbitrary cluster filesystems or concurrent
append read/modify/write operations. Sync retains ignore-existing jobs/scripts
and checksum-based mutable-log behavior; interrupted copies may be partial.

Base Conda imports the active main source and command help works. The baseline
rollback remains clean at `33bcbd34fb167fca67aa64739a013073c64167b1`. Main/test/
rollback persistent configs remain absent and jobs/scripts/logs/receipts/
observations have zero runtime files. No source/environment/state migration.

## Open questions and forward constraints

No database/index, record migration, multi-writer transaction guarantee, automatic
transfer retry or deployment. Mutable scientific source and prepared environments
remain MVP7. Real cluster compatibility is not established by mocked commands.

## Log

| Date | Event |
|---|---|
| 2026-11-12 | MVP6.0 local baseline: 366 passed in 3.14 s |
| 2026-11-12 | MVP6.1 mechanical extraction: all existing 366 offline tests passed in 3.52 s (39 expected warnings); patch targets moved to their owning adapters |
| 2026-11-12 | MVP6.2 seven regressions reproduced and fixed; shared record writer, snapshot/append hardening, transfer/config/SSH boundaries and explicit exports |
| 2026-11-12 | MVP6.3 full offline suite: 392 passed; current client/human/map/register updated; local `mvp6` checkpoint |
