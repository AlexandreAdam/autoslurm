# Cleaning saved bundles

## Cancelling active jobs

`asl cancel 3` previews cancellable jobs in the selected saved run;
`asl cancel 3 --yes` sends the cancellation requests. Named local profiles such
as `rusty-local` use local `scancel`. Runs with saved execution metadata use
their recorded producing transport even if today's profile changed. Legacy
runs without that metadata use the named current profile. Missing profiles or
inconsistent recorded transports stop dispatch before any cancellation; there
is no local/remote fallback. A later command failure can still follow an earlier
accepted request when multiple targets are selected.
Inspect status afterwards to confirm the scheduler's final state. Cancellation
does not delete bundle records or scientific results.

## Removing saved records

Use cleanup to prune local saved bundle records after runs finish:

```sh
asl clean --scope completed          # Preview successful runs
asl clean --scope completed --yes    # Remove those local bundle JSON files
asl clean --scope terminal           # Preview all finished outcomes, including mixed results
asl clean 2 --scope completed        # Restrict the completed scope to status index 2
```

| Scope | Selects |
|---|---|
| `inactive` (default) | Superseded snapshots hidden by the active visibility policy |
| `unsubmitted` | Snapshots with zero recorded submitted jobs; tracked attempts stay protected |
| `completed` | Every job submitted and every task observed completed successfully |
| `failed` | Every submitted task failed, excluding cancellation |
| `cancelled` | Every submitted task cancelled |
| `terminal` | Every submitted job/task finished, including mixed completed/failed/cancelled results |
| `all` | Union of inactive, unsubmitted and terminal; includes successful runs |

Terminal scopes query fresh scheduler evidence using the recorded producing
machine. Unknown/missing tasks, failed observations and running/pending jobs
prevent terminal cleanup. An aggregate array failure alone is insufficient.
Tracked runs also require readable, consistent local receipts with a settled
`submitted` outcome; partial/uncertain/submitting attempts are retained even if
known IDs finished. No receipt is fetched remotely or refreshed by cleanup.
Legacy terminal scopes concern submitted work; `completed` additionally requires
that no job was left unsubmitted. Changed snapshots are retained after observation.

The command previews by default. Review it, then rerun with `--yes`; selection is
recomputed on each invocation. Terminal scopes constrain explicit indices/ranges.
The older index-only behavior remains for other scopes, including protection of
receipt-bearing snapshots. Default inactive and unsubmitted cleanup never query
the scheduler. Cleanup needs working cluster access for terminal scopes.

**Only the selected local bundle JSON files are deleted.** Separate receipts,
observation/log caches, generated scripts, cluster files and scientific results
remain. Deletion removes the bundle from normal status/index/log navigation;
a retained receipt does not restore its definition. Save needed definitions or
inspect logs before cleaning. This is record cleanup, not disk-space reclamation
for datasets, cancellation, remote synchronization or automatic history migration.
