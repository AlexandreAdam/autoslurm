# Current State Inventory

This document records the current AutoSlurm interface and the behavior that the
refactor must preserve unless explicitly changed.

## CLI Surface

- `autoslurm submit`
- `autoslurm status`
- `autoslurm logs`
- `autoslurm inspect`
- `autoslurm sync`
- `autoslurm clean`
- `autoslurm filter`
- `autoslurm configuration`

Aliases and short names exist for several surfaces, including `asl`, `config`,
`stat`, `context`, `agent-context`, and `kill`.

## Submission Path

- `submit` resolves a bundle by name, index, or `--latest`.
- Remote submission copies SLURM scripts and invokes `sbatch` remotely.
- Local submission runs `sbatch` directly.
- The submit path validates bundles before submission.
- The submit path does not currently require `sacct` to launch jobs.

## Status Path

- `status` renders bundle summaries from saved snapshots.
- It queries live Slurm state for job and array-task status.
- It currently uses `squeue` and `sacct` as live data sources.
- Missing accounting data can lead to incomplete or ambiguous state.

## Logs and Inspect Path

- `logs` and `inspect` are read-side inspection commands.
- They render bundle context, job details, scripts, and log contents.
- They use local `.out` files when available.
- For array jobs, they currently try to map logical ids to raw log ids.
- That mapping may depend on live `sacct` queries.

## Sync Path

- `sync` pulls remote AutoSlurm storage into local storage.
- It is the natural place to establish a local cache of remote state.
- Today it is primarily a mirror step, not yet a full local index builder.

## Clean Path

- `clean` operates on saved bundle snapshots.
- It classifies snapshots using snapshot state plus job-status information.
- It can rely on live job state when determining failed or cancelled bundles.

## Snapshot Model

- Bundle snapshots are stored in local JSON files.
- A snapshot includes bundle name, saved timestamp, jobs, ids, and metadata.
- Snapshot state is currently derived from submission count and validation rules.
- The snapshot layer is the closest thing to a local source of truth today.

## Known Structural Weaknesses

- Multiple modules reconstruct status independently.
- Log lookup and status resolution do not share a single canonical model.
- Remote and local assumptions are mixed into the CLI layer.
- Fallbacks often blur the line between "not available" and "not found".
- Array-job handling is split across status, logs, and experiment context code.

