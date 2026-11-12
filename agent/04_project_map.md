# Public workflow map

The development MVP7.1 boundary is `01_client_workflow.md`. Public Python imports
come from `autoslurm`; do not integrate through private backend modules or write
tracking JSON directly. The pinned stable installation retains its earlier API.

| Stage | Supported surface | Durable result |
|---|---|---|
| Describe work | `save_bundle`, `schedule_job` | Exact planned path and saved job names |
| Declare software | `attach_software_manifest`, `bundle_software_manifest`, `normalize_software_manifest` | One shared request; machine-owned runtime name |
| Prepare source on the current host | `prepare_software_sources` | Exact Git commits/checkouts or `SoftwarePreparationError.evidence`; no runtime readiness |
| Check paths/scripts | `preview_bundle(path, machine=...)` | Resolved producing paths and script text; no submission |
| Dispatch once | `submit_jobs(..., bundle_path=path)` | Receipt, or `SubmissionError.receipt` |
| Rediscover | `list_runs`, `list_submissions` | Exact local run/receipt references |
| Inspect acceptance | `load_submission`, explicit `refresh_submission` | Known accepted IDs, partial/rejected/uncertain outcomes |
| Inspect execution | `inspect_bundle`, `inspect_bundles` | Shared tasks/state, source/time/errors and optional bounded logs |
| Locate results | `recorded_execution`, `resolve_results_path`, `path_exists` | Producing roots and paths after profile edits |
| Agent tools | `execute_acp`, `action_definitions`, `agent_context` | Structured actions and current guidance |

## Client responsibilities

Expose an installed application command, explicit inputs, a small smoke mode,
nonzero failure exits and independent shard outputs. A thin array adapter may
read `SLURM_ARRAY_TASK_ID`. Reducers validate all expected shards and their
compatibility. Numerical routines do not need AutoSlurm imports.

Declare project-relative `input_args` and `working_directory`, results-relative
`output_dir`/`path_args`, and Slurm resources. AutoSlurm resolves machine roots;
the application handles paths inside opaque scientific configuration files.
Prepare software and inputs before running; compute jobs do no installation/Git
work. Use fresh output namespaces and keep scientific validation application-owned.

## Ownership inside AutoSlurm

Source preparation has a separate dependency flow:
`software_sources` coordinates tracking and calls `git_projects` for managed
cache/checkout effects; `software_manifest` owns pure request validation.
`GitCommands` is the sole Git process adapter. `record_files` remains the shared
JSON publication owner. Runtime installation and execution wiring remain planned;
no new SSH or scheduler implementation was added.

For maintainers, the active dependency flow is:

```text
Python / CLI / ACP -> inspection (coordinates explicit stages)
                       |-> inspection_collection -> files/profiles/scheduler
                       |-> inspection_state -> pure task/state projection
                       |-> inspection_cache -> observation/excerpt JSON
                       |-> inspection_artifacts -> scripts / log_files
                                                          |-> local reads
                                                          |-> remote tail batch
                                                          |-> excerpt cache
```

`inspection_state` requires provided observations and producing profiles. It
never reads configuration, files or a clock, queries a scheduler or mutates
caller data. Shared producing-machine interpretation lives in execution and
is data-only. `inspection_collection` explicitly loads local evidence/profiles
and batches valid IDs; malformed entries do not poison other jobs' observations.

`inspection_cache` owns observation and remote excerpt cache I/O. Status evidence
is saved before request-specific artifacts are attached, keeping those failure
scopes distinct. Invalid cache shapes are unavailable evidence, while failed
cache writes retain already collected observations/log text. `log_files` now
separates reference selection, local reads, remote batching/decoding and cached
excerpts, without importing the inspection coordinator.


Submission now follows explicit responsibilities:

```text
job_runner -> bundle_preparation -> PreparedBundle (definitions, paths, scripts)
           -> path/shell preflight
           -> submission_operation
                create records -> stage exact scripts -> dispatch -> persist evidence
                                                        |
                                                        v
                                           shared bulk_submit_driver
```

`bundle_preparation.prepare_bundle` is an internal in-memory transformation;
preflight has explicit filesystem/process/remote effects. Preview and submission
use the same prepared values and validation path. `submission_operation` separates
record creation, script writes, dispatch, failure classification and persistence.
Its transient dispatch phase distinguishes not-started, started and observed
outcomes; it is separate from durable per-job receipts and scheduler task state.
The graph driver still owns per-job acceptance/persistence ordering. Dependencies
are command arguments in both lanes; prepared scripts are never edited by it.
These are internal boundaries, not new client APIs.

The inspection coordinator retains operation order and public result assembly;
its extracted stages own collection, pure projection, storage and artifact reads.
MVP6 separates the remaining local persistence and transport responsibilities:

```text
Python / CLI / ACP -> bundle_selection -> local discovery + selection policy
                  -> save_load_jobs -> normalization + complete snapshot/append
                  -> config -> profiles + shared configuration writer
                  -> file_transfer -> SCP / rsync / directory probes
                                      |-> transport -> shared SSH arguments
execution / scheduler / receipts / logs -> transport -> shared SSH arguments
bundles / config / receipts / caches -> record_files -> atomic JSON
utils -> explicit compatibility aliases + script naming
```

`save_load_jobs` now implements local persistence, with explicit aliases for
historical selection/transfer imports. Internal callers use the owning modules.
`bundle_metadata` owns older field-update helpers; they share the same writer.
The `config` CLI and Python API use one writer, and the profile's local/
remote classification has one owner. Configuration reads do not discover hosts.
`transport` separates pure argument construction from explicit helper-root probes;
operation adapters retain their own timeouts/error interpretation and no-retry rules.

New snapshot publication is exclusive and complete, so timestamp collisions never
clobber earlier work. A multi-job append reads/publishes once. Atomic replacement
protects existing record bytes against pre-publication failure, but append still
has no concurrent-writer lock. Directory-sync errors may occur after a complete
record is published; this is not a transaction over several files.

`file_transfer` batches script copies and checks staging directories per operation,
without a process-global existence cache. Sync delegates probes/copies to it and
keeps terminal presentation separate; connection failure cannot become a successful
sync of supposedly absent directories. Its broader immutable-copy policy remains
unchanged. Exact inspection/receipt refresh retain their separate evidence contracts.

The package uses explicit imports and `__all__`; intentional public functions
remain, accidental typing/dataclass exports are removed. Receipt state transitions,
legacy low-level dispatch, configuration alias handling and shell argument
representation remain further review points. Backend aliases are not new client APIs.


Execution context owns path mapping and saved producing metadata; storage owns
the selected lane root. Inspection writes only observation caches, never saved
run definitions or receipts. Status/context wrappers render shared evidence;
there is no second agent state engine.

Configuration and mutable state live under the selected storage root, not an
assumed home directory. Internal jobs, scripts, outputs, receipts and observation
caches are implementation details. Use returned references and public APIs rather
than reconstructing filenames. `sync` is a broader profile-based storage copy;
exact inspection is the run-specific observation boundary.

Prepared code/input contents are not snapshotted automatically. Scheduler
history can be unavailable; real-cluster validation, automated reconciliation,
scientific retries and complete packaged agent resources remain later work.

MVP7.0c makes `config` the implementation/command owner; `configuration` modules
retain explicit compatibility entry points. Profiles configure `software_root`
and a merged `results_root` for input/cwd/output paths. One normalization helper
coalesces unambiguous old profiles and rejects conflicting roots before effects.
Explicit root-setting flags resolve an old split without moving files or invoking
SSH. New execution evidence saves the two roots; historical execution contexts
still read the older separate project/result fields. The context's internal
`project_root` field is a compatibility input-base slot, never a third configurable
root for new work. Software cloning/install/release management remain planned.

MVP7.0d centralizes SSH alias validation and transport evidence in config/transport.
Current profiles normalize to `ssh_alias`; new execution/receipt metadata stores
that alias alone. SSH, SCP, rsync and submission sessions all delegate HostName,
User and IdentityFile lookup to SSH. Legacy address/key parsing remains only to
interpret older recorded transports and compatibility adapters, not as another
configuration mode. Retired schedule flags are rejected before application
argument discovery, preventing connection fields from leaking into science args.
