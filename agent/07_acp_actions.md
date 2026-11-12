# ACP actions reference

`execute_acp({"action": "...", ...})` returns `status` and `result`, or an error
message. Discover supported actions with `action_definitions()`; metadata lives
in `src/autoslurm/acp_action.json`. Use the owning installation's metadata.

| Action | Purpose |
|---|---|
| `list_runs` | Discover local exact run paths; optional `bundle` filter |
| `inspect_run` | Structured exact inspection by `bundle_path` or `receipt_path`; fresh by default |
| `list_submissions` | Discover local incremental submission receipts |
| `inspect_submission` | Read an exact receipt; explicit `refresh` fetches execution-side evidence |
| `schedule` | Save a definition; never dispatches work |
| `gather_context` | Read selected guidance sections or a task recipe |
| `list_experiments` | Older bundle-specific listing; returns exact snapshot paths |
| `inspect_experiments` | Human overview with scripts and bounded logs; use `inspect_run` for structured evidence |

`inspect_run` accepts optional `include_logs`, `job_name`, `task_index`, `tail`,
`max_log_bytes`, `max_logs`, and `refresh`. Setting `refresh: false` performs no
network calls and labels cached scheduler/remote-log evidence stale or absent.
Default refresh can query the producing cluster and fetch requested log tails.
Inspection never submits/cancels work; submission uses the public Python/CLI
surface and requires authorization for that lane.

A response with `status: success` can contain failed queries, unknown tasks or
failed computation. Read `result.freshness`, `errors`, task states and receipt
outcomes. `01_client_workflow.md` defines the evidence contract and next steps.
