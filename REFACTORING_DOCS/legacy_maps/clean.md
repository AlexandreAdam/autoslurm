# Clean Flow

This chart shows how the current clean command decides what is inactive or
terminal before deleting snapshot files.

```mermaid
flowchart TD
    A[autoslurm clean] --> B[apps/clean.py: main]
    B --> C[_build_parser]
    B --> D[_resolve_target_rows]
    B --> E[save_load_jobs.bundle_snapshots]
    B --> F[save_load_jobs.inactive_bundle_snapshots]
    B --> G[save_load_jobs.all_bundle_snapshots]
    B --> H[save_load_jobs.load_bundle_from_path]
    B --> I[status.job_status_texts]
    B --> J[status.FAILED_STATES]
    B --> K[_render_table]

    D --> E
    F --> L[save_load_jobs._stale_snapshots]
    G --> M[save_load_jobs._all_snapshot_entries]
    H --> N[load and validate bundle JSON]
    I --> O[status._fetch_statuses_for_job_ids]
    O --> P[squeue]
    O --> Q[sacct]

    B --> R[pathlib.Path.unlink]
```

## Main Dependencies

- `apps/clean.py` owns the CLI and selection logic.
- `save_load_jobs.py` provides snapshot classification and visibility policy.
- `status.py` is consulted to classify submitted jobs as failed or cancelled.
- `squeue` and `sacct` can still influence the clean classification path.

