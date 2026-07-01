# Refactor Strategy

This document records the meta-strategy for redesigning AutoSlurm into a more
modular, maintainable backend.

The intent is not to preserve the current architecture. The intent is to
preserve useful behavior while replacing the architecture with something easier
to understand, test, and extend.

## Strategy Summary

1. Freeze the current behavior as a reference point, not as a design target.
2. Define a small set of canonical data objects before rewriting modules.
3. Rebuild one vertical slice at a time behind narrow interfaces.
4. Write new tests against behavior and contracts, not old implementation
   details.
5. Keep legacy code only as a comparison target until each slice is replaced.

## Design Priorities

- Keep core logic pure where possible.
- Separate state, policy, transport, and presentation.
- Make external dependencies replaceable.
- Centralize assumptions instead of duplicating them across CLI entrypoints.
- Prefer small explicit modules over large shared hubs.

## Core Architectural Split

The new architecture should separate these responsibilities:

- bundle state and snapshot persistence
- sync-driven local indexing
- submission transport
- status resolution
- log resolution
- cleaning and snapshot policy
- CLI parsing and rendering

If a function needs to know about storage, transport, naming, status policy, and
CLI formatting at the same time, it is too broad and should be split.

## Rebuild Method

The package should be reimplemented as vertical slices:

1. bundle/storage model
2. sync and local index
3. status resolution
4. log resolution
5. submit path
6. clean/filter surfaces

Each slice should be complete enough to run and test independently before
moving to the next slice.

## Testing Approach

Use tests that validate the public behavior of the system:

- command-level contract tests
- service-level orchestration tests
- pure unit tests for parsing and indexing
- a small number of integration tests for real Slurm/SSH behavior

The tests should describe the new system, not the old helper structure.

## Legacy Policy

- Keep old code available while the new slice is being built.
- Do not let new code depend on old assumptions.
- Translate old formats at the boundary if needed.
- Move replaced code into legacy locations once the new path is validated.

## External Dependency Boundary

The backend should isolate tools like:

- `ssh`
- `sbatch`
- `squeue`
- `sacct`
- `rsync`
- `scp`

These should be behind small adapter interfaces so they can be mocked, swapped,
or replaced without disturbing the core logic.

## Success Criteria

- The package can work from a local cache after sync where possible.
- Array-job handling is consistent across status, logs, and clean.
- Submission, inspection, and synchronization are decoupled from one another.
- New tests cover the intended behavior without inheriting old assumptions.
- The codebase becomes easier to extend without reintroducing cross-cutting
  coupling.

