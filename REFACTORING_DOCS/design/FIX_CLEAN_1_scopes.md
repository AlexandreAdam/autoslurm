# FIX.CLEAN.1 Finished bundle cleanup

## Status

Implemented locally in 0.2.0.dev12 following the 2026-11-23 request. MVP10.7's
broader destructive-operation diagnostics remain separate.

## Problem and implementation choices

Cleanup lacked successful/mixed terminal scopes and retained every receipt-bearing
snapshot. Existing failure aggregation could hide live tasks in an array.

Add completed and terminal; expand all. Reuse load_run for exact receipt overlays
and observe_job_statuses for fresh producing-machine scheduler/task projection.
One terminal eligibility function serves failed/cancelled/completed/terminal/all.
Require complete terminal tasks, error-free observations and submitted receipts.
Keep partial/uncertain dispatch protected; no automatic refresh, retry or deletion
of receipts. Require every job submitted for completed; legacy terminal scopes
continue to concern submitted work. Terminal scopes filter explicit indices too.
Fingerprint observed snapshots and retain a changed file before deletion.

Preview/default scopes and existing index-only behavior remain. Only local bundle
JSON is removed; navigation through the removed definition is lost. No schema
change, archival engine, results cleanup, cluster write or historical migration.
These implementation choices do not pre-approve a broader retention policy.

## Verification

41 new offline cases cover actual inspection projection, mixed states, arrays,
missing/unknown/live tasks, observation errors, real temporary receipt overlays,
unsettled/corrupt receipts, previews, explicit indices, unchanged receipts and
changed snapshots. Full suite: 1710 passed, 84 expected collision warnings in
12.43 s; .development/test-runs/clean-scopes.xml. Artifact evidence is recorded
in the installation register. No daily state/config cleanup or cluster contact.
