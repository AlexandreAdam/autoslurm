# AutoSlurm Function Map

This document is a flat reference of the current package-level functions and
classes in `autoslurm`. The goal is to make the package easier to navigate
before we start mapping dependencies between functions and tools.

The descriptions below are brief and intentionally shallow. They describe what
each function appears to do, not how it depends on other functions yet.

## `acp.py`

- `_load_action_definitions`: load the ACP action metadata from JSON.
- `_parse_date`: parse a user-provided date string into a `datetime`.
- `list_bundles`: list saved bundles for a bundle name and optional date.
- `_sections_for_task`: resolve which doc sections belong to a task.
- `execute_acp`: execute an ACP action payload and return a structured result.
- `action_definitions`: expose the loaded ACP action definitions.

## `array_status.py`

- `status_for_job_id`: resolve the effective status for a job or array parent.
- `array_progress_for_job_id`: compute array completion progress.
- `declared_array_size`: parse a Slurm array spec into a total count.
- `declared_array_indices`: parse a Slurm array spec into concrete task indices.
- `_array_task_index`: detect whether a raw job id belongs to a specific array task.

## `bulk_submit.py`

- `SubmissionRequest`: represent one job submission request.
- `LevelSubmitResult`: represent the result of level-based DAG submission.
- `topological_levels`: group a DAG into submit-ready dependency levels.
- `submit_dag_by_levels`: submit a DAG level by level and collect results.

## `bulk_submit_driver.py`

- `BulkSubmitPayload`: structured input for remote bulk submission.
- `BulkSubmitDriverResult`: structured output of remote bulk submission.
- `parse_job_id_from_parsable`: extract a job id from `sbatch --parsable` output.
- `_submit_one`: submit one job payload to `sbatch`.
- `submit_payload`: submit a batch payload and return a structured driver result.

## `context.py`

- `_ordered_agent_files`: return the files that make up the agent context.
- `_render_file`: render one file as text for the agent context.
- `_matches_selectors`: test whether a file path matches selected context sections.
- `agent_context`: build the agent-facing context bundle text.
- `agent_context_paths`: return the file paths included in agent context.

## `definitions.py`

- This module is constant/data only in the current codebase.

## `experiment_context.py`

- `_job_entries`: iterate bundle jobs in a stable order.
- `_resolve_job_selector`: resolve a job selector string to a job record.
- `_read_text`: read a file safely as text.
- `_load_bundle_snapshot`: load a bundle snapshot by name and date.
- `job_context`: render a compact job context summary.
- `_parse_remote_logs`: parse remote log output into filename/content pairs.
- `_fetch_remote_logs_for_job`: fetch logs for a job from a remote machine.
- `_collect_out_logs`: collect local logs and fall back to remote logs.
- `_collect_out_logs_for_job_ids`: collect logs matching one or more job ids.
- `_log_path_matches_job_id`: test whether a log filename matches a job id.
- `_array_task_log_job_ids`: derive candidate ids for an array task log.
- `_fetch_array_task_raw_job_id`: resolve an array task to its raw Slurm id.
- `_latest_out_log_for_bundle`: pick the newest log for a bundle.
- `_latest_out_log_for_job`: pick the newest log for a specific job.
- `_latest_out_log_in_storage`: pick the newest log in local storage.
- `latest_log_context`: render the newest relevant log or a readable error.
- `experiment_context`: render a bundle, scripts, and logs as agent context.

## `job_dependency.py`

- `dependency_graph`: convert job dependency declarations into a graph.
- `update_slurm_with_dependencies`: inject dependency ids into a SLURM script.

## `job_runner.py`

- `transfer_slurm_to_remote`: compatibility alias for the plural transfer helper.
- `submit_jobs_legacy_remote`: submit jobs one by one on a remote machine.
- `submit_jobs`: main bundle submission entrypoint.

## `job_to_slurm.py`

- `create_slurm_script`: render one job into a SLURM script file.
- `_format_script_args`: normalize script arguments into CLI-style strings.
- `_normalize_script_args`: normalize input argument values before rendering.
- `_write_script_args`: write script args into an output stream.
- `write_slurm_content`: write the full SLURM script body.

## `legacy_submit_driver.py`

- `submit_jobs_legacy_remote`: older remote job submission path kept for fallback.

## `logs.py`

- `main`: command-line entrypoint for bundle and job log inspection.

## `remote_fs.py`

- `_is_remote`: detect whether a machine config is remote.
- `resolve_results_path`: resolve a relative results path on the target machine.
- `path_exists`: test whether a local or remote path exists.

## `run_slurm.py`

- `get_job_id_from_sbatch_output`: parse a Slurm job id from `sbatch` output.
- `run_slurm_remotely`: run one SLURM script over SSH and capture the job id.
- `ssh_submission_session`: open a multiplexed SSH session for repeated submits.
- `run_slurm_locally`: submit one script locally with `sbatch`.
- `run_bulk_submit_driver_remotely`: run the internal bulk-submit driver remotely.

## `save_load_jobs.py`

- `get_bundle_filter_mode`: read the current bundle visibility filter mode.
- `set_bundle_filter_mode`: persist the bundle visibility filter mode.
- `_submitted_job_count`: count submitted jobs inside a bundle payload.
- `_snapshot_kind_from_payload`: classify a snapshot as draft or submission.
- `_ensure_snapshot_kind`: stamp missing snapshot-kind metadata.
- `_analyze_bundle_file`: classify one bundle snapshot file.
- `bundle_snapshot_state`: validate and classify an explicit bundle file path.
- `_is_placeholder_file`: detect hidden placeholder files.
- `_all_snapshot_entries`: load and classify every saved snapshot.
- `all_bundle_snapshots`: return all snapshots regardless of filter mode.
- `_active_visible_snapshots`: apply the active visibility policy.
- `_stale_snapshots`: compute snapshots hidden by the active policy.
- `save_bundle`: write a bundle JSON snapshot to local storage.
- `schedule_job`: append or create a job snapshot.
- `_resolve_machine_config`: normalize a machine configuration.
- `_remote_root_for_machine`: compute the remote storage root for a machine.
- `_scp_to_remote`: copy a file to a remote path with `scp`.
- `_ensure_remote_directory`: create a remote directory if needed.
- `transfer_slurm_to_remote`: copy one SLURM script to remote storage.
- `transfer_slurms_to_remote`: copy a set of SLURM scripts to remote storage.
- `transfer_bundle_to_remote`: copy a bundle snapshot to remote storage.
- `order_jobs`: order jobs according to a dependency ordering.
- `load_bundle`: load the latest or selected bundle snapshot.
- `load_bundle_from_path`: load a bundle snapshot from a file path.
- `list_saved_bundles`: list saved bundle snapshots matching a name.
- `latest_bundle_summaries`: summarize the latest bundle snapshot per name.
- `bundle_snapshots`: return bundle snapshots after applying visibility policy.
- `stale_bundle_snapshots`: return snapshots hidden by the active policy.
- `inactive_bundle_snapshots`: return inactive snapshots from the current policy.
- `nearest_bundle_filename`: find the bundle snapshot nearest to a date.

## `scan.py`

- `_catalog_path`: return the catalog file path.
- `_load_catalog`: load the local app catalog.
- `_save_catalog`: save the local app catalog.
- `_scan_pyproject`: scan a repository for console script declarations.
- `_infer_purpose`: infer a human-readable purpose for an app.
- `_module_file_candidates`: find likely source files for a module target.
- `_doc_summary_from_target`: extract a short doc summary from a target module.
- `_upsert_repo_entry`: add or update one repository entry in the catalog.
- `_render_scan_table`: render a table of discovered applications.
- `_scan_repo`: scan one repository path.
- `_render_list`: render the stored catalog as text.
- `_build_parser`: build the CLI parser for scan.
- `main`: command-line entrypoint for scanning repositories.

## `status.py`

- `display_state`: normalize a raw Slurm state for display.
- `infer_bundle_status`: infer a bundle-level state from job states.
- `_colorize_state_text`: colorize a job state string.
- `is_cancellable_state`: check whether a state can be cancelled.
- `_visible_len`: compute visible string width without ANSI codes.
- `_ljust_visible`: left-pad text while ignoring ANSI width.
- `_center_visible`: center text while ignoring ANSI width.
- `_parse_status_lines`: parse `job_id|state` lines into a dict.
- `_parse_job_field_lines`: parse `job_id|value` lines into a dict.
- `_fetch_statuses_locally`: query local Slurm tools for status.
- `_fetch_statuses_remotely`: query remote Slurm tools over SSH for status.
- `_fetch_statuses_for_job_ids`: choose local or remote status lookup.
- `_fetch_time_left_locally`: query local remaining time values.
- `_fetch_time_left_remotely`: query remote remaining time values.
- `_fetch_statuses_and_time_left_remotely`: fetch status and remaining time together.
- `_fetch_time_left_for_job_ids`: choose local or remote remaining-time lookup.
- `_fetch_statuses_and_time_left_for_job_ids`: fetch both status and remaining time.
- `job_status_text`: resolve a single job status string.
- `job_status_texts`: resolve status strings for a list of jobs.
- `job_status_details`: build detailed status records for jobs.
- `_job_remaining_times`: compute remaining time values for jobs.
- `_bundle_summary_lines`: render bundle summary lines for the status view.
- `bundle_index_context`: render the bundle index summary.
- `bundle_jobs_context`: render a selected bundle’s job summary.
- `latest_bundle_status_context`: render the latest bundle status summary.

## `status_views.py`

- `_requested_time`: format a job’s requested wall time.
- `_requested_gpus`: format a job’s GPU request.
- `_dependencies_text`: format dependency information for display.
- `_colorize_state_text`: colorize a state string for the table output.
- `_center_visible`: center visible text for table columns.
- `bundle_job_rows`: build per-job table rows from a bundle record.
- `bundle_job_rows_from_jobs`: build table rows directly from job entries.
- `bundle_jobs_context`: render the bundle job table from a bundle record.
- `bundle_jobs_context_from_rows`: render the bundle job table from prebuilt rows.

## `storage.py`

- `set_storage_root`: set the process-local storage root.
- `_root`: return the current storage root.
- `storage_root`: return the storage root path.
- `jobs_dir`: return the jobs directory path.
- `slurm_dir`: return the SLURM scripts directory path.
- `out_dir`: return the output logs directory path.
- `config_file_path`: return the config file path.
- `ensure_storage_dirs`: create the expected storage directories.

## `sync.py`

- `_is_remote`: detect whether a machine config points to a remote host.
- `_remote_ssh_command`: build an SSH command for a remote shell action.
- `_remote_storage_root`: resolve the remote AutoSlurm storage root.
- `_rsync_command`: build the rsync command used for syncing.
- `_remote_dir_exists`: test whether a remote directory exists.
- `sync_machine`: synchronize remote AutoSlurm storage into local storage.

## `utils.py`

- `activation_command_from_config`: resolve an environment activation command.
- `name_slurm_script`: derive the SLURM script filename for a job snapshot.
- `update_job_info_with_id`: write a submitted job id into stored metadata.
- `update_job_metadata`: merge arbitrary job metadata into a bundle snapshot.
- `_normalize_config`: normalize raw config data into the internal config shape.
- `save_config`: write the AutoSlurm config file.
- `load_config`: load the AutoSlurm config file.
- `machine_config`: resolve the selected machine config for CLI use.
- `ssh_host_from_config`: resolve the SSH host string for a machine.
- `scp_host_and_keypath_from_config`: resolve the host and key path for `scp`.
- `remote_storage_root_from_config`: resolve the remote storage root path.

## `apps/agent_context.py`

- `main`: CLI entrypoint for printing agent context.

## `apps/bulk_submit_driver.py`

- `parse_args`: parse CLI arguments for the bulk submit driver.
- `_read_payload_text`: load JSON payload text from a file or stdin.
- `main`: command-line entrypoint for the bulk submit driver.

## `apps/cancel.py`

- `_parse_date`: parse date input for bundle selection.
- `_resolve_bundle_name`: resolve a bundle name from a selector and date.
- `_state_matches`: test whether a job status matches a cancel filter.
- `_cancel_local`: cancel one or more local job ids.
- `_cancel_remote`: cancel one or more remote job ids.
- `_build_parser`: build the cancel CLI parser.
- `main`: command-line entrypoint for cancellation.

## `apps/clean.py`

- `_render_table`: render a table of bundle snapshot rows.
- `_build_parser`: build the clean CLI parser.
- `_resolve_target_rows`: resolve row selections from CLI indices and ranges.
- `main`: command-line entrypoint for cleaning stale snapshots.

## `apps/configuration.py`

- `_ensure_config_dir`: create the config directory if needed.
- `_save_config`: persist the edited config file.
- `_refresh_config_aliases`: update short-name aliases in config.
- `_is_remote`: detect whether a machine config is remote.
- `_remote_ssh_command`: build an SSH command for remote validation.
- `_validation_shell_command`: build the validation shell command.
- `_validate_machine`: validate one machine configuration.
- `_validate_machine_selection`: validate a machine selection in config.
- `_prompt_text`: prompt the user for a text value.
- `_prompt_yes_no`: prompt the user for a yes/no value.
- `_prompt_machine_name`: prompt for a machine name.
- `_prompt_machine_details`: prompt for machine configuration fields.
- `_select_machine`: prompt the user to select a machine.
- `_create_machine`: create a new machine entry.
- `_update_machine`: update an existing machine entry.
- `_rename_machine`: rename an existing machine entry.
- `_change_default_machine`: change the default machine.
- `_set_default_machine_by_name`: set the default machine by name.
- `_create_default_machine`: create the initial machine entry.
- `_menu_loop`: run the interactive configuration menu.
- `display_config`: print the full config.
- `display_config_summary`: print a summary of the config.
- `main`: CLI entrypoint for configuration.

## `apps/experiment_context.py`

- `_parse_date`: parse date input for context selection.
- `_build_reference_date`: build a reference date from CLI fields.
- `_add_date_arguments`: add date-related CLI arguments.
- `_resolve_reference_date`: resolve a date from parsed args.
- `_copy_to_clipboard`: copy rendered text to the clipboard.
- `_emit`: print text and optionally copy it.
- `_add_common_arguments`: add shared context CLI arguments.
- `_build_parser`: build the experiment-context parser.
- `main`: CLI entrypoint for experiment context rendering.

## `apps/filter.py`

- `_build_parser`: build the bundle filter CLI parser.
- `main`: CLI entrypoint for reading or setting bundle filter mode.

## `apps/initialize.py`

- `parse_args`: parse CLI args for initialize.
- `main`: CLI entrypoint for creating an empty bundle.

## `apps/inspect.py`

- `_parse_date`: parse date input for bundle selection.
- `_build_reference_date`: build a reference date from CLI fields.
- `_copy_to_clipboard`: copy rendered text to the clipboard.
- `_emit`: print text and optionally copy it.
- `_resolve_job_selector`: resolve a job selector to a job name.
- `_resolve_bundle_target`: resolve a bundle selector to a bundle name.
- `_strip_status_instruction`: remove the status hint from log text.
- `_tail_text`: return the last N lines of text.
- `_list_job_log_files`: list local log files for one job.
- `_log_path_matches_job_id`: test whether a log filename matches a job id.
- `_list_array_task_log_files`: list local log files for one array task.
- `_parse_array_task_filter`: parse array task selection tokens.
- `_resolve_job_row`: resolve one job row and optional array task.
- `_build_parser`: build the inspect CLI parser.
- `main`: CLI entrypoint for job and log inspection.

## `apps/logs.py`

- `main`: CLI entrypoint for the logs command.

## `apps/root.py`

- `_build_parser`: build the top-level `autoslurm` command parser.
- `main`: dispatch the selected subcommand.

## `apps/schedule.py`

- `_prepare_script_command`: build the base script command.
- `_run_help_command`: query a script’s `--help` output.
- `_normalize_flag`: normalize a CLI flag name.
- `_parse_help_options`: infer accepted options from help text.
- `_parse_unknown_args`: parse unrecognized CLI args for scheduled scripts.
- `parse_script_args`: convert script args into structured job metadata.
- `_build_parser`: build the schedule CLI parser.
- `parse_args`: parse schedule arguments.
- `main`: CLI entrypoint for scheduling jobs.

## `apps/scan.py`

- See the `scan.py` module above; this CLI is the user-facing entrypoint.

## `apps/status.py`

- `_parse_date`: parse date input for status selection.
- `_build_reference_date`: build a reference date from CLI fields.
- `_build_parser`: build the status CLI parser.
- `_parse_array_task_filter`: parse array task selection tokens.
- `_status_rows`: load and sort bundle snapshot rows.
- `_status_summary_text`: render the non-batched status summary.
- `_summary_job_metrics`: compute summary counts for one job.
- `_status_summary_text_batched`: render the batched status summary.
- `_resolve_targets`: resolve requested bundle indices or names.
- `main`: CLI entrypoint for bundle status display.

## `apps/submit.py`

- `parse_args`: parse CLI arguments for submit.
- `main`: CLI entrypoint for bundle submission.

## `apps/sync.py`

- `main`: CLI entrypoint for synchronizing remote storage.

## `apps/agent_context.py`

- `main`: CLI entrypoint for the agent context shortcut.

## Notes

- This map deliberately does not describe function-to-function dependencies yet.
- It is intended as the first pass for understanding the package’s surface area.
- The next step is to turn this inventory into a dependency chart for the
  highest-impact flows: submit, status, logs/inspect, sync, and clean.
