# Current client workflow

Use this recipe with the development installation including MVP1. The pinned
stable installation does not have these additions. Read `00_operating_rules.md`
first; this recipe takes precedence over older examples where their claims
differ. Current repository work is local only: submissions are tested with
mocked Slurm, never a real cluster.

## Identify the installation

Record the interpreter, actual AutoSlurm import path, source revision, selected
machine and resolved storage root. Both local installations report version
0.1.0, so version alone cannot identify them. The repository's
`REFACTORING_DOCS/installation-register.md` records the actual local setup.

Use `AUTOSLURM_STORAGE_ROOT` for every development process. Keep its config,
tracking, logs and results separate from stable storage. Prepared environments
are operator-owned; compute jobs do not install packages, pull Git repositories
or change shared code. One bundle targets one machine.

## Adapt scientific software

Keep computation independent of AutoSlurm. Expose an installed command with
explicit arguments, useful `--help`, a cheap smoke run and nonzero exits for
invalid input or failed computation. A thin adapter may read
`SLURM_ARRAY_TASK_ID`; scientific functions need not know Slurm. Give each shard
a distinct output. A reducer validates all expected shards and their input
compatibility before reporting success.

Client definitions keep paths relative. These are the current bases:

| Field | Base and behavior |
|---|---|
| `script` | Installed application command in the prepared environment |
| `working_directory` | Project-relative directory; defaults to `.` under the machine's absolute `project_root` |
| String arguments named in `input_args` | Required, pre-existing project-relative inputs; resolved under `project_root`, independent of `working_directory` |
| `script_args.output_dir` | Results-relative; AutoSlurm resolves under machine `results_root`, or selected execution storage's `results/` |
| String arguments named in `path_args` | Same results-relative base, for example a reducer's `parts_dir` |
| Undeclared arguments | Passed through; relative paths depend on the established working directory |
| Paths inside application config files | Application-owned; never inspected or rewritten by AutoSlurm |

Configure absolute infrastructure roots once in the selected machine profile;
keep application declarations relative. Project-aware jobs reject absolute paths
and `..` traversal in declared inputs, results and working directories. Use
`working_directory`, not a separate Slurm `chdir`. AutoSlurm validates the project,
working directory and required inputs before writing scripts or submitting.

For example, an operator-prepared remote profile contains these infrastructure
settings (replace them with its real isolated locations):

```json
{
  "hostname": "cluster-development",
  "storage_root": "/cluster/autoslurm-development",
  "project_root": "/cluster/science-project",
  "results_root": "/cluster/science-results",
  "venv_path": "/cluster/prepared-environment",
  "slurm_account": "account"
}
```

Local profiles omit SSH identity and use the process's selected storage root;
legacy local `path` does not override that selection. Set profile roots through
the public configuration API; the interactive editor preserves existing roots.
Custom project-relative Slurm `output` paths need an existing parent directory;
otherwise use the default log destination managed by AutoSlurm.

Inputs must already exist on the selected machine; staging and opaque config
rewriting are not supported. Declare an upstream job's future results in
`path_args`, rather than required pre-existing `input_args`. Use fresh study/output
namespaces for attempts; scientific validity belongs to the client. Legacy jobs
without project context retain their previous absolute-path behavior.

## Save and select an exact definition

In MVP0.3, public `save_bundle` returns the exact saved `Path`. For one job,
`schedule_job` returns `(saved_job, path)`; retain the saved name because append
operations can rename duplicates.

```python
from uuid import uuid4
from autoslurm import save_bundle, load_bundle_from_path

bundle_name = f"study-{uuid4().hex}"
definition = {
    "sample": {
        "name": "sample",
        "script": "science-demo",
        "input_args": ["input_file"],
        "script_args": {
            "mode": "single",
            "input_file": "data/measurements.json",
            "output_dir": f"{bundle_name}/summary",
        },
        "slurm": {"tasks": 1, "cpus_per_task": 1, "mem": "64M", "time": "00:01:00"},
    }
}
planned_path = save_bundle(definition, bundle_name)
jobs, dependencies, saved_date = load_bundle_from_path(planned_path)
```

Record the bundle name, planned path and definition in the client handoff before
submission. Rediscover work with `list_saved_bundles(bundle_name=...)` or ACP
`list_experiments`; load the returned path with `load_bundle_from_path`. Do not
reconstruct filenames, edit tracking JSON or parse terminal rows. Name, `latest`
and index selectors can move. `load_bundle(name, desired_date=...)` selects the
nearest date, as does `submit_jobs(..., date=...)`. Neither is an exact snapshot
selector. `select_bundle_snapshot` owns the shared CLI/name selection policy:
default CLI name/latest selection prefers ready drafts; dated loading selects
the nearest timestamp across saved snapshots.

Before submission, `preview_bundle(planned_path, machine="target")` validates and
returns plain resolved paths and rendered script text without writing scripts or
submitting. A remote preview still contacts the configured machine for root
discovery and batched input validation. Under this repository's local-only scope,
remote interactions must be mocked.

## Submit once and retain evidence

For an already authorized operation in the selected lane, or a mocked test:

```python
from autoslurm import submit_jobs, list_saved_bundles, load_bundle_from_path

submit_jobs(bundle_name, machine="target", bundle_path=planned_path)
observed = []
for entry in list_saved_bundles(bundle_name=bundle_name):
    saved_jobs, _, _ = load_bundle_from_path(entry["path"])
    ids = {job["name"]: job["id"] for job in saved_jobs if job.get("id")}
    if ids:
        observed.append({"path": str(entry["path"]), "date": entry["date"].isoformat(), "ids": ids})
```

Use a unique bundle name and one writer for this bounded recipe. Submission
imports the selected definition into a new tracking snapshot. Record both the
planned reference and actual submission path/date/IDs. `submit_jobs` returns
`None`, not a receipt. Records remain mutable; timestamps have one-second
resolution. Keep the client's own definition/evidence record. This recipe does
not support concurrent writers or provide an immutable attempt store.

The CLI equivalent is `asl submit NAME --bundle-file PATH --machine PROFILE`.
Outside mocked tests it creates real scheduler effects. ACP supports scheduling,
listing, inspection and context gathering; it has no submit action.

An exception or absent ID does not prove rejection. Remote bulk-to-legacy
fallback and incomplete partial-failure records remain until MVP2. Never
automatically retry, erase IDs or resubmit a saved submission. Preserve errors
and known IDs; stop for outcome reconciliation in the same installation.

## Inspect and hand off

`load_bundle_from_path` reads recorded IDs/machine, not fresh scheduler evidence.
`recorded_execution(submission_path, job_name)` reads the job's producing roots,
logical/resolved paths, working directory and transport identity. It does not
discover today's profile. Use
`resolve_results_path(relative, bundle_path=submission_path, job_name=job_name)`
or `path_exists(relative, bundle_path=submission_path, job_name=job_name)` to use
those producing roots/transport even after profile edits. A legacy record without
execution evidence fails explicitly; select its original profile yourself.
These records preserve locations, not immutable code/input contents or scheduler
observations. Status/log readers are consolidated separately in MVP3.

Use the owning installation's `status`/`inspect` for observations. Retain the full
saved timestamp and verify identity: `asl inspect NAME --date FULL_TIMESTAMP
--job JOB_NAME --log --tail 40` bounds the excerpt. Date selection is nearest-date
selection; stop if the recorded snapshot is missing rather than accepting a
neighbor. These commands can query/fetch from the cluster. `sync` currently
skips existing files; do not assume growing logs refreshed. Unified evidence
and refresh fixes remain MVP3.

A fresh agent needs lane/interpreter/import/revision, machine/root, client input
and output namespace, exact planned and submission references, job/task IDs,
actions already taken, observation time/errors and next safe action. Missing
accounting rows/logs mean unknown evidence, not successful science. Keep excerpts
bounded and reference full artifacts. Exclude credentials.

`examples/reference_client/` demonstrates one job and four shards followed by a
reducer. Its application does not import AutoSlurm; tests exercise this recipe
with temporary state and mocked submission commands.
