# Status: state, task counts and evidence freshness

Use `asl status --head` for the newest 10 visible run/bundle rows; `--head N`
chooses a count. Selection occurs before inspection, so older runs are not queried.
Head is overview-only; `asl status INDEX/NAME`, exact --bundle-file and --array
retain their selectors. Keep exact bundle/receipt paths for durable handoffs.
No automatic sorting by attention or renumbering/filtering of selected history.

Use public inspect_bundle(s), inspect_logs/fetch_run, and ACP inspect_run for
structured evidence. Do not parse colored tables or read private sidecars.
Canonical aggregate priority is failure, active work, unknown, cancellation,
then all-completed. Submission uncertainty/rejection retains its existing
precedence. FAILED may include active or unknown tasks: read all task counts.
Do not infer that a cancelled downstream job caused the upstream failure.

Human overview uses run/status/tasks; UNSUBMITTED is the readable label for
existing structured ready_to_go. The optional data column distinguishes checked,
cached, partially checked, unavailable and not checked. Checked is collection
time, not scientific validity/completeness. Missing states remain unknown even
when both scheduler queries returned successfully. No queue ETA is inferred.

Each returned job/task has a disposable explanation: category, message,
raw_reason, attention, freshness. Categories include none, dependency,
dependency_invalid, priority, resources, array_limit, hold, begin_time,
configuration, reservation, policy_limit, unknown, mixed and failure. Raw
state/reason/exit/source fields remain authoritative and unchanged. Default
afterok bundle dependency explanations may add dependency_condition and
dependencies [{name, job_id, state, verified}]. Unknown/stale/different-machine
parents are unverified; freshly completed parents need all declared task evidence
and a completed parent aggregate. Custom Slurm expressions remain generic.
Never infer dependency impossibility from a failed parent alone; only the
scheduler's DependencyNeverSatisfied reason establishes that reported condition.

Array explanations include pending_counts by category. Read tasks for per-index
reasons, especially mixed arrays; attention flags failures even if other tasks
are pending. Explanations do not validate scientific results or cross-machine
prerequisites. Campaign member views inherit this same evidence without another
scheduler service or graph.

Explanations are derived after cache I/O, including for old sidecars and
last_observed jobs. No explanation record version or migration is added. Old
aggregate labels are corrected in memory from retained task/parent facts.
refresh=False/--cached performs no commands, receipt refresh/projection,
source-log reads or cache writes. Stale explanations are last-observed, not new
proof of a current dependency blocker. Missing cached evidence stays unverified.

`asl status --details` exposes raw reasons, exit codes, resources, time limits,
saved dates and exact paths. --json is full structured evidence with no color.
--color auto uses terminal colors and respects NO_COLOR; always/never override
text coloring. --width bounds tables; abbreviation never changes structured
facts. Ordinary rows omit successful exit and historical completed-job waits.
Default visibility/order and status/log/fetch index identity are unchanged.
