# MVP6 Persistence and transport boundaries

## Status

In progress locally on `dev`, 2026-11-12. Base daily commands import main;
verification uses `.development/python` with temporary state and mocked external
commands. Baseline: 366 offline tests passed (38 expected collision warnings).
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

## Open questions and forward constraints

No database/index, record migration, multi-writer transaction guarantee, automatic
transfer retry or deployment. Mutable scientific source and prepared environments
remain MVP7. Real cluster compatibility is not established by mocked commands.

## Log

| Date | Event |
|---|---|
| 2026-11-12 | MVP6.0 local baseline: 366 passed in 3.14 s |
| 2026-11-12 | MVP6.1 mechanical extraction: all existing 366 offline tests passed in 3.52 s (39 expected warnings); patch targets moved to their owning adapters |
