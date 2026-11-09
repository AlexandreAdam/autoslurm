# AutoSlurm MVP roadmap

[PLAN.md](../PLAN.md) is the active task, scope and progress source of truth.
The [earlier M0-M6 roadmap](archive/PLAN_before_mvps.md) is archived. Deliver small
usable improvements to the current implementation before completing the product.

## Release ladder

| Release | Outcome | Focused effort |
|---|---|---|
| MVP0 | Pinned stable daily use; isolated development code/helper/state; a small baseline and agent recipe | Half to one day |
| MVP1 | One machine/path/selection policy and relative application paths | One to two days |
| MVP2 | No blanket retry, incremental accepted-job receipts, explicit partial/uncertain outcomes, per-job environment | One to three days |
| MVP3 | One task/status/log view, current logs, bounded structured agent inspection and fresh-session rediscovery | Two to three days |
| MVP4 optional | Filtered retrieval of one declared scientific results subtree | Half to one day |

These are incremental planning ranges, subject to the baseline, not deadlines.
Useful releases begin after MVP1 and MVP2. Reuse existing representations and
working paths; there is no complete new object model/database prerequisite.

## Daily use during development

Keep a pinned stable checkout/environment and its existing tracking roots on
workstation and cluster. Develop in separate code/environments with explicit
separate local/remote state and test results. Promote one tested release for
new runs; retain the previous installation for its in-flight jobs and rollback.
No concurrent writers from different versions and no implicit old-run migration.

## Later layers

- **L1:** richer versioned records, offline index, automatic reconciliation/resume
  and historical import/migration.
- **L2:** scientific failed-task/reducer automation and stronger provenance.
- **L3:** public distribution, polished human/complete agent documentation,
  broad artifact-install matrices and release automation.

The interaction map and documentation designs remain full-product references.
Review the current slice only, ship its small accurate recipe, and validate
cluster behavior early with cheap explicit checks. Default tests stay offline.
