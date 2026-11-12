# Task: Submit & Monitor

First read `00_operating_rules.md` and `01_client_workflow.md` for installation identity, stable/development
ownership, durable handoff references and handling uncertain submissions.

Development MVP2 returns a receipt from `submit_jobs`; preserve
`SubmissionError.receipt` on failure. Use `list_submissions` and exact
`load_submission`/`refresh_submission`, or `asl submission`, to inspect accepted,
rejected, blocked and unknown outcomes. ACP exposes `list_submissions` and
`inspect_submission` with the same evidence. Refresh may contact the producing
machine, but never submits again. A `submitted` receipt means scheduler
acceptance, not scientific completion. See the client recipe for exact fields
and the distinction between blocked dependents and unobserved remote work.

After submission, use `inspect_bundle(receipt_path=...)` or ACP `inspect_run`
for scheduler observations and relevant bounded logs. `refresh: false` is a
no-network cached read. Use `refresh_submission` first when execution receipt
evidence itself needs fetching. Scheduler and submission outcomes stay separate.

Keep exact planned/tracking/receipt paths in the handoff. Discovery uses
`list_runs` / `list_submissions`; terminal row numbers and latest/name selectors
are temporary conveniences. Check freshness, observation errors and task evidence
before suggesting a diagnosis. Scientific validation and retry decisions belong
to the application/operator. See `09_task_inspect.md` for the inspection loop.
