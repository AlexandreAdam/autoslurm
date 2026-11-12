# Agent interface

Use the owning installation's public Python API or ACP. Start with
`00_operating_rules.md`, then `01_client_workflow.md` for application adaptation,
paths, submission safety and durable handoff. Prepared software runs on compute
nodes; workstation agents call AutoSlurm.

- `agent_context(sections=[...])` or ACP `gather_context` supplies this guidance.
  A `task` such as `schedule` or `inspect_run` selects the relevant recipe.
- `save_bundle` and `schedule_job` return exact saved references. Preview before
  authorized submission; retain the returned receipt or `SubmissionError.receipt`.
- `list_runs` and `list_submissions` rediscover local work after context loss.
- `inspect_bundle` / ACP `inspect_run` expose structured task identity,
  scheduler/receipt evidence, freshness/errors and selected bounded logs.
- `load_submission` / `refresh_submission` inspect execution receipt evidence
  without resubmitting. Remote receipt refresh is separate from scheduler refresh.
- Terminal tables and `experiment_context` are human presentations of shared
  evidence. Do not parse them, reconstruct filenames, edit tracking JSON or call
  private backend modules as an integration strategy.

A successful tool call means inspection succeeded. Check the returned evidence
before claiming submission acceptance, scheduler completion or scientific
validity. Preserve unknown outcomes and do not retry blindly. See
`07_acp_actions.md` for discovery and `12_task_acp_reference.md` for parameters.
