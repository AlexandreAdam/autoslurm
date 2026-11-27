# Reading job status

Start with the latest saved runs:

```sh
asl status --head             # Latest 10 saved runs
asl status --head 5           # Latest 5
asl status                   # All runs visible under the current history policy
asl status 2                 # Jobs in run 2
asl status 2 --array          # Individual array tasks
asl status 2 --array 0 3-5    # Original Slurm task indices
asl status 2 --details       # Full reasons, exit codes and resource/time limits
asl status --head --cached   # Saved status without contacting the cluster
asl status 2 --json          # Complete structured evidence
```

`--head` selects the newest run/bundle rows before querying Slurm. It does not
mean individual jobs inside a bundle. It works with overview, cached and JSON
output; use a run selector separately to drill down. Indices/order keep their
usual meaning. Keep an exact bundle/receipt reference for durable agent handoffs,
since newly saved runs can change indices.

## The overview

```text
idx  run                    status       tasks
1    gs-gold-v1             RUNNING      15 running · 174 waiting · 69 done
2    gs-kepler-luminous-v0  FAILED       50 failed · 1 cancelled
3    gs-full-rehearsal-v0   COMPLETED    103 done
4    rehearsal-draft       UNSUBMITTED  63 not submitted
Checked: 2026-11-27 15:38:07 UTC
```

Counts describe scheduler tasks, including setup/merge and other supporting
jobs. They are not a count of unique scientific results. `COMPLETED` means
scheduler completion; your application still validates its outputs.

- **FAILED** takes priority over cancellations. A failed compute array with a
  cancelled merge remains failed. Running, waiting and unknown counts remain
  visible beside failures.
- Active work takes priority over a cancellation elsewhere. With no known
  failure or active work, missing states prevent claiming a fully finished run.
- **UNSUBMITTED** means the definition is saved, not that its environment or
  inputs have been checked for readiness. The structured state remains
  `ready_to_go` for existing programmatic consumers.

Green means completed, blue running, yellow queued/cancelled, red failed/rejected,
magenta unknown/uncertain/unavailable, and dim unsubmitted. Terminal colors are
automatic; redirected output and JSON stay plain. Set `NO_COLOR`, or use
`--color never`; `--color always` forces colors for text output.

## How current is this information?

**Checked** is the time of a successful collection, not when the job ran. It
does not establish that every task has a known state; unknown counts remain
explicit. When runs were checked at different times, the footer shows a range.
If a row needs qualification, a `data` column explains it:

| Label | Meaning |
|---|---|
| checked | The current refresh completed without collection errors |
| cached | Previously saved evidence; no new cluster check |
| partially checked | Some evidence was collected, but part of the refresh failed |
| unavailable | The check failed; current task states may be unknown |
| not checked | No saved scheduler check exists |

Errors remain visible. A freshly attempted failed check is not a refreshed
successful result. `--cached` never contacts the scheduler/source logs, refreshes
receipts or writes caches. Older compatible sidecars are read without migration;
derived aggregates are corrected in memory, so old failure-plus-cancellation
records also report failure when inspected from cache.

## Job and array details

The job table shows the job ID/name, state, array progress and an explanation.
The reason column distinguishes dependency waits, priority, requested resources,
array concurrency, holds, policy limits and unknown reasons. Default bundle
dependencies can name outstanding direct parents, for example `Waiting for shards`.
A freshly completed parent is omitted only with complete successful task evidence.
Stale/missing parent evidence is qualified. Custom Slurm dependency expressions
retain a generic explanation rather than being reinterpreted as `afterok`.
Cross-machine dependencies remain unsupported.

Mixed arrays keep individual task reasons in `--array` and JSON. Known failures
are not hidden by an array's pending tasks. Completed jobs hide historical wait
reasons and routine `exit=0:0` lines in the normal table; `--details` retains them.
The resource/time limit is available in details. Pending walltime is not displayed
as time remaining or a prediction of when a job will start.

Tables fit the terminal (120 columns when redirected); `--width 80` selects a
width explicitly. Long cells are abbreviated with a pointer to `--details` or
`--json`. Details are deliberately unabridged. Summary details also show saved
timestamps and exact paths to distinguish identically named runs.

For execution evidence, use [logs](logs.md) or fetching. For a multi-machine
campaign use [campaign inspect/fetch](campaigns.md); `asl status` selects ordinary
single-machine runs.
