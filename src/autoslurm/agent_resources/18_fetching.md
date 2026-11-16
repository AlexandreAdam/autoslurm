# Fetch execution evidence

Use fetch_run to refresh linked execution receipts before scheduler status and
bounded logs. This can recover accepted IDs after a lost submission response.

```python
from autoslurm import fetch_run
view = fetch_run(receipt_path=receipt_path, job_name="fit", task_index=7,
                 stream="both", tail=40, max_log_bytes=65536, max_logs=20)
offline = fetch_run(receipt_path=receipt_path, refresh=False)
```

Select exactly one local tracking bundle_path or receipt_path. Only validated
receipt links belonging to that exact snapshot are refreshed, using recorded
producing paths/transport. No receipt guessing by bundle name or profile fallback
occurs. A draft without a linked submission remains a draft.

The result is the existing inspection object: jobs/tasks/status/reasons/exit
codes, submissions, logs, errors, times and freshness. Check errors/freshness
before interpreting results. A receipt failure preserves known IDs and readable
logs. Newly observed IDs remain in the response even if local receipt/projection
persistence fails; preserve them in the client handoff and do not claim they
were saved. Fetch failure is not scheduler rejection or scientific failure.
Never resubmit automatically because fetching failed.

Receipt reads select one regular file, capped at 1 MiB/30 seconds. Remote reads
require python3 without a remote AutoSlurm install. Missing/unreadable/nonregular/
changing/oversized/malformed records and transport/launch/timeout failures carry
shared diagnostics. Arbitrary remote output is not copied into error messages.
Log defaults remain 40 lines, 64 KiB/file and 20 files/run; hard bounds are
1 MiB/file and 100 files/run. Filters precede bounds; omissions/truncation stay
explicit. Job/task filters restrict logs; receipt/status refresh is run-level.
Only existing observation/excerpt caches are written; no export tree is created.

refresh=False reads local records/caches only: no execution-receipt refresh,
scheduler/source-log reads, tracking projection or cache writes. Cached excerpts
remain stale with their times; absent excerpts are not_cached. Do not silently
refresh offline.

```sh
asl fetch 1
asl fetch 1 --job 2 --task 7
asl fetch 1 --array --job 5
asl fetch study --tail 100
asl fetch --receipt /absolute/local/receipt.json --json
asl fetch 1 --cached
asl fetch --view --cached
```

Selectors match asl status/logs, including ranges/history/latest. Keep exact
references in durable handoffs because row indices change. Bare fetch shows
help. CLI prints partial text/JSON and exits 1 for collection errors; a scheduler
FAILED state alone is not a failed fetch. ACP action fetch_run accepts the same
Python selectors/options; inspect result.errors even when status is success.
inspect_logs/asl logs retain their existing behavior without receipt refresh.

Scientific results/datasets remain application-owned. No recursive output scan,
full-log download, job mutation, submission retry or environment setup runs.
Legacy asl sync copies whole jobs/slurm/out directories, including full logs,
and omits receipts; it is not bounded fetching. Mirror policy and cluster-only
receipt discovery are separate work. Regressions use mocked SSH/Slurm and exact
standalone workers against temporary records, covering recovery, partial
failures, bounds/identity, sparse arrays and public/cached parity.
