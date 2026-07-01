# AutoSlurm Refactor Roadmap

## Summary

The current AutoSlurm design leans too heavily on live Slurm queries and
duplicated assumptions in CLI entrypoints. The refactor will move the system
toward a local-first model where `sync` builds and refreshes the internal view
of bundles, job status, and logs, and read-side commands render from that local
state before reaching back to the cluster.

## Goals

- Make local AutoSlurm storage the main source of truth after refresh.
- Centralize status, log, and array-task indexing.
- Reduce dependence on live `sacct` and other accounting queries.
- Keep the user-facing interface stable while internals change.
- Preserve current behavior as long as possible during migration.

## Current Pain Points

- `status` and `logs` depend on live Slurm state more than is desirable.
- `sacct` availability is a brittle external dependency.
- array-job log mapping is split across multiple code paths.
- CLI behavior is spread across several modules with repeated assumptions.
- fallback behavior often hides whether data is genuinely absent or merely
  unavailable.

## Phased Plan

### Phase 1: Document the current behavior

- Record the current CLI surface and the actual behavior of `submit`, `status`,
  `logs`/`inspect`, `sync`, `clean`, and `filter`.
- Capture how bundles, snapshots, job ids, array jobs, and log filenames are
  currently resolved.
- Identify the places where cluster queries are required today.

### Phase 2: Define the internal model

- Introduce a local snapshot model for bundles and submitted jobs.
- Track logical ids, raw ids, array task ids, job state, and log locations in a
  single structured index.
- Make provenance explicit so readers know whether data came from local cache,
  sync, or live query fallback.

### Phase 3: Make sync the refresh boundary

- Use `sync` to populate the local job/status/log memory.
- Mirror remote bundle files and `.out` logs into the local storage view.
- Record enough metadata locally to allow offline inspection whenever possible.

### Phase 4: Move readers to the local model

- Refactor `status`, `logs`, `inspect`, and `clean` to read the local index
  first.
- Keep live Slurm queries as optional repair paths instead of the default path.
- Return explicit warnings when data is incomplete rather than silently hiding
  uncertainty.

### Phase 5: Centralize shared assumptions

- Move array parsing, log lookup, bundle selection, and snapshot policy into
  shared modules.
- Keep CLI entrypoints thin.
- Eliminate duplicated status logic across the package.

### Phase 6: Retire old code paths carefully

- Move replaced implementations into `legacy/` modules when they are no longer
  the active path.
- Preserve the old behavior as reference material until the new path is
  validated.
- Remove or deprecate the legacy path only after tests and docs cover the new
  behavior.

## Migration Principles

- No destructive rewrites.
- No silent behavior changes.
- Preserve backwards-compatible behavior until the replacement is validated.
- Prefer one canonical implementation per concern.
- Keep assumptions in shared modules rather than re-deriving them in CLI code.

## Success Criteria

- `status` and `logs` work from local cached state after sync, even when Slurm
  accounting is partially unavailable.
- Array-job handling is consistent across status, log lookup, and inspection.
- The CLI interface remains usable during the transition.
- Legacy code remains available as context until the new design is stable.

