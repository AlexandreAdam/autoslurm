# Status Flow

This chart shows how the current status command reaches from the CLI to the
Slurm query helpers and bundle rendering helpers.

```mermaid
flowchart TD
    A[autoslurm status] --> B[apps/status.py: main]
    B --> C[_build_parser]
    B --> D[_resolve_targets]
    B --> E[_status_rows]
    B --> F[_status_summary_text]
    B --> G[_status_summary_text_batched]

    E --> H[save_load_jobs.bundle_snapshots]
    F --> I[save_load_jobs.load_bundle]
    F --> J[status.job_status_texts]
    G --> K[save_load_jobs.load_bundle]
    G --> L[status._fetch_statuses_and_time_left_for_job_ids]
    G --> M[status_views.bundle_job_rows_from_jobs]
    F --> N[status.infer_bundle_status]

    J --> O[status._fetch_statuses_for_job_ids]
    O --> P[status._fetch_statuses_locally]
    O --> Q[status._fetch_statuses_remotely]
    P --> R[squeue]
    P --> S[sacct]
    Q --> T[ssh]
    Q --> U[squeue]
    Q --> V[sacct]

    L --> W[status._fetch_time_left_for_job_ids]
    W --> X[status._fetch_time_left_locally]
    W --> Y[status._fetch_time_left_remotely]
    X --> R
    Y --> T

    M --> Z[status_views.bundle_jobs_context_from_rows]
```

## Main Dependencies

- `apps/status.py` owns CLI parsing, date selection, and summary formatting.
- `save_load_jobs.py` provides bundle snapshots and bundle loading.
- `status.py` performs the actual Slurm lookups and status inference.
- `status_views.py` renders the bundle/job tables.
- `squeue`, `sacct`, and `ssh` are the live external tools used by the current
  implementation.

