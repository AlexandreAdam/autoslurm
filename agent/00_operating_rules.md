# Start here for AutoSlurm operations

Use the guide and public interface belonging to the installation that manages
the job. Refactor designs describe future behavior; they are not installed
capabilities. This page establishes operating rules during the MVP transition.

## Identify the context before acting

- Establish which installation/environment and machine you are using, and which
  configuration/tracking roots it resolves. Do not infer them from a checkout
  name, shell prompt or a default machine remembered from another session.
- Use the known working installation for daily scientific jobs. Development
  uses separate code/environment, matched helper, state and test outputs.
- If the context is unknown, limit activity to read-only discovery. Do not
  schedule, submit, change configuration, cancel, clean or migrate records while
  guessing which installation owns them.
- Existing queued/running jobs stay with the installation that submitted them.
  Updating a repository or package does not transfer job ownership.

## Use supported operations and record evidence

- Inspect the selected installation's public help/API before relying on a
  command or option. Older agent pages contain configuration, flag and refresh
  assumptions under review; do not treat those as proof of runtime behavior.
- Submit dependencies as job declarations through supported operations. Do not
  edit generated scripts or call private dependency-edit helpers in client code.
- Record the exact saved bundle reference/version, machine, job/task names and
  returned Slurm IDs in the client experiment or handoff record. A moving
  `latest` selector or display index is not a durable identity.
- After partial failure or connection loss, retain all known IDs and error
  evidence. The scheduler/helper may already have accepted work and may still
  be running. Do not submit the bundle again just because no final response
  arrived; establish the previous outcome first.
- Distinguish a failed observation from a failed computation. Report what was
  actually observed, when, and what remains unknown. A missing log/queue row is
  not evidence of successful completion.
- Keep excerpts bounded and retain references to full logs and artifacts.

## Integrating an application

Keep scientific computation independent of submission glue. Prefer an installed
command, explicit validated parameters, relative input/output paths, resource
and worker limits, distinct task outputs, and meaningful nonzero failures.
AutoSlurm owns the selected machine's path mapping. Development MVP1 supports
profile `project_root`, relative `working_directory` and declared `input_args`,
with shared preview/execution resolution and recorded artifact roots. Read
`01_client_workflow.md` for the supported bases and preflight contract. The pinned
stable installation retains its previous behavior. Arbitrary configuration
rewriting and input staging are not supported.

## Development storage selection (MVP0.2)

This feature exists in the development installation; it does not change the
pinned stable installation. Set `AUTOSLURM_STORAGE_ROOT` to an absolute path in
the environment of every development CLI/Python process. It selects
`config.json`, `jobs/`, `slurm/`, `out/` and the default `results/` subtree.
An empty/relative value fails rather than falling back to another installation.
The Python `set_storage_root(path)` override takes precedence for that process
only; `set_storage_root(None)` restores environment/default discovery.

For remote development, machine configuration uses an absolute POSIX
`storage_root` alongside its separate `venv_path`. AutoSlurm verifies selector
support and the exact reported root before submission; transfers, helper
execution and sync use the same selection. Explicit `storage_root` takes
precedence over legacy `path`; missing support, probe errors or a mismatched root
stop the operation. Remote checks are mocked under the current project scope.

Storage selection does not install software, copy application inputs or rewrite
explicit application output paths. Keep declared `results_root`, custom Slurm
outputs and application-owned paths separate from stable outputs. Development
MVP2 returns durable submission receipts and removes automatic
bulk fallback. Preserve `SubmissionError.receipt` and inspect/refresh that exact
receipt; never retry an uncertain submission automatically. A missing receipt
does not prove rejection. The exact local setup is in
`REFACTORING_DOCS/installation-register.md` in the development repository.

MVP3 adds exact structured `inspect_bundle` / ACP `inspect_run` and local
`list_runs` discovery. Retain timestamps, freshness, errors and task identity;
use bounded selected logs. `refresh=False` performs no network calls and marks
cached scheduler/remote evidence stale or absent. See the client recipe.

Use prepared cluster software. Compute jobs do not install packages or update
Git checkouts. Scientific validation, checkpoint meaning and compatibility of
partial results remain the application's responsibility.

For a new agent session, retain installation/lane, machine, exact bundle/task
references, actions taken, observed state/log evidence and time, unresolved
outcomes and the next supported operation. Never include credentials or assume
automatic retry/recovery features exist before their release.
