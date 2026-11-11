# MVP1 Paths and selection

## Status

Complete locally, 2026-11-11; local closure tag `mvp1`. The user authorized
implementing the next MVP. Follow the
local-only scope and separate development installation in [WORKFLOW](../../WORKFLOW.md).
Existing bundle dictionaries/files remain; no general filesystem or migration
framework is introduced. MVP2 submission fallback and MVP3 status/log work remain
separate.

## Problems

| Problem | Bounded response |
|---|---|
| Relative inputs depend on the submitting directory | Profile `project_root` and job-relative `working_directory`, defaulting to the project root |
| Results/remote roots are re-derived by several paths | One execution context per selected operation, passed through preparation and transport |
| Inputs and outputs need different bases | Job `input_args` names required project-relative input arguments; existing `path_args` names results-relative arguments; `output_dir` is automatic |
| Preview and stored runs can disagree after profile changes | Use the same resolver for preview/rendering; record logical/resolved execution evidence and reuse producing results roots |
| Filename/name/date selection logic can diverge | Keep exact loading as the primitive; share snapshot date and effective job-name helpers with name-based loading |

## Decisions

Routine implementation choices within the authorized MVP follow these contracts:

- **D1 Implemented path bases.** Machine `project_root`, `results_root` and storage roots are infrastructure
  paths, absolute on the selected machine. Application declarations are relative.
  New project-aware jobs reject absolute/traversing path declarations. Legacy
  jobs without project context keep their existing absolute-path behavior.
  Local execution uses the storage module's selected root, ignoring legacy
  local profile `path`; remote execution keeps verified helper-root discovery.
- **D2 Implemented working directory.** `working_directory` is project-relative. It defaults to `.` when a project
  root is configured. Script directives and shell execution both establish it.
- `input_args` names required string arguments rooted at the project, independent
  of working_directory. Results-relative `path_args` are not required to exist:
  downstream jobs may produce them. No opaque config rewriting or staging.
- **D3 Implemented operation context.** Local preflight checks project/working directories and required inputs.
  Remote preflight checks these paths in one mocked transport operation. Root
  discovery/selector compatibility is resolved once for the operation, without
  a persistent cache. Missing/invalid inputs stop before scheduler effects.
- **D4 Implemented execution evidence.** Public `preview_bundle` returns plain execution data. Saved submission jobs retain
  original arguments plus additive execution metadata: selected machine,
  producing roots, working directory and logical/resolved paths. Artifact lookup
  can use the exact saved run rather than today's profile roots.
  Public `recorded_execution` reads that evidence. `resolve_results_path` and
  `path_exists` accept exact `bundle_path`/`job_name` selectors; saved remote
  lookup uses its producing transport without current profile/root discovery.
- Preserve existing supported APIs through small optional context arguments and
  wrappers where useful. Do not move whole modules or build a second engine.

## Validation

The full offline suite passed: **270 tests in 2.27 s**, with five expected
timestamp-collision warnings. Report: `.development/test-runs/mvp1-final.xml`
under the original repository. The
[reference client](../../examples/reference_client/README.md) exercises both
profiles from unrelated directories, checks matching preview/rendered/executed/
result paths and unchanged relative definitions, and rejects missing/invalid
project roots/inputs before submission. It also verifies activation failure and
restores cwd after activation changes it. Mocked remote submission performs one
root probe and one batched input check; failed preflight transfers/submits nothing.
Unit checks cover nested working directories, generated results that need not
yet exist, path boundaries, saved remote transport without any current profile,
and shared exact/dated/name selection.

Base Conda still imports the original baseline source; its code/tests and empty
runtime directories are unchanged. Development import/storage identity remains
separate, without persistent machine profiles. No real cluster validation,
push or promotion occurred.

## Open questions

None blocks this bounded increment. Receipt persistence and uncertain submission
reconciliation belong to MVP2; task/status/log consolidation belongs to MVP3.

## Forward constraints

Saved locations do not freeze input contents, symlink targets, code or packages.
No concurrency guarantee or new immutable attempt store is introduced. Legacy
records without execution evidence fail explicitly for saved-context lookup;
operators can select the original profile themselves. Status/log commands still
use their existing lookup paths; growing-log synchronization and catch-all
bulk-to-legacy submission fallback remain documented limitations. Custom Slurm
log parents must already exist. No automatic staging, package installation,
retry or recovery was added.

## Log

| Date | Event |
|---|---|
| 2026-11-11 | MVP1.0 scoped around the reference client's project/results bases, one operation context and saved execution evidence |
| 2026-11-11 | MVP1.1 shared context, input/cwd declarations, preview and preflight implemented |
| 2026-11-11 | MVP1.2 context passed through rendering/transport; saved-run artifact lookup and snapshot/name helpers consolidated |
| 2026-11-11 | MVP1.3 closed with 270 passing offline tests and updated guides/schema; task commit `git log --grep '^MVP1.3:'`, local tag `mvp1`; stable unchanged |
