# Task: Inspect Experiments

Read `00_operating_rules.md` and `01_client_workflow.md` from the installation
that owns the run. Development through MVP8 supports this contract; stable remains
pinned to its earlier behavior.

1. Discover local references with `list_runs(bundle_name=...)` or ACP
   `{"action":"list_runs","bundle":"study"}`. Preserve exact `bundle_path`.
   Use `list_submissions` when the handoff has a submission identity.
2. Inspect with `inspect_bundle(bundle_path)` or
   `inspect_bundle(receipt_path=...)`; ACP `inspect_run` takes the same selectors.
   Default refresh queries the producing scheduler; `refresh: false` makes no
   network calls and labels cached evidence stale/never.
3. Read `freshness`, `errors`, `observed_at`, submission outcomes and each task's
   state/source/reason/exit. Missing rows mean unknown. Parent failure does not
   identify which missing task failed. Scheduler completion does not validate
   scientific output.
4. Request bounded logs only for relevant jobs/tasks using `include_logs`,
   `job_name`, `task_index`, `stream`, `tail`, `max_log_bytes`, `max_logs`. Keep full log
   paths in the handoff; report missing, not_cached, omitted and error states.
   Explicit refresh reads growing logs at recorded producing locations.
5. Retain exact references, job/task IDs, last evidence/time/errors, actions
   already taken and the next safe operation. Never retry an uncertain submit.

Terminal equivalents: `asl status --bundle-file PATH --array`,
`asl inspect --receipt PATH --json`, and
`asl logs --receipt PATH --job JOB --stream stderr --tail 40`.
Name/date/index conveniences resolve to an exact snapshot but can move between
sessions; do not retain them as identity. Date selection is nearest-date.

`inspect_experiments` and `experiment_context` remain human renderers with
scripts and bounded logs. Do not parse their Markdown as a programmatic API or
run them remotely as an inspection fallback. `inspect_run` is the structured
boundary. `gather_context` with `task: "inspect_run"` loads this contract.

For direct log inspection use public `inspect_logs(bundle_path=...)` or
`inspect_logs(receipt_path=...)`, optionally selecting job/task/stream. Fresh is
the default; `refresh=False` / CLI `--cached` reads cached status and excerpts
without scheduler or source-log reads on either machine. Preserve freshness,
errors, missing/empty/not_cached distinctions and partial observations. Merged
streams stay merged. Honor byte/line/file limits and explicit truncation/omission.
The reader rejects special files and flags changes during a read; refresh rather
than claiming an immutable snapshot. Retrieve execution logs only, never scan or
copy application datasets/results. See [client recipe](01_client_workflow.md).
