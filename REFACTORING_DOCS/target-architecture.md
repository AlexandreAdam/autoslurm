# Target Architecture

This document describes the intended internal model for the refactored
AutoSlurm stack.

## Design Intent

The refactored system should be local-first. After a sync, the local AutoSlurm
storage should contain enough information to inspect bundles, report status, and
find logs without requiring live Slurm accounting as the default path.

## Core Internal Model

The system should maintain a canonical bundle/job record with:

- bundle snapshot identity
- job name and submission metadata
- logical Slurm job id
- raw Slurm job id
- array parent id and array task index
- job state
- log path or log-path candidates
- source/provenance of each resolved field

## Local Memory Layer

The local memory layer should be built from synced artifacts and persisted in a
machine-readable local index.

It should allow:

- status lookup without immediate cluster access
- array-task lookup from local metadata
- log lookup from local `.out` files and local mapping records
- provenance-aware fallbacks when data is incomplete

## Sync-Driven Refresh

`sync` should become the boundary between remote state and local state.

It should:

- mirror remote bundle snapshots
- mirror remote output logs
- update or rebuild the local status/log index
- record what data was refreshed and when

## Reader Behavior

Read-side commands should follow this order:

1. consult the local index
2. use local files and cached mappings
3. fall back to live cluster queries only when needed
4. surface incomplete state explicitly

This applies to:

- `status`
- `logs`
- `inspect`
- `clean`

## Module Direction

- One module should own bundle snapshot selection and visibility policy.
- One module should own status resolution.
- One module should own log resolution and array-task mapping.
- One module should own sync/index refresh behavior.
- CLI entrypoints should mostly parse arguments and render output.

## Legacy Boundary

When a path is replaced, the old code should move to a legacy location rather
than being removed immediately. The legacy path is for reference, compatibility,
and regression comparison during the transition.

