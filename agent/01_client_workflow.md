# Current client workflow

Use this recipe with the development installation including MVP0.3. The pinned
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
| `script_args.output_dir` | Results-relative; AutoSlurm resolves under machine `results_root`, or selected execution storage's `results/` |
| String arguments named in `path_args` | Same results-relative base, for example a reducer's `parts_dir` |
| Other arguments such as `input_file` | Passed through; relative paths depend on the application working directory |
| Paths inside application config files | Application-owned; never inspected or rewritten by AutoSlurm |

Input staging and a project-root/working-directory contract are MVP1 work. Do
not put input arguments in `path_args` expecting a project-input base. Establish
the working directory and input availability before an operational submission.
The reference test explicitly starts in its application directory. Use fresh
study/output namespaces for attempts; scientific validity belongs to the client.

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
nearest date; `submit_jobs(..., date=...)` is not an exact snapshot selector.

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
