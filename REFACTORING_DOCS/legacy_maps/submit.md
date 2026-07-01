# Submit Flow

This chart shows the current submission path from the CLI down to the Slurm
and storage helpers.

```mermaid
flowchart TD
    A[autoslurm submit] --> B[apps/submit.py: main]
    B --> C[parse_args]
    B --> D[save_load_jobs: bundle snapshot lookup]
    B --> E[bundle_snapshot_state]
    B --> F[utils.machine_config]
    B --> G[job_runner.submit_jobs]

    G --> H[job_to_slurm.create_slurm_script]
    G --> I[save_load_jobs.load_bundle]
    G --> J[save_load_jobs.save_bundle]
    G --> K[save_load_jobs.update metadata helpers]
    G --> L[run_slurm.ssh_submission_session]
    G --> M[run_slurm.run_slurm_locally]
    G --> N[run_slurm.run_bulk_submit_driver_remotely]
    G --> O[save_load_jobs.transfer_slurms_to_remote]
    G --> P[save_load_jobs.transfer_bundle_to_remote]
    G --> Q[job_dependency.update_slurm_with_dependencies]

    N --> R[remote python -m autoslurm.apps.bulk_submit_driver]
    R --> S[apps/bulk_submit_driver.py: main]
    S --> T[bulk_submit_driver.submit_payload]
    T --> U[bulk_submit.submit_dag_by_levels]
    U --> V[bulk_submit.topological_levels]
    T --> W[subprocess sbatch --parsable]
    W --> X[sbatch]
```

## Main Dependencies

- CLI parsing and bundle selection happen in `apps/submit.py`.
- Job rendering happens in `job_to_slurm.py`.
- Submission transport happens in `run_slurm.py`.
- Dependency ordering and DAG level handling happen in `job_dependency.py` and
  `bulk_submit.py`.
- Remote bulk submission uses the remote Python entrypoint in
  `apps/bulk_submit_driver.py`.

