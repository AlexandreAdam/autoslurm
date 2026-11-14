# Task: Plan & Schedule Jobs

Start with `00_operating_rules.md` and `01_client_workflow.md`. Identify the installation/lane and machine
before scheduling; planned resolver or recovery features are not current APIs.

## Alexandre's lasting bundle preference

**Job arguments are explicit, named and readable in the bundle** (2026-11-13).
Apply this when generating jobs and when reviewing or helping client software.

- Use one typed CLI command per kind of job, preferably Typer: put a fixed
  `tool TASK` in `script`, with one named `script_args` key per setting. Keep
  effective defaults visible in the saved JSON.
- Never pack settings into base64, a JSON blob or a single config-file option.
  Point out encoded configuration as something to replace with individual
  job-specific options. Declared input data files remain valid inputs.
- Each argument value is `int`, `float`, `str` or `bool`. A list becomes one
  comma-separated string parsed/validated by the client, not a Python/JSON list:
  current list rendering produces `--flag a b`, which Typer rejects for the
  intended single-value option interface. `input_args`/`path_args` still contain
  lists of argument names; they are not application argument values.
- Boolean options default to off: real `True` emits `--flag`, while real `False`
  is omitted. Record false settings in JSON; a default-on CLI option cannot be
  disabled by omission. Strings are literal values, including spaces and shell
  metacharacters; AutoSlurm quotes them after path resolution. Do not hand-escape
  values. Reject control characters. `$VAR`, substitutions and glob patterns are
  literal text; use runtime_environment or CLI environment defaults for runtime
  values, never shell expressions hidden in script_args.
- **Before saving or submitting**, validate every job against its command's
  typed signature: unknown names, required options, types (including CSV
  elements), boolean defaults and invalid/control-character values. Use the public path/shell
  preview in addition to client validation; it does not check arbitrary CLI
  signatures. Errors must fail locally before writing/submitting the workload.

See the [client argument contract and example](01_client_workflow.md#explicit-named-job-arguments).
These are client-design rules. AutoSlurm checks structural/literal validity;
arbitrary command signatures still need client validation. Existing raw bundles
retain space-style lists and positionals, now safely quoted, but the recommended
client pattern remains named scalars/CSV. Historical bundles are not rewritten.

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

Configure `software_root` for managed code and `results_root` for scientific data
with `asl config`. Declare required inputs in `input_args`; they, `working_directory`,
`path_args` and `output_dir` all resolve relative to `results_root`. The working
directory does not change the base for declared arguments. Required inputs must
already exist; `path_args` can point to future upstream results. Check
`preview_bundle` before submission and retain exact producing paths. See
`01_client_workflow.md` for defaults, legacy profile handling and saved evidence.
