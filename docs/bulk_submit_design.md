# Bulk DAG Submission Design (Internal)

This functionality is internal to AutoSlurm and is **not a user-facing CLI feature**.
Users still interact with `asl submit`; the bulk path is an implementation detail behind the existing CLI surface.

## Goal

Keep dependency correctness while reducing transport overhead by batching submissions at DAG level boundaries.

- Wide graph: one transport call per level.
- Tall graph: still one level per node (dependency-constrained), but same orchestration API.

## Status

- `autoslurm.bulk_submit`: DAG level planner/orchestrator (internal).
- `autoslurm.bulk_submit_driver`: remote execution core using `sbatch --parsable` (internal).
- `autoslurm.apps.bulk_submit_driver`: remote entrypoint wrapper consumed by `submit_jobs` (internal).
- `submit_jobs` remote path now calls the bulk driver first and can fallback to legacy submission.

## API

- `topological_levels(children_by_job) -> list[list[str]]`
- `submit_dag_by_levels(children_by_job, slurm_names, submit_level) -> LevelSubmitResult`

Where:

- `children_by_job` is parent->children adjacency (same shape as AutoSlurm dependency graph).
- `submit_level` is a pluggable callback that can do one remote round-trip for all jobs in one level.

## Mock Usage

```python
from autoslurm.bulk_submit import submit_dag_by_levels

children_by_job = {
    "A": ["D"],
    "B": ["D"],
    "C": ["D"],
    "D": [],
}
slurm_names = {
    "A": "A_20260525.sh",
    "B": "B_20260525.sh",
    "C": "C_20260525.sh",
    "D": "D_20260525.sh",
}

def submit_level(requests):
    # Future integration point:
    # one ssh session/command that runs sbatch --parsable for each request
    # and returns {job_name: job_id}
    return {request.job_name: f"id-{request.job_name}" for request in requests}

result = submit_dag_by_levels(
    children_by_job=children_by_job,
    slurm_names=slurm_names,
    submit_level=submit_level,
)

print(result.levels)       # [['A', 'B', 'C'], ['D']]
print(result.round_trips)  # 2
print(result.job_ids)      # {'A': 'id-A', ...}
```

## Notes

- This design cleanly separates DAG logic from transport logic.
- Future integration should implement a concrete remote `submit_level` callback and preserve existing metadata updates/error handling in `job_runner`.

## Recommended Production Pattern (Local + Remote AutoSlurm)

Use local AutoSlurm as the planner/orchestrator and remote AutoSlurm as the submit executor.

### Why

- Avoid ad-hoc shell command composition for `sbatch` loops.
- Keep dependency planning local where bundle metadata already exists.
- Execute submits remotely in Python with structured input/output.

### Local Responsibilities

1. Load bundle and build dependency graph.
2. Create all SLURM scripts locally.
3. Transfer scripts and bundle metadata to remote storage.
4. Compute levelized DAG using `submit_dag_by_levels`.
5. For each level, call one fixed remote entrypoint (or call one entrypoint for the full DAG).
6. Parse returned job IDs and update local bundle metadata.

### Remote Responsibilities

1. Read payload (JSON) produced by local side:
   - job names
   - script paths
   - parent job names (or precomputed dependency IDs per request)
2. Submit with `sbatch --parsable` using Python `subprocess.run([...])`.
3. Resolve and apply `--dependency=afterok:...` flags as jobs are submitted.
4. Return structured JSON:
   - `job_ids`
   - per-job errors (if any)
   - execution summary

### Security Posture

- Prefer fixed remote Python entrypoints over dynamic `bash -lc` script assembly.
- Pass only structured data files/arguments.
- Use argv lists in subprocess calls, not shell-evaluated command strings.

### Shape Behavior

- Wide DAG: submit many sibling jobs in one remote invocation per level.
- Tall DAG: still one `sbatch` per node logically, but transport overhead is minimized by remote-side execution.
