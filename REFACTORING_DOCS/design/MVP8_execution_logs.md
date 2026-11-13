# MVP8 Execution logs and failure evidence

## Status

Complete locally on dev, 2026-11-12; actual cluster validation remains deferred.
FIX.LOGS.1 (2026-11-13) adds terminal index navigation; see the amendment below.
The user confirmed execution-evidence-only scope; implementation choices below
fulfil that scope without introducing a new persisted run format.

## Scope

The user clarified that retrieval belongs to AutoSlurm's own execution evidence:
job stdout/stderr, Slurm `.out` files, status, reasons and exit codes. Application
results/datasets stay application-owned. This supersedes the proposed generic
result download, file-type allowlist and scientific-output size rules.

Reuse `inspection`, `inspection_artifacts`, `log_files`, `InspectionCache` and
recorded producing metadata. Add a clear public `inspect_logs` operation and
make `asl logs` read logs by default. Do not add a second inspection engine.

## Interface

```sh
asl status 1 --array
asl logs 1 --array --job 5
asl logs 1 --job 2 --task 7
asl logs --bundle-file /path/to/saved-submission.json --job fit --task 2
asl logs --receipt /path/to/receipt.json --job fit --stream stderr --json
asl logs --bundle-file /path/to/saved-submission.json --cached
```

`inspect_logs(bundle_path=..., job_name=..., task_index=..., stream="stderr")`
returns the shared inspection object: scheduler/task states and reasons/exit
codes alongside log entries. Default fresh reads; `refresh=False` reads cached
evidence with no scheduler/source-log access. Existing inspect/ACP operations
use the same reader and optional stream selection.

Select only recorded stdout/stderr patterns and their task/job ID expansions.
No arbitrary path or directory selector is exposed. Merged output is explicitly
labelled as containing both streams. Existing limits remain 40 lines, 64 KiB per
file and 20 files by default (at most 1 MiB/file and 100 files). These limit log
excerpts; the underlying log may be large. Omissions/truncation are explicit.
There is no recursive scanning, dataset filtering, full-log copy or job retry.

## Robustness

One standard-library regular-file reader handles local and remote logs. Open
special files nonblocking and reject them. Use a stable file descriptor and a
bounded read at an observed end offset. Report concurrent change/rotation rather
than claiming an immutable snapshot. Empty files are available and empty; missing
paths differ from permission/read errors and failed transport. Keep paths, job/
task identity, observation time, returned byte count and freshness in evidence.

SSH sends only the reader source through stdin using the shared adapter, without
remote AutoSlurm installation or copied helpers. Validate bounds/response IDs,
encoded lengths and sizes; preserve good per-file evidence when another entry
is missing/failed. Use recorded aliases/paths after configuration edits. Cache
failures cannot discard live evidence; cached reads stay marked stale and never
silently refresh. Deduplicate repeated candidate paths in one SSH read.

## Verification

Mock Slurm/SSH and temporary local files only. Cover the exact stdin probe,
merged/custom/array paths, stream selection before limits, empty/missing/permission/
special-file reads, changing files, malformed/oversized replies, unavailable SSH,
cached local/remote reads, CLI/API equivalence and previous scientific workflows.
Record actual results here and in PLAN at closure. No live cluster action.

## Completion evidence

562 full offline tests passed in 5.58 s, 38 expected collision warnings;
`.development/test-runs/execution-logs-final.xml`. Twenty net new cases cover
the direct CLI/API/ACP boundary, merged/separate streams, empty/missing/errors,
regular-file rejection of FIFOs/directories, bounded 1 GiB sparse-file reads,
concurrent growth/rotation, stream selection before limits, malformed/bounded
responses and cache-write/no-source-read behavior. Existing exact-SSH-payload,
array, receipt, scientific reference and submission cases pass, including the
separately completed FIX.SSH.1 sharing/socket checks.

A clean temporary-source wheel was built offline, installed into a disposable
target, and passed isolated public API, reader, entry-point and help smoke checks.
Artifact `.development/artifacts/mvp8/autoslurm-0.1.0-py3-none-any.whl`, SHA256
`9b3e5c18e04f3964fdb8ff0c2eabe4e55e9682f449a23ebe099b0179d0c634d4`.
Base Conda imports main and `asl logs --help` exposes the new command immediately.
The standalone `autoslurm-logs` entry point is corrected for new installations;
existing entry-point wrappers require reinstalling to change, so use `asl logs`
in the current base environment. No base reinstall was performed. Rollback source
is clean at 33bcbd3. No actual SSH, Slurm, scientific transfer, remote installation,
daily configuration mutation or deployment occurred. Task prefix `MVP8:`, local
milestone tag `mvp8`; push the completed dev commit under the working agreement.

## Terminal navigation amendment (FIX.LOGS.1, 2026-11-13)

The user requires the simple navigation already available in status/inspect,
without typing file paths. `asl logs` now accepts the shared visible bundle
name/index/range policy, nearest-date/component selectors, latest selection,
and `--view` for the status bundle list. `--job` accepts a name or one-based row
index; `--array` uses expanded declared-task rows and optional task/range filters.
`--task` (alias `--array-task`) selects the actual Slurm task index, including
sparse arrays. Use matching array filters when copying a display row from status.
Job selection requires one exact run, resolved before observation. Contradictory
selectors fail instead of silently choosing another job/task. Empty command
still shows help. Names/indices can move; saved handoffs keep exact references.

The job-row mapping was extracted from inspect into `apps/inspection_selection`
and reused by both CLIs. Status continues to own shared bundle/date/range parsing.
One inspection call batches scheduler observations across multiple selected runs.
An optional ephemeral `ArtifactRequest.task_indices` restricts resolved array
tasks before the existing log reader applies file limits; ordinary jobs remain
visible under array filters, matching status. This also fixes inspect's log
filtering and preserves an explicit task alongside a numeric unexpanded job row.
No new persisted format or alternate retrieval engine. One-run JSON stays an
object; multi-run JSON is a list retaining exact bundle paths. Bounds remain
per run; cached reads never query scheduler/source logs.

Verification: 623 full offline tests passed in 10.38 s, 40 expected collision
warnings; `.development/test-runs/log-navigation.xml`. Thirty new cases cover
bundle name/index/latest/range/history identity, ordinary/expanded/sparse rows,
task aliases, mixed ordinary/array filtering, bounds after selection, invalid
selectors before commands, batched queries, cached navigation/listing and the
shared inspect regressions. The first full run exposed ANSI color in a test's
table assertion; the assertion now strips color before checking row identity.

Clean temporary-source wheel install and indexed/expanded-array/cached navigation
smoke passed. Artifact `.development/artifacts/log-navigation/autoslurm-0.1.0-py3-none-any.whl`,
SHA256 `af7088345b15a3205eb6d9e723f39a0ca960e5aadda11862f8453c7e97693e43`.
No live cluster commands, daily configuration/tracking mutation, package install
into base Conda or rollback source change. Existing base `asl` imports active
dev source; no entry-point reinstall is needed.
