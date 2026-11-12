# AutoSlurm milestone designs

[PLAN.md](../../PLAN.md) records what happens next and what is complete. Each
milestone design records its problems, decisions, unresolved questions, and
validation approach.

| Milestone | Document | Status |
|---|---|---|
| MVP0 Safe development and a small baseline | [MVP0_safe_development.md](MVP0_safe_development.md) | Complete locally; no promotion |
| MVP1 Paths and selection | [MVP1_paths_and_selection.md](MVP1_paths_and_selection.md) | Complete locally; no promotion |
| MVP2 Submission safety | [MVP2_submission_safety.md](MVP2_submission_safety.md) | Complete locally; no promotion |
| MVP3 Shared inspection | [MVP3_shared_inspection.md](MVP3_shared_inspection.md) | Complete locally; no promotion |
| MVP4 Submission boundaries | [MVP4_submission_boundaries.md](MVP4_submission_boundaries.md) | Complete locally; no promotion |
| MVP7 Cluster software preparation | [MVP7_cluster_software_preparation.md](MVP7_cluster_software_preparation.md) | Planned; manifest contract first |
| Original M0 Interaction mapping and regression coverage | [M0_baseline.md](M0_baseline.md) | Superseded by MVP0; historical proposal |

Coverage references include the [interaction map](../interaction-map.md),
[agent documentation design](../agent-documentation-design.md), and
[human documentation and distribution design](../documentation-and-distribution-design.md).
Review only the subset needed by the current MVP. Later product designs remain
provisional and do not gate small reliability improvements.

Open later designs when the preceding milestone closes. Do not create empty
design documents for every future milestone.

## Document structure

Each design has **Status**, **Problems**, **Decisions**, **Open questions**,
**Forward constraints**, and **Log**. Each decision has a stable ID and a status
such as proposed, accepted, amended, or deferred. Include the intended behavior
and the evidence that will verify it.

Decisions become accepted after user review. Record a short summary in PLAN.md;
keep the reasoning here. Resolve task-blocking questions before dependent code.
Update decisions and logs in the same commit as the work they govern.

Close the design with the milestone's checks, exceptions, and tag. Preserve it
as the explanation for the implementation.
