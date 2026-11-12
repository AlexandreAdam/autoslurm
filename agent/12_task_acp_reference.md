# Task: ACP Reference

Read `00_operating_rules.md` before issuing operational requests. Use only
actions supported by the selected installation and preserve exact run evidence.

For any tool that speaks ACP, rely on this distilled reference:

| Action | Purpose | Required Parameters |
| --- | --- | --- |
| `inspect_experiments` | Human overview with status, scripts and bounded logs. | `bundle`, optional `date`. |
| `list_experiments` | Enumerate `jobs/<bundle>_*.json` files so you can pick the right timestamp. | `bundle`. |
| `schedule` | Persist a job dict (script + args + SLURM resources) into a bundle. | `bundle` (or job-provided bundle), `job`, optional `append`. |
| `gather_context` | Return the entire `agent/` folder (docs, schema, examples) as one string. | None. |
| `list_runs` | Discover exact local saved paths without scheduler queries. | Optional `bundle`. |
| `inspect_run` | Shared structured status, tasks, errors and optional bounded logs. | Exactly one `bundle_path` or `receipt_path`; optional `refresh` (default true), `include_logs`, `job_name`, `task_index`, `tail`, `max_log_bytes`, `max_logs`. |
| `list_submissions` | List local submission receipts without scheduler queries. | Optional `bundle`. |
| `inspect_submission` | Read an exact receipt; explicit refresh fetches its execution-side record without submitting. | `receipt_path`; optional boolean `refresh`. |

See `src/autoslurm/acp_action.json` for the authoritative metadata (copy it but keep the JSON valid). `agent_context()`/`autoslurm-agent-context` print a sorted version of these docs, and `07_acp_actions.md` describes how to use `action_definitions()` to introspect this table programmatically before emitting ACPs. To gather only this reference via the CLI: `autoslurm-agent-context --sections 12_task_acp_reference.md`; via ACP: `{"action":"gather_context","sections":["12_task_acp_reference.md"]}`.

Use `refresh: false` for no network calls; evidence is stale/never. Inspect
returned freshness and errors even when the ACP envelope says success. Missing
rows/logs do not establish completion, rejection or scientific validity.
