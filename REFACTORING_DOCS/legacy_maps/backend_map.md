# Backend Map

This document maps the core backend of AutoSlurm as a set of isolated modules.
It focuses on the low-level machinery that makes the package automate SLURM,
not on the CLI wrappers themselves.

The goal of this pass is to identify the backend building blocks and what each
block is responsible for. Dependency graphs will come later.

## Core Backend Modules

### `storage.py`

Persistent local storage layout and directory handling.

- `set_storage_root`: override the process-local AutoSlurm storage root.
- `_root`: resolve the active root path used by storage helpers.
- `storage_root`: return the root directory for jobs, slurm scripts, and logs.
- `jobs_dir`: return the bundle snapshot directory.
- `slurm_dir`: return the rendered SLURM script directory.
- `out_dir`: return the output log directory.
- `config_file_path`: return the config file path.
- `ensure_storage_dirs`: create the expected local directories.

### `utils.py`

Machine configuration, path resolution, and metadata updates.

- `activation_command_from_config`: build the activation command for a machine.
- `name_slurm_script`: derive the SLURM script filename for a job snapshot.
- `update_job_info_with_id`: persist a submitted job id in bundle metadata.
- `update_job_metadata`: merge arbitrary metadata into a job entry.
- `_normalize_config`: normalize raw config into the package’s config shape.
- `save_config`: persist the normalized config.
- `load_config`: load the config from disk.
- `machine_config`: resolve the selected machine configuration.
- `ssh_host_from_config`: build the SSH host string for a machine.
- `scp_host_and_keypath_from_config`: build the `scp` target and key path.
- `remote_storage_root_from_config`: resolve the remote AutoSlurm storage root.

### `save_load_jobs.py`

Bundle snapshot persistence, filtering, transfer, and ordering.

- `get_bundle_filter_mode`: read the current global bundle visibility policy.
- `set_bundle_filter_mode`: persist the global bundle visibility policy.
- `_submitted_job_count`: count submitted jobs in a bundle payload.
- `_snapshot_kind_from_payload`: classify a bundle payload as draft or submission.
- `_ensure_snapshot_kind`: stamp missing snapshot-kind metadata.
- `_analyze_bundle_file`: classify one bundle snapshot file.
- `bundle_snapshot_state`: validate and classify an explicit bundle file path.
- `_is_placeholder_file`: detect placeholder files in storage.
- `_all_snapshot_entries`: scan and classify every snapshot file.
- `all_bundle_snapshots`: expose all snapshot entries without filtering.
- `_active_visible_snapshots`: apply the active bundle visibility policy.
- `_stale_snapshots`: derive snapshots hidden by the active policy.
- `save_bundle`: write a bundle snapshot to local storage.
- `schedule_job`: append or create a bundle/job snapshot.
- `_resolve_machine_config`: normalize a machine selection for transfer helpers.
- `_remote_root_for_machine`: compute the remote storage root for a machine.
- `_scp_to_remote`: copy one local file to a remote path.
- `_ensure_remote_directory`: create a remote directory if needed.
- `transfer_slurm_to_remote`: copy one rendered SLURM script to remote storage.
- `transfer_slurms_to_remote`: copy multiple SLURM scripts to remote storage.
- `transfer_bundle_to_remote`: copy a bundle snapshot to remote storage.
- `order_jobs`: order jobs according to dependency ordering.
- `load_bundle`: load a selected or latest bundle snapshot.
- `load_bundle_from_path`: load a bundle snapshot from an explicit file path.
- `list_saved_bundles`: list stored snapshots for a bundle name.
- `latest_bundle_summaries`: summarize the latest snapshot per bundle name.
- `bundle_snapshots`: return snapshots after applying the current filter mode.
- `stale_bundle_snapshots`: return snapshots hidden by the active policy.
- `inactive_bundle_snapshots`: return inactive snapshots from the current policy.
- `nearest_bundle_filename`: select the nearest bundle snapshot by date.

### `job_dependency.py`

Dependency graph extraction and script dependency injection.

- `dependency_graph`: convert bundle dependency declarations into a graph.
- `update_slurm_with_dependencies`: inject dependency job ids into SLURM scripts.

### `job_to_slurm.py`

SLURM script rendering.

- `create_slurm_script`: render one job record into a SLURM script file.
- `_format_script_args`: convert job args into CLI-style script arguments.
- `_normalize_script_args`: normalize script argument values before rendering.
- `_write_script_args`: write script arguments into the script body.
- `write_slurm_content`: write the full rendered SLURM content.

### `run_slurm.py`

Local and remote job submission transport.

- `get_job_id_from_sbatch_output`: parse a job id from `sbatch` output.
- `run_slurm_remotely`: submit one script remotely and return the job id.
- `ssh_submission_session`: open a multiplexed SSH session for repeated submits.
- `run_slurm_locally`: submit one script locally and return the job id.
- `run_bulk_submit_driver_remotely`: run the remote bulk-submit driver and parse its result.

### `bulk_submit.py`

Level-based dependency submission orchestration.

- `SubmissionRequest`: represent one job submission request.
- `LevelSubmitResult`: represent the result of level-based DAG submission.
- `topological_levels`: group a DAG into submit-ready levels.
- `submit_dag_by_levels`: submit a DAG level by level.

### `bulk_submit_driver.py`

Remote bulk submission payload execution.

- `BulkSubmitPayload`: structured input for the remote bulk-submit driver.
- `BulkSubmitDriverResult`: structured output from the remote bulk-submit driver.
- `parse_job_id_from_parsable`: parse a job id from `sbatch --parsable`.
- `_submit_one`: submit one job payload inside the driver.
- `submit_payload`: execute a payload locally on the cluster host.

### `legacy_submit_driver.py`

Compatibility remote submission path.

- `submit_jobs_legacy_remote`: older one-by-one remote submit path kept for fallback.

### `array_status.py`

Array-job state interpretation.

- `status_for_job_id`: resolve the effective status for a job or array parent.
- `array_progress_for_job_id`: compute array completion progress.
- `declared_array_size`: parse a Slurm array spec into a count.
- `declared_array_indices`: parse a Slurm array spec into concrete indices.
- `_array_task_index`: detect whether a raw job id belongs to an array task.

### `status.py`

Slurm status query helpers and status aggregation.

- `display_state`: normalize a raw Slurm state for display.
- `infer_bundle_status`: infer a bundle-level status from job states.
- `_colorize_state_text`: colorize a state string.
- `is_cancellable_state`: test whether a state can be cancelled.
- `_visible_len`: measure visible width without ANSI escapes.
- `_ljust_visible`: left-align text while ignoring ANSI escapes.
- `_center_visible`: center text while ignoring ANSI escapes.
- `_parse_status_lines`: parse `job_id|state` lines.
- `_parse_job_field_lines`: parse `job_id|value` lines.
- `_fetch_statuses_locally`: query local Slurm tools for job state.
- `_fetch_statuses_remotely`: query remote Slurm tools over SSH.
- `_fetch_statuses_for_job_ids`: choose local or remote status lookup.
- `_fetch_time_left_locally`: query local remaining time values.
- `_fetch_time_left_remotely`: query remote remaining time values.
- `_fetch_statuses_and_time_left_remotely`: fetch status and remaining time together.
- `_fetch_time_left_for_job_ids`: choose local or remote remaining-time lookup.
- `_fetch_statuses_and_time_left_for_job_ids`: fetch both status and time left.
- `job_status_text`: resolve one job status string.
- `job_status_texts`: resolve status strings for a bundle of jobs.
- `job_status_details`: build detailed status records.
- `_job_remaining_times`: compute remaining-time values.
- `_bundle_summary_lines`: render bundle summary lines.
- `bundle_index_context`: render the bundle index summary.
- `bundle_jobs_context`: render the selected bundle’s job summary.
- `latest_bundle_status_context`: render the latest bundle summary.

### `status_views.py`

Display helpers for bundle/job table rendering.

- `_requested_time`: format a job’s requested wall time.
- `_requested_gpus`: format a job’s GPU request.
- `_dependencies_text`: format dependency information for display.
- `_colorize_state_text`: colorize a state string.
- `_center_visible`: center visible text for table columns.
- `bundle_job_rows`: build table rows from a bundle record.
- `bundle_job_rows_from_jobs`: build table rows from raw job entries.
- `bundle_jobs_context`: render a bundle job table.
- `bundle_jobs_context_from_rows`: render a bundle job table from prepared rows.

### `remote_fs.py`

Remote path resolution and existence checks.

- `_is_remote`: detect whether a machine config represents a remote host.
- `resolve_results_path`: resolve a relative results path on the target machine.
- `path_exists`: test whether a path exists locally or remotely.

### `sync.py`

Remote storage mirroring into local storage.

- `_is_remote`: detect whether a machine config is remote.
- `_remote_ssh_command`: build the SSH command used for remote shell probes.
- `_remote_storage_root`: discover the remote AutoSlurm storage root.
- `_rsync_command`: build the rsync command for a directory mirror.
- `_remote_dir_exists`: test whether a remote directory exists.
- `sync_machine`: synchronize jobs, slurm scripts, and logs locally.

## Backend Tooling

The backend currently relies on these external tools:

- `ssh`: remote command execution and transport
- `sbatch`: job submission
- `squeue`: live status and remaining-time lookup
- `sacct`: accounting lookup and array-task resolution
- `rsync`: local mirror of remote storage
- `scp`: remote file transfer for SLURM scripts and bundles

## Backend Isolation Targets

For the refactor, the backend can be thought of as a small set of isolated
responsibilities:

- storage and config
- bundle snapshot persistence
- SLURM script rendering
- submission transport
- array-status interpretation
- status and log materialization
- remote sync and mirror operations

That separation is the point of this map: it gives us a stable description of
the legacy backend before we split dependencies apart in the new architecture.

