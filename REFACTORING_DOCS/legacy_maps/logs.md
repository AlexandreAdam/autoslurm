# Logs Flow

This chart shows how the current logs and inspect commands traverse bundle
snapshots, local output files, and remote fallbacks.

```mermaid
flowchart TD
    A[autoslurm logs] --> B[apps/logs.py: main]
    B --> C[apps/status.py: main]
    B --> D[apps/inspect.py: main]

    D --> E[_build_parser]
    D --> F[_resolve_bundle_target]
    D --> G[_resolve_job_selector]
    D --> H[_resolve_job_row]
    D --> I[_list_job_log_files]
    D --> J[_list_array_task_log_files]
    D --> K[experiment_context.job_context]
    D --> L[experiment_context.latest_log_context]

    G --> M[save_load_jobs.load_bundle]
    F --> N[save_load_jobs.bundle_snapshots]
    H --> O[status_views.bundle_job_rows_from_jobs]
    I --> P[storage.out_dir]
    I --> Q[_log_path_matches_job_id]
    J --> R[experiment_context._array_task_log_job_ids]
    J --> S[_log_path_matches_job_id]

    K --> T[experiment_context._collect_out_logs]
    L --> U[experiment_context._latest_out_log_for_bundle]
    L --> V[experiment_context._latest_out_log_for_job]
    T --> W[experiment_context._fetch_remote_logs_for_job]
    U --> X[save_load_jobs.load_bundle]
    V --> X
    W --> Y[ssh]
    W --> Z[remote python + log parsing]

    Z --> AA[experiment_context._parse_remote_logs]
    V --> AB[experiment_context._array_task_log_job_ids]
    AB --> AC[sacct for JobID -> JobIDRaw mapping]
```

## Main Dependencies

- `apps/logs.py` is only a thin dispatcher.
- `apps/inspect.py` does most of the CLI selection and rendering work.
- `experiment_context.py` handles the log aggregation, fallback fetching, and
  array-task raw-id resolution.
- `save_load_jobs.py` supplies bundle snapshots and saved bundle paths.
- `storage.py` supplies the local output directory.
- `sacct` is used when the code needs to resolve array-task log ids.

