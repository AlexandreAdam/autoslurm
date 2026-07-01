# Status and Log Workflow Notes

This note captures brittle areas in the current AutoSlurm status/log workflow so
they can be revisited during the next refactor.

## Current Model

`asl status` is derived from Slurm accounting, not from log parsing. For array
jobs it queries Slurm for logical task ids such as `14811217_2` and states such
as `COMPLETED` or `FAILED`.

`asl logs` resolves local `.out` files. On some clusters, successful array task
logs are written under the raw allocated Slurm id, for example:

```text
status id: 14811217_2
raw log id: 14813018
log file: final_lens_sweep_ring-14813018.out
```

This means status and logs must share a reliable mapping from logical array task
ids to raw Slurm ids.

## Brittle Areas

1. Slurm accounting format assumptions

   Status currently depends on `sacct -o JobID,State`. This works on Rorqual
   because `JobID` preserves logical array ids while `JobIDRaw` does not. Other
   Slurm versions/configurations may differ.

2. Status and log lookup use separate Slurm queries

   Status resolves task states separately from log lookup. Log lookup then runs
   another query to map `JobID -> JobIDRaw`. These paths can drift again.

3. Log filename convention

   Log lookup assumes files are named `<job_name>-<slurm-id>.out`, where the id
   may be either logical or raw. If the Slurm output template changes, log
   resolution can silently break.

4. Silent fallbacks hide uncertainty

   Several paths return empty results when `sacct`, SSH, config lookup, or
   remote parsing fails. Status should distinguish "known empty" from "query
   failed" and show a warning/source when accounting is incomplete.

5. Parent-array fallback is lossy

   If Slurm only returns a parent array state, AutoSlurm cannot know task-level
   truth. The UI should expose unknown task counts instead of pretending the
   declared array shape is fully known.

6. Bundle version identity is easy to misread

   Repeated bundle names such as `final_lens_sweep` are normal. Name-only
   commands can resolve to latest/nearest snapshots, so output should make the
   exact timestamp/version highly visible.

## Refactor Target

Create one internal resolved status model and have `status`, `logs`, `inspect`,
and `--list-files` all render from it:

```text
BundleSnapshot
  JobSubmission
    parent_id
    array_spec
    task_records:
      task_index
      logical_id
      raw_id
      state
      exit_code
      job_name
      log_path
```

The Slurm resolver should query a richer set of fields in one place, ideally:

```bash
sacct -n -P -j <ids> -o JobID,JobIDRaw,State,ExitCode,JobName
```

Then the rest of AutoSlurm should consume parsed records instead of re-parsing
Slurm output or guessing log paths independently.

## Suggested Tests

- Recorded `sacct` fixtures for Rorqual-style array output.
- Logical array id to raw log id mapping.
- Repeated bundle names with multiple submitted snapshots.
- Missing/failed `sacct` query shows an explicit unknown/warning state.
- Changed log filename template fails clearly instead of showing unrelated logs.
