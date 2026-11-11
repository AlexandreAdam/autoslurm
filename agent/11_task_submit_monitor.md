# Task: Submit & Monitor

First read `00_operating_rules.md` and `01_client_workflow.md` for installation identity, stable/development
ownership, durable handoff references and handling uncertain submissions.

When it’s time to execute scheduled jobs and watch their logs, these references help:

- `04_project_map.md` and `03_experiment_context.md` note the submission flow: `autoslurm-submit <bundle>` invokes `submit_jobs`, which renders scripts, transfers them if remote, calls `sbatch`, and updates the bundle with job IDs.
- Declare dependencies through the selected installation's supported scheduling
  interface. Clients should not edit generated scripts or call private
  dependency-edit helpers to construct submissions.
- After submission, `inspect_experiments` (ACP) or rerunning `autoslurm-experiment-context` returns the `.out` logs that the scheduler writes under `$AUTOSLURM/out` (and the remote fetch logic brings remote logs back into that directory).
- Use `save_bundle`'s returned path or `list_experiments`' returned snapshot path.
  Submit with explicit `bundle_path`/`--bundle-file`; retain actual submission
  path/date/IDs too. Do not resume from a remembered latest bundle or row index.
- The agent context summary (`gather_context`) is handy for reminding the agent which directories exist and which helper to call for submission.

LLM prompt tip: include `submit_jobs` into the prompt by referencing the `autoslurm.job_runner` section in `04_project_map.md`, describe what `autoslurm-submit` prints, and have it emit `{"action":"list_experiments","bundle":...}` followed by `{"action":"inspect_experiments", ...}` to monitor outputs. Use `autoslurm-agent-context --sections 00_operating_rules.md 01_client_workflow.md 11_task_submit_monitor.md 12_task_acp_reference.md` (or `{"action":"gather_context","task":"schedule"}`/`"list_experiments"`) to load just the submit guidance and ACP reference into the prompt before issuing these calls.
