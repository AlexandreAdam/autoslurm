This folder contains curated guidance for agent use:

- Start with `00_operating_rules.md`: identify the installation that owns the
  run, record exact job evidence, and distinguish current behavior from planned
  MVP capabilities. It applies before any scheduling or cluster side effect.
- Then read `01_client_workflow.md` for the current client recipe, path bases,
  exact selection and handoff limits. It takes precedence over older examples.
- `04_project_map.md` describes how the Python API + CLI interact with job definitions.
- `schema.json` captures the JSON format of bundles for validation/reference.
- `agent/examples/` holds reusable shell scripts illustrating common submission patterns.
- `05_cli_reference.md` lists CLI commands and flags relevant to agents.
- `13_software_preparation.md` covers Git source requests, host-side preparation,
  exact commit evidence and the guard against submitting unprepared runtimes.
- `06_resource_rules.md` documents SLURM resource expectations.
- `07_acp_actions.md` summarizes the ACP actions and references `acp_action.json`.
- `02_llm_interface.md` summarizes LLM context tooling and describes the current structured interface.
- `09_task_inspect.md`, `10_task_schedule.md`, `11_task_submit_monitor.md`, and `12_task_acp_reference.md` distill the relevant pieces for specific agent tasks.
- The new `autoslurm-agent-context` CLI (and `agent_context()` API) print the
  entire agent folder as a single payload.
