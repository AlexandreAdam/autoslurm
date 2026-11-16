# Understand a job through its logs

AutoSlurm brings scheduler evidence and execution logs together so you or an
agent can investigate a job without rediscovering its cluster paths. Scientific
datasets and results stay with the application. A completed scheduler job still
needs application checks to establish scientific success.

## Fetch a run for investigation

`asl fetch` brings together the run's submission records, current scheduler
status and bounded log excerpts. Use it after a lost submission response, or
before taking execution evidence offline:

```sh
asl status
asl fetch 1
asl fetch 1 --job 2 --task 7
asl fetch study --tail 100
asl fetch 1 --cached
```

It uses the same selectors as `asl logs`, including `--array` expanded rows,
history/date, ranges, `--latest`, exact `--bundle-file` and `--receipt`. A bare
`asl fetch` shows help; `asl fetch --view --cached` lists local runs.

For fresh fetches, AutoSlurm first updates only the submission receipts already
linked to the selected tracking snapshots. This can recover accepted scheduler
IDs after a lost response, before querying status or locating logs. It then uses
the existing inspection pipeline, saving observations and excerpts into the
existing local caches. It never submits/retries jobs, discovers receipts by
bundle name or fetches scientific results. A planned bundle without a linked
submission stays unsubmitted. Job/task filters restrict logs; receipt/status
refresh stays at run level, and file/byte limits apply per run.

```python
from autoslurm import fetch_run

view = fetch_run(receipt_path=receipt_path, job_name="fit", task_index=7,
                 tail=40, max_log_bytes=65536, max_logs=20)
# Keep partial evidence and inspect errors before interpreting missing data.
for error in view["errors"]:
    print(error["source"], error["message"])
offline = fetch_run(receipt_path=receipt_path, refresh=False)
```

ACP action `fetch_run` accepts the same exact selectors and bounds. Its result
is the inspection object, with partial failures in `result.errors`; protocol
`status: success` alone does not establish that every source was available.
Python likewise returns useful partial evidence. The CLI prints that evidence
and exits 1 for collection errors; `--json` retains the structured result.

Execution-receipt reads use one exact recorded path, the same standalone regular-
file reader as logs, a 1 MiB limit and a 30-second timeout. Remote reads require
`python3`, without installing AutoSlurm remotely. Malformed/oversized/changing,
missing or unreadable receipts and failed transport preserve known IDs. Readable
logs remain usable even when receipts or scheduler observations fail. A local
persistence failure retains recovered IDs in the returned evidence, with an
explicit error; do not assume they were saved successfully.

`--cached` never refreshes receipts, projects snapshots, queries the scheduler or
reads source logs. It reads local saved records/caches, marks excerpts stale and
reports `not_cached` when absent. Fetching saves bounded excerpts, not complete
`.out` files or an exported directory. Limits below apply to both commands.

`asl sync` remains the older whole-directory mirror of jobs/scripts/out. It can
transfer full large logs and does not include submission receipts. Use `asl fetch`
for selected, bounded execution evidence; sync is not an equivalent bounded
fetch. Changing that legacy mirror is separate work.

## Select a run and read

Use the same indices as `asl status`; no paths are needed:

```sh
asl status                         # list bundles
asl status 1                       # show jobs in bundle 1
asl logs 1 --job 2                  # logs for job row 2
asl logs 1 --job 2 --task 7         # exact Slurm array task 7 of that job
asl status 1 --array                # show expanded array-task rows
asl logs 1 --array --job 5          # logs for expanded row 5
```

Bundle and displayed job row indices start at 1. `--task` uses the actual Slurm
array index, which may start at 0 or be sparse. Use the same `--array` filters
when moving from the status table to logs. `--array 2-4` selects those task
indices before log-file limits apply; ordinary non-array jobs remain included,
as in status. `--job` also accepts a job name.

Bundle names, ranges, history and latest selection work too:

```sh
asl logs study --job fit --tail 100
asl logs 1-2
asl logs study --date 2026-11-12 --job fit
asl logs --latest --job fit
asl logs --view                     # same bundle list as asl status
```

Indices follow the current status visibility filter and ordering, so they can
move as runs are added. For a durable agent handoff, keep the exact submission
snapshot or receipt returned during submission; these selectors remain supported:

```sh
asl logs --bundle-file /absolute/saved/run.json
asl logs --receipt /absolute/local/receipt.json --job fit --task 2 --stream stderr
asl logs --receipt /absolute/local/receipt.json --json
```

The command reads fresh status and log excerpts by default. It shows job/task
IDs, scheduler state, exit code and reason alongside the recorded stdout/stderr
paths. Missing scheduler details stay unknown. A failed job with readable
evidence is a successful inspection; errors collecting evidence produce an error
exit status while retaining the available information. With no arguments the
command shows help. Browse saved bundles through `asl status`, `asl logs --view`,
`asl inspect` or `list_runs`. Numeric job selection requires one selected bundle;
multiple bundles use one batched scheduler observation. The JSON result is an
object for one run and a list for multiple runs, retaining exact bundle paths.

An application agent can use the same evidence directly:

```python
from autoslurm import inspect_logs

view = inspect_logs(receipt_path=receipt_path, job_name="fit", task_index=2,
                    stream="stderr", tail=40, max_log_bytes=65536, max_logs=20)
```

Use one `bundle_path` or `receipt_path`, never both. `view["jobs"]` carries
scheduler/task evidence; `view["logs"]` carries excerpts and their paths/times;
`view["errors"]` explains unavailable evidence. Existing `inspect_bundle` with
`include_logs=True` and ACP `inspect_run` use the same pipeline.

## Bounded, recorded evidence

Defaults are the last 40 lines within 64 KiB per log, for at most 20 logs per run.
`--tail`, `--max-bytes` and `--max-logs` adjust those limits; the upper bounds are
1 MiB per file and 100 files. Filter by job, array task and stream before those
limits apply. Truncated excerpts and omitted logs are labelled. A very long
final line can fill the byte budget before reaching the requested line count.
AutoSlurm does not download a full log or recursively scan an output directory.

Paths come from saved producing roots, working directories and Slurm output/error
patterns, expanded using the job/task IDs. Editing a profile does not redirect
old logs. By default Slurm merges stderr into stdout: an entry labelled both
streams contains that combined text. `--stream stderr` selects it, but cannot
separate its mixed contents. Separate recorded error paths yield separate entries.

| Log observation | Interpretation |
|---|---|
| `available`, `empty: true` | The file exists and was empty when observed |
| `missing` | None of the recorded candidate paths was found |
| `error` | Permission, transport, malformed response or read failure; availability may be unknown |
| `not_cached` | No matching saved excerpt is available; says nothing about the source file |
| `changed_during_read: true` | The file changed or rotated; refresh for newer evidence |

Available entries retain machine/job/task identity, `path`, `observed_at`,
`freshness`, `size_bytes`, `bytes_read`, `bytes_returned`, `empty` and `truncated`.
`bytes_read` bounds source bytes; `bytes_returned` measures the displayed UTF-8
text after line selection and replacement of invalid characters. Only regular
files are read; special files are rejected without waiting for a writer.

## Inspect without contacting the machine

```sh
asl logs --receipt /absolute/local/receipt.json --cached
asl logs 1 --job 2 --cached
```

Python uses `refresh=False`. Both local and remote inspection then read cached
status/excerpts only, without scheduler or source-log reads. Cached evidence is
stale and retains its original observation time. Raising the limits cannot
recover content that was never saved. A cache-write failure preserves fresh
evidence in the response and reports the error; it does not invent a saved copy.

When an observation fails, retain available tasks/logs and the error rather than
assuming the job succeeded or retrying it. Remote log reads require SSH access
and `python3`, using the [recorded SSH alias](ssh_configuration.md). No helper is
installed remotely. Applications own diagnosis, scientific output validation
and any decision to create another submission.
