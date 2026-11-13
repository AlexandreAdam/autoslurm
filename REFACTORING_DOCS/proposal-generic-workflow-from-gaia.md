# Proposal: fold gaia-asteroseismology's generic workflow layer into autoslurm

*Written 2026-11-13 from the gaia-asteroseismology side, after its first cluster runs (E0 passed on rusty).
For an agent planning autoslurm work. A proposal, not a decision: Alexandre decides what moves and when.*

## Why
gaia-asteroseismology built a workflow layer on top of autoslurm: about 1,800 lines in
`src/gaia_asteroseismology/jobs/` and `src/gaia_asteroseismology/tasks/`. Only about 400 of them are about gaia
(its pipeline tasks, a JAX/GPU environment check, its folder layout). The rest is generic machinery every future
project would rebuild. Moving it into autoslurm makes it reusable, and makes autoslurm safer for agents by
default (look before submitting, resources always shown, offline planning).

The machinery splits by **where it runs**:

1. **Submit side** (laptop or login node: bundles, receipts, profiles). It belongs **in autoslurm itself**.
2. **Node side** (inside the job, in the project's environment). It must not depend on the scheduler, so it
   belongs in a **dependency-free subpackage** (e.g. `autoslurm.tasks`, importable without the rest) or a
   sibling package.

Before designing, check what autoslurm already has that overlaps: `dependency_graph`, `topological_levels`,
`submit_dag_by_levels`, `inspect_bundle(s)`, `list_runs`, `experiment_context`, `software_expectations`,
`attach_software_manifest`, `update_software`. Extend those rather than duplicate them.

## Part 1: into autoslurm (submit side)
All of these read only the bundle, the receipts and the profile, never the project's code.

### 1.1 Resource view of a bundle
- **What:** a table per job: tasks (array size and concurrency cap), partition, constraint, GPUs/task, CPUs/task,
  memory/task, time/task, dependencies. Then totals: "N jobs, M tasks; worst case X GPU-hours, Y CPU-hours",
  where worst case is Σ tasks × GPUs × time and Σ tasks × ntasks × CPUs × time.
- **From gaia:** `jobs/bundles.py`: `hours`, `gpus`, `array_tasks`, `resource_view`, `format_resource_view`,
  `read_bundle`.
- **Integration:** `autoslurm.resource_view(bundle) -> dict` plus a formatter; `asl show --resources BUNDLE`.
  Printed by default before any submission. Optional: a per-profile GPU-hour cap that refuses larger bundles
  unless `--force`.

### 1.2 Look before submitting
- **What:** before anything is sent (including the software pull), print the bundle's context and its resource
  view, then ask `Submit? [y/N]`. `--yes` skips the question for scripted use. Declining sends nothing.
- **Context** is a short markdown file saved next to the bundle: purpose, stages, planned code, machine. In gaia
  it is written from the study's docstring.
- **From gaia:** `jobs/commands.py`: `write_context`, `show`, `_confirm_after_printing`, `NotConfirmed`, and the
  `confirm=` hook of `submit`/`resubmit`.
- **Integration:** `save_bundle(..., context=str | None)` stores `<bundle>.context.md`.
  `submit_jobs(..., confirm=callable | None)`, with the CLI's `asl submit --context --resources [--yes]`.

### 1.3 Software preparation inside submit
- **What:** `submit` runs `update_software` first, unless `--no-update`. Around it, gaia adds three generic checks:
  - warn before submitting if the local checkout has uncommitted changes or unpushed commits (the cluster runs the
    pushed `main`);
  - **stop** if the pull changed the package's declared dependencies (a hash of `[project].dependencies` in
    `pyproject.toml` before and after; extras ignored). The `--no-deps` install would not bring them, so the user
    must install them first;
  - record the before and after commits and the planned commit in the run record.
- **From gaia:** `jobs/commands.py`: `code_warnings`, `declared_dependencies`, `update_code`, `updates_code`,
  `CodeUpdateStopped`; `tasks/provenance.py`: `requirements_hash`, `dependency_hash`,
  `installed_dependency_hash`.
- **Integration:** fold into `update_software` (or a `prepare_software` step that submit calls). The project's
  pyproject path comes from the profile's `software_root/<project>`. Pairs with two fixes found on rusty:
  - the editable refresh should build with isolation (drop `--no-build-isolation --no-index`, keep `--no-deps`),
    and show pip's last lines when it fails;
  - job scripts should render `env_command` (module loads) **and** `source <venv_path>/bin/activate` when both
    are set. Today `venv_path` silently wins.

### 1.4 Run records
- **What:** one JSON per run (by name) grouping everything about it: the planned bundle, each submission (label,
  bundle path, receipt), code updates, fetches, warnings, the resource view, the context file. A later session
  finds the run by name. Paths of the run's own files are stored relative to the run's folder.
- **From gaia:** `jobs/commands.py`: `record_path`, `load_record`, `save_record`, `run_path`, and the fields
  written by `plan`, `submit` and `fetch`.
- **Integration:** extend `list_runs` / receipts into `autoslurm.runs`: `create_run(name, bundle, context)`,
  `load_run(name)`, `record_submission(...)`. Each project gets a folder for its runs (configurable;
  `data/runs/` in gaia).

### 1.5 Status and resubmit
- **What:**
  - Status per stage and array index, from Slurm through the receipts (COMPLETED counts as done), with log tails of
    failed indices on request.
  - Resubmit builds a bundle of only the failed or never-run indices plus every stage downstream of them, drops
    dependencies on stages already done, submits it as "resubmit N", and refuses when nothing failed.
- **From gaia:** `jobs/commands.py`: `status`, `_log_tail`, `resubmit`; `jobs/bundles.py`: `bundle(...,
  stages=, indices=)`, `array_spec`.
- **Integration:** `inspect_bundle` already gives states; add `failed_indices(run)` and
  `resubmission_bundle(bundle, failed) -> bundle`, which is pure graph work on the bundle's `dependencies` and
  `slurm.array`. Then `asl resubmit RUN --context --resources`.

### 1.6 Fetch (G1) and offline plan (G8)
Both are already in `requirements-gaia-asteroseismology.md`:
- **Fetch (G1):** bring a filtered subtree of `results_root` back to the laptop. gaia's `fetch` only works for
  local profiles today.
- **Offline plan (G8):** planning a bundle for a remote profile must never SSH. Today `resolve_execution_context`,
  `preview_bundle`, `path_exists` and `remote_storage_root_from_config` connect without saying so. gaia avoids
  them and has a test that blocks ssh/rsync/scp during `plan`.

### 1.7 Argument rendering (open, Alexandre is thinking about it)
gaia passes every option by name in `script_args`, so bundles and scripts stay readable. Rendering limits met so far:
- lists are written `--flag a b` (argparse form; Typer needs repeated flags);
- values other than paths are unquoted;
- `False` is omitted.

A per-job `list_style` / `bool_style` and quoting with `shlex.quote` were discussed but **not decided**.

## Part 2: a scheduler-free tasks package (node side)
Runs inside the job. It must import nothing from autoslurm's submit side, so a project's environment can use it on
compute nodes.

- **Runs as data:** `Run(name, stages)` and `Stage(name, task, config, count, resources, depends_on)`. JSON round
  trip, validated graph (dependencies are earlier stages, no cycles). From gaia: `tasks/run_file.py`.
- **Task registry and a generated CLI:** `@task("name")` on a typed function `fn(ctx, *, opt: int = 0, ...)`.
  The registry derives the options from the signature (scalars or Optional; booleans default to False). The CLI
  is generated with one Typer command per task, plus common options (`--run --stage --output-root --index --count
  --planned-code-id --force`). The index defaults to `SLURM_ARRAY_TASK_ID`. Options are checked against the
  signature at plan time. From gaia: `tasks/registry.py`, `tasks/__main__.py`.
- **Idempotent indices and provenance:**
  - `execute` validates and fills the options, computes a stage hash (run, stage, task, count, options), and skips
    an index whose done marker has that hash;
  - it checks installed against declared dependencies, runs the task, and writes `done/<index>.json` (stage hash,
    code id, planned code id, seconds, peak memory, host, Slurm job, the task's returned numbers);
  - `missing_indices` lets reducers refuse partial or mismatched inputs.

  From gaia: `tasks/runner.py`, `tasks/provenance.py`.
- **Generic tasks:** `gather` (a reducer) and `echo` (for tests, with a `fail_once` option to test resubmission).
  From gaia: `tasks/builtin.py`. Also worth generalizing: the compile-seconds and GPU-memory readings in
  `tasks/diagnostics.py` (`compile_clock`, `device_memory`), behind an optional JAX import.
- **The bridge:** `bundle(run, code_id) -> dict` turns a `Run` into an autoslurm bundle (script =
  `<cli> <task>`, named `script_args`, `path_args`, array specs, dependencies). It is the one piece that knows both
  sides; put it in autoslurm's submit side, taking the run as plain data. From gaia: `jobs/bundles.py:bundle`.

## Part 3: what stays in gaia
- The science tasks: `self-challenge-set`, `pipeline-shard`, `pipeline-merge`, `pipeline-summary`
  (`tasks/pipeline.py`).
- The JAX/GPU environment check (`tasks/diagnostics.py`, minus the generic timers).
- Studies (`studies/e*_*.py`) with `run()` and `figures()`, and the folder layout (`jobs/layout.py`).
- `gaia-seismo-jobs` becomes a thin wrapper: load a study, call autoslurm's plan, show, submit, status,
  resubmit, fetch.

## Suggested order
1. **Resource view plus look-before-submit (1.1, 1.2):** small, used on every submission, and makes autoslurm
   safer for any agent.
2. **Run records, then status and resubmit (1.4, 1.5).**
3. **Software preparation with the dependency stop (1.3)**, together with the build-isolation and
   `env_command` fixes.
4. **Fetch and offline plan (1.6):** already tracked as G1 and G8.
5. **The tasks package (Part 2):** best after a second project wants it, so two users shape its interface. gaia
   then deletes its copies (the gaia rule: no shims or aliases; callers updated in the same commit).

## Constraints to keep
These are Alexandre's rules and Flatiron's (see gaia's `CLAUDE.md`, "The cluster"):
- Agents never submit. Every submission shows its resources and asks first.
- No hidden SSH in planning.
- Code lives in home (`software_root`); ceph (`results_root`) holds data only.
- Never install over scicomp's modules.
- Be gentle with ceph metadata (no recursive listing; aggregate small outputs).
- Readable bundles: every argument named, no encoded blobs.

Reference implementation and tests: gaia-asteroseismology at `8eaffec` (`tests/test_jobs.py`,
`tests/test_tasks.py`, `tests/test_e0_run.py`, `tests/test_e1_run.py`). The design history is in
`design/M5d_compute.md` there.
