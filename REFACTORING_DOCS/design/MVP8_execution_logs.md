# MVP8 Execution logs and failure evidence

## Status

Complete locally on dev, 2026-11-12; actual cluster validation remains deferred.
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
