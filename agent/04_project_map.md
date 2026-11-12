# Public workflow map

The development MVP3 boundary is `01_client_workflow.md`. Public Python imports
come from `autoslurm`; do not integrate through private backend modules or write
tracking JSON directly. The pinned stable installation retains its earlier API.

| Stage | Supported surface | Durable result |
|---|---|---|
| Describe work | `save_bundle`, `schedule_job` | Exact planned path and saved job names |
| Check paths/scripts | `preview_bundle(path, machine=...)` | Resolved producing paths and script text; no submission |
| Dispatch once | `submit_jobs(..., bundle_path=path)` | Receipt, or `SubmissionError.receipt` |
| Rediscover | `list_runs`, `list_submissions` | Exact local run/receipt references |
| Inspect acceptance | `load_submission`, explicit `refresh_submission` | Known accepted IDs, partial/rejected/uncertain outcomes |
| Inspect execution | `inspect_bundle`, `inspect_bundles` | Shared tasks/state, source/time/errors and optional bounded logs |
| Locate results | `recorded_execution`, `resolve_results_path`, `path_exists` | Producing roots and paths after profile edits |
| Agent tools | `execute_acp`, `action_definitions`, `agent_context` | Structured actions and current guidance |

## Client responsibilities

Expose an installed application command, explicit inputs, a small smoke mode,
nonzero failure exits and independent shard outputs. A thin array adapter may
read `SLURM_ARRAY_TASK_ID`. Reducers validate all expected shards and their
compatibility. Numerical routines do not need AutoSlurm imports.

Declare project-relative `input_args` and `working_directory`, results-relative
`output_dir`/`path_args`, and Slurm resources. AutoSlurm resolves machine roots;
the application handles paths inside opaque scientific configuration files.
Prepare software and inputs before running; compute jobs do no installation/Git
work. Use fresh output namespaces and keep scientific validation application-owned.

## Ownership inside AutoSlurm

For maintainers, the active dependency flow is:

```text
Python / CLI / ACP -> inspection -> scheduler (queue/accounting)
                         |      -> array_status (identity and aggregation)
                         |      -> log_files (exact bounded tails)
                         |      -> saved bundles + local submission receipts
                         v
                    status_views / human context
```

Submission remains owned by job_runner and the shared bulk submission driver.
Execution context owns path mapping and saved producing metadata; storage owns
the selected lane root. Inspection writes only observation caches, never saved
run definitions or receipts. Status/context wrappers render shared evidence;
there is no second agent state engine.

Configuration and mutable state live under the selected storage root, not an
assumed home directory. Internal jobs, scripts, outputs, receipts and observation
caches are implementation details. Use returned references and public APIs rather
than reconstructing filenames. `sync` is a broader profile-based storage copy;
exact inspection is the run-specific observation boundary.

Prepared code/input contents are not snapshotted automatically. Scheduler
history can be unavailable; real-cluster validation, automated reconciliation,
scientific retries and complete packaged agent resources remain later work.
