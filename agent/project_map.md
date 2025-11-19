# Agent Project Map

This document outlines how an agent should interface with AutoSlurm programmatically and via the CLI. Focus is on scheduling and submitting jobs—configuration details (paths, SSH keys) are handled elsewhere.

## Python API usage

### Scheduling jobs

Use `autoslurm.schedule_job(job, bundle_name, append=False)` to write job definitions into the internal storage. A job dict includes:

- `name`: unique identifier for the job.
- `script`: the application entry point or script name you want to run.
- `script_args`: dict of CLI arguments parsed from the target script (`--arg=value` style).
- `slurm`: dict of SBATCH directives (`time`, `mem`, `cpus_per_task`, `gres`, etc.).
- `dependencies`: optional list of job names this job depends on.
- `pre_commands`: optional list of shell commands to run before the job.

Example job:

```python
from autoslurm.save_load_jobs import schedule_job

job = {
    "name": "analysis",
    "script": "stats-pipeline",
    "script_args": {"input": "results.csv", "alpha": 0.05},
    "slurm": {"time": "00:45:00", "mem": "4G", "cpus_per_task": 2},
}

schedule_job(job, bundle_name="analytics", append=True)
```

`append=True` adds the job to an existing bundle (module will write to `jobs/<bundle>_*.json`). Omitting append creates a new bundle file.

### Submitting jobs

Call `autoslurm.submit_jobs(bundle_name, machine=<machine_name>, machine_overrides=...)` once all jobs are staged. Pass the machine name stored in `~/.autoslurmconfig` (defaults to the configured default), and optionally override the env/SLURM details or SSH info via `machine_overrides`.

Dependencies are embedded in the job structure (via the `dependencies` key). AutoSlurm rewrites the generated SLURM scripts with proper `#SBATCH --dependency` lines before submission.

## CLI usage

### Scheduling via `autoslurm-schedule`

- `autoslurm-schedule <script>` schedules a job or appends it to a bundle. It introspects `<script>` (or a registered entry point) by running `--help` and parsing the available CLI arguments.
- Application arguments follow the SLURM options; AutoSlurm collects everything it doesn't recognize and stores it in the job definition.
- Use `--bundle <name>` to group multiple jobs, `--append` to add to an existing bundle, `--dependencies <job1> <job2>` to declare prerequisites, and `--pre-commands` to execute shell commands before the main script.
- SLURM flags (e.g., `--time`, `--mem`, `--gres`, `--cpus_per_task`) specify resource requests.
- Use `--submit` to schedule and immediately submit the bundle, optionally with `--machine` to target a named machine from the config.

Example command:

```bash
autoslurm-schedule train-model \
  --bundle nightly-training \
  --time 06:00:00 --gres gpu:1 --cpus_per_task 8 --mem 48G \
  --data-path /shared/datasets/train.json \
  --epochs 40 --lr 5e-4 --seed 42
```

### Submitting via `autoslurm-submit`

- After scheduling (possibly across multiple bundles), run `autoslurm-submit <bundle>` to dispatch the jobs either locally or remotely.
- You can override machine parameters (hostname/hosturl/username/key_path/env_command/slurm_account) via CLI flags when the stored configuration is insufficient.
- The CLI uploads the generated SLURM scripts, runs `sbatch`, and tracks the returned job IDs inside the bundle JSON.

### Handling dependencies & bundles

- Each job describes dependencies; AutoSlurm automatically rewrites the SLURM script with `--dependency=afterok:<parent_ids>` so you don’t need to manage job IDs yourself.
- Bundles are JSON files in the internal storage. Add jobs with `--append` or the Python `schedule_job` helper, then submit once all dependencies are captured.
