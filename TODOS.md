# AutoSlurm Workflow Notes

This document tracks the current workflow we have been building, the main pieces that now exist, and the assumptions that are no longer valid.

## Current Workflow

`autoslurm` is the scheduler and control plane.
`substructure_lens` builds the experiment bundles.

The intended flow is:

1. Configure one or more machines with `asl configuration`.
2. Build an experiment bundle in `substructure_lens`.
3. Register the bundle with `autoslurm`.
4. Submit the latest bundle or a named bundle with `autoslurm submit`.
5. Pull remote storage into the local mirror with `asl sync`, or refresh on demand with `asl context --refresh`.
6. Inspect bundle status, job status, scripts, and logs with `asl context`.

## What Exists Today

### In `autoslurm`

- `asl` root command as the main entry point.
- `agent` and `context` as short names, with backward-compatible aliases.
- `autoslurm submit --latest`.
- `autoslurm context --latest`.
- `autoslurm context --latest-log`.
- `autoslurm context --refresh`.
- `autoslurm context --clipboard` and `--clip`.
- Compact `context` views for:
  - latest bundle summaries
  - bundle job listings
  - single job status
  - job script output
  - logs
- Remote machine support through SSH aliases and `env_command`.
- Remote storage root discovery from the remote AutoSlurm install.
- Remote submission that:
  - copies SLURM scripts to remote `slurm/`
  - runs `sbatch` remotely
  - mirrors bundle JSON to remote `jobs/`
- `asl sync` as a pull-only mirror from remote `jobs/`, `slurm/`, and `out/`.
- Config storage at the AutoSlurm root, not under `src/`.
- `config.json`, `jobs/`, `slurm/`, and `out/` at the AutoSlurm root.
- Validation for remote machine config:
  - SSH reachability
  - venv activation
  - `python -c "import autoslurm"`
- Short machine summary with `asl configuration --summary`.
- Interactive machine rename and default-machine switching.

### In `substructure_lens`

- Bundle builders for:
  - alpha sweep
  - source-resolution sweep
- Shared bundle helper layer to avoid duplicating scheduling and logging code.
- Automatic experiment ledger in `jobs/experiments.jsonl`.
- Bundle scheduling into AutoSlurm by default.
- Configurable bundle names for experiment tracking.
- Quieter production runs:
  - reduced Bessel-root verbosity
  - Hutchinson start/finish timing prints
- Job metadata including:
  - timings
  - CG iteration counts
  - stop codes
  - epsilon/lambda definitions
  - output paths
- Jacobian mode subset computation so jobs only differentiate assigned columns.
- Batch controls separated by purpose:
  - Jacobian construction batch size
  - CG projection batch size
  - Hutchinson probe batch size

## Current Usage Pattern

Recommended day-to-day flow:

- configure machines once
- generate a named bundle from `substructure_lens`
- submit the latest or named bundle with `autoslurm`
- use `asl context` to inspect status and logs
- use `asl sync` only when you want to refresh the local mirror
- use `asl context --refresh` when you want fresh logs without calling sync manually

## Stale Assumptions

The following assumptions should be treated as stale:

- `local` must exist as a configuration entry.
- configuration should create runtime directories.
- machine config must include an explicit local path.
- remote machine discovery can rely on DNS resolution of SSH aliases.
- SLURM output should point at the local workstation path for remote runs.
- `context` should default to dumping everything.
- logs must be inspected manually in the filesystem.
- submission must always use a named bundle.
- remote AutoSlurm must be installed in a fixed path.
- `autoslurm` should own experiment purpose tracking as scheduler metadata.

## Caution Points

These parts are working, but should still be treated carefully:

- `context` on large remote logs can be expensive if refreshed too often.
- `sync` is intentionally pull-only and does not clean old files.
- experiment purpose tracking is still a lightweight local record, not a full database.
- the remote `path` override still exists in some places for backward compatibility, but the long-term model is root discovery plus `env_command`.

## Suggested Doc Sections

If this becomes a fuller docs page later, the natural sections are:

- Overview
- Machine Configuration
- Bundle Builders
- Submission Workflow
- Context and Logs
- Sync
- Experiment Logging
- Remote Execution Model
- Deprecated Assumptions
