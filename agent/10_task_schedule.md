# Task: Plan & Schedule Jobs

Start with `00_operating_rules.md` and `01_client_workflow.md`. Identify the installation/lane and machine
before scheduling; planned resolver or recovery features are not current APIs.

To plan a new workload, gather the relevant CLI usage, resource guidance, and ACP action:

- `04_project_map.md` and `05_cli_reference.md` describe scheduling flags. The Python API `autoslurm.schedule_job` takes a job dictionary with `script`, `script_args`, `dependencies` and `slurm` fields. Do not rely on `pre_commands`: the current renderer does not execute it.
- `06_resource_rules.md` explains preferred CPU/GPU/memory/walltime ratios, array/job constraints, and accounting practices—the rules you should obey when generating the SLURM payload.
- `07_acp_actions.md` and `acp_action.json` define the `schedule` action (expecting `bundle`, `job`, optional `append`). Crafting an ACP payload with those keys mirrors calling the CLI/Python helper.
- `01_context_overview.md` reminds you that bundles live under `$AUTOSLURM/jobs` and that duplicate job names are renamed (`_001`, `_002`, …).

Prompt tip: include the examples from `06_resource_rules.md` (light, heavy, array) along with the `slurm` field descriptions from `04_project_map.md` so the LLM replicates the exact flag strings you want. Call `autoslurm-agent-context --sections 00_operating_rules.md 01_client_workflow.md 10_task_schedule.md 12_task_acp_reference.md 06_resource_rules.md` (or `{"action":"gather_context","task":"schedule"}`) to keep the prompt concise before scheduling, then use `execute_acp({"action":"schedule", ...})`.

## Output Path Rule For Bundle-Building Agents

When preparing `script_args` for jobs that write results (for example `--output-dir`), use **results-relative paths**, not machine-local absolute paths.

- Include the project root segment in the relative value so outputs stay grouped by project.
- Example: `script_args["output_dir"] = "substructure_lens/results/transfer_production/adaptive_grid_3/alpha_05/source_2048"`.
- Avoid emitting `/lustre...` or other hard-coded machine-specific prefixes in job payloads.

AutoSlurm is responsible for mapping relative output paths to an absolute remote location (for example under a configured `results_root` on the target machine). This keeps bundles portable when generated on one machine and submitted on another.

Other input arguments require an established application working directory.
`path_args` uses the same results base as `output_dir`, not a project-input base.
