# AutoSlurm MVP plan

Improve the working package in independently usable increments. Prioritize
relative paths, one implementation of each core rule, submission safety, and
agent usability. Keep the larger product design as a direction rather than a
prerequisite for using the first improvements.

This file is the source of truth for active scope, task order and progress.

## Status

- **Current milestone:** MVP6, persistence and transport boundaries; complete locally.
- **Stage:** main checkout is active on `dev`, explicitly selected by the user
  on 2026-11-12. Base Conda imports it; tests use the same source with isolated
  environment/state. Baseline rollback source remains in `.development/stable`.
  Full offline suite: 392 passed. Local persistence/selection, configuration,
  SSH construction and file movement now have explicit owners. Complete atomic
  writes, exclusive snapshot creation and one-update batch appends protect saved
  records. Inspection/submission/scientific workflows remain covered.
  Local daily-use activation completed; no cluster installation changed.
- **Next task:** MVP7 manifest attachment and helper/runtime environment separation;
  implementation has not started. Latest-source defaults and machine-owned dependency
  setup, first-time cloning and independent software/results locations are confirmed;
  read the design before adding software preparation.
- **Scope update:** MVP4–MVP6 modularity increments are complete locally. MVP7
  covers bundle-driven Git project/environment preparation on the login/preparation
  host, with mocked cluster interactions under the current scope. Result retrieval
  remains optional.
- **Last updated:** 2026-11-12.
- **Working agreement:** [WORKFLOW.md](WORKFLOW.md).
- **Installation evidence:** [installation register](REFACTORING_DOCS/installation-register.md)
  and [baseline results](REFACTORING_DOCS/design/MVP0_safe_development.md#local-baseline-mvp01).
- **Current execution scope:** local only. Mock Slurm and remote commands in
  tests; no SSH, live submissions, remote discovery or cluster installation.
- **Previous plan:** [archived M0-M6 roadmap](REFACTORING_DOCS/archive/PLAN_before_mvps.md).
  Old task IDs remain historical; they are not reused by this plan.

## Delivery priorities

1. Keep daily jobs usable while development proceeds in isolation.
2. Centralize path, machine, bundle-selection, task-identity and state rules in
   small shared helpers, while reusing the working bundle format and code.
3. Prevent duplicate submissions and preserve known partial success.
4. Give agents precise, bounded inspection and an accurate client integration
   recipe, including how to resume after losing chat context.
5. Add scientific conveniences and a complete packaged/documented release only
   when the reliability increments are already useful.

"One source of truth" means one active implementation per concern. It does not
require implementing a new database, complete record hierarchy, protocol, or
persistent local index before the first release. There is no wholesale module
move as a prerequisite. Correctness and reduced repeated cluster work are the
first performance improvements; numerical throughput is application-owned.

## MVP release ladder

These are rough focused engineering effort ranges, not deadlines. They assume
one maintainer with agent assistance, one configured cluster, reuse of existing
tests and tooling, and small additive metadata changes. Re-estimate after MVP0.
Each row is incremental, not cumulative.

| Release | User-visible improvement | Focused effort | Explicit boundary |
|---|---|---:|---|
| MVP0 | Daily use protected; separate development state and a reproducible baseline | Half to one day | No production migration or broad test-harness rewrite |
| MVP1 | Relative application paths work predictably; machine/path/selection rules have one owner | One to two days | Existing bundle layout retained; no general filesystem abstraction |
| MVP2 | Unsafe fallback removed; known submitted jobs survive partial failure; uncertain outcomes are explicit | One to three days | No automatic recovery/resubmission of uncertain acceptances |
| MVP3 | Agent and terminal agree on tasks/status/logs; growing logs update; a new agent can rediscover work | Two to three days | Reuse current queries/storage; no complete offline-index redesign |
| MVP4 | Shared preparation and explicit submission lifecycle/dispatch boundaries | One to two days | Existing receipt format and failure guarantees; no retry engine |
| MVP5 | Separate inspection collection, state projection, caches and artifact reads | One to two days | Preserve public inspection results; no new index |
| MVP6 | Separate bundle persistence/selection from transport and configuration helpers | One to two days | No storage migration or broad module renaming |
| MVP7 | Prepare exact Git project revisions and verify isolated runtime installations for a bundle | Estimate after manifest contract | Login/preparation host only; never update code/environments used by existing jobs |
| Optional result retrieval | Filtered retrieval for one declared result subtree | Half to one day | No general data-staging system or automatic scientific retry engine |

Useful changes can ship after MVP1 and MVP2. MVP0-MVP3 represent roughly five to
nine focused days with the stated scope; none requires completing later product
work. If a task exceeds its boundary, split it and keep the smaller useful
release. First-release estimates do not include automatic reconciliation,
reducer repair, complete migration, or polished publication.

## Constraints that remain

- This refactor is currently developed and tested locally only, as requested.
  Exercise remote behavior through mocks. Real cluster validation and deployment
  are deferred to an explicitly authorized later session; local test success
  does not establish real cluster compatibility.
- Agents operate on the workstation. Cluster commands use a bounded helper on
  the login node; compute jobs use prepared software without internet/Git work.
- Every application run/bundle targets one selected machine. Different runs
  may select different named profiles; multi-machine routing is out of scope.
- Client definitions/configuration use relative paths with explicit bases.
  AutoSlurm discovers machine roots and provides execution context. Do not
  rewrite arbitrary strings or nested configuration files to guess paths.
- Relative path resolution does not make an input file exist on the cluster.
  Validate availability or describe the required preparation explicitly.
- Configuration and tracking state must be isolated from the code installation
  and from the other release lane. Keep logical paths and producing-machine
  locations so a later profile change cannot redirect old artifacts.
- Keep existing formats where convenient for the first increments. Breaking
  APIs/formats are allowed at a promoted release boundary; no blanket promise
  to preserve private imports, all aliases, or every intermediate format.
- Preserve production records and live-job handling in the stable installation.
  Historical import/read compatibility can be added later; never silently
  reinterpret or overwrite old records.
- Jobs with unknown state or uncertain submission are not automatically retried
  or removed. Scientific success, checkpoint semantics and compatibility of
  outputs remain application responsibilities.

## Use the package during the refactor

As explicitly requested on 2026-11-12, the main folder is now the active `dev`
checkout and base Conda's editable installation imports it. Plain `asl` and
`autoslurm` use development code with the main storage root, unless explicitly
selected otherwise. No persistent machine config or local jobs existed at the
switch, so no tracking migration was required. Cluster installations are unchanged.

Tests use `.development/python`/`.development/asl` with `.development/venv` and
`.development/state`, importing the active main source. Default fixtures use
fresh temporary roots and reject unmocked external effects. The old development
checkout remains as the MVP4 snapshot, not the active editing location.

The baseline is preserved at `.development/stable`; source-selecting
`.development/stable-python` and `.development/stable-asl` use that checkout and
its own default storage. All original main working files were backed up and
stashed; existing user edits were restored unchanged. See the installation
register for exact evidence, wrappers and rollback ownership.

### Promotion and rollback

1. Record the stable revision, installed environments, helper version and roots.
   Finish or continue managing existing jobs through that stable lane.
2. Implement and validate one MVP in development with local mocked Slurm and
   transport commands. Real cluster checks are deferred under the current
   local-only scope. Early installs may remain from a pinned checkout; a wheel smoke
   check before promotion detects source-tree resource assumptions.
3. Select the tested revision as a release candidate. Change only the chosen
   new-run configuration explicitly, recording code/helper/root identity.
4. Keep the previous stable environment/root available for its in-flight jobs
   and historical inspection. Do not update an environment referenced by queued
   jobs. Promotion does not migrate or resubmit those jobs.
5. Start new runs with the promoted installation. If it fails, use the previous
   lane for new work; inspect any candidate submissions in their original lane
   first so rollback does not duplicate jobs or lose their records.

An existing job belongs to the lane/attempt that submitted it. Old live tracking
files are never jointly written by old and new code. Read-only fixture copies
are fine; copied submission IDs are never treated as new work to submit. A later
migration must be explicit, one-way when necessary, and backed by retained data.

## MVP0 Protect daily use

Design: [MVP0 safe development](REFACTORING_DOCS/design/MVP0_safe_development.md).
Only the current milestone has detailed tasks. Later releases have bounded
outcomes; detail their tasks when the preceding release is useful.

- [x] **MVP0.0 Restructure the plan.** *Done when:* the old roadmap is archived,
  MVP boundaries/effort are stated, stable/development lanes are described, and
supporting designs distinguish early delivery from later product work.
- [x] **MVP0.0a Establish the working rules.** *Done when:* WORKFLOW.md defines
  task/release gates and handoff, AGENTS.md/CLAUDE.md use the same agreement, an
  installation register clearly marks unverified state, and a short operating
  guide is available in the existing agent context. No installations, runtime
  roots, jobs or releases are changed by this documentation step.
- [x] **MVP0.1 Record the working baseline.** *Done when:* the actual local
  installation/import/storage locations and immutable source revision reference
  are recorded, fast-test results and one cheap mocked workflow are described,
  and tests have been inspected for side effects. No existing installation or
  production root changes. Cluster inventory is deferred under local-only scope;
  recording a revision is not freezing the editable installation (MVP0.2).
- [x] **MVP0.2 Make development isolation explicit.** *Done when:* the chosen root
  selector is supported by local and remote development code; fake-command tests
  prove config, job, script, log and result writes stay in the selected lane;
  discovery resolves the intended helper/root. A mismatched/unknown helper root
  cannot silently fall back into production. Retain the baseline code separately
  and verify a separate local development checkout/environment. Make the default
  test fixtures explicitly offline, including the unmocked accounting probe found
  in MVP0.1. All remote checks use mocks; no cluster setup is required here.
- [x] **MVP0.3 Publish the small development contract.** *Done when:* an accurate
  short agent recipe identifies the lane, supported operations, relative path
  convention, how to select an exact saved bundle, and unsafe actions to avoid.
  Use one local smoke client and one small dependency/array fixture; add other
  regression cases only as their implementation needs them.

A review need settle only choices blocking this increment. The
[interaction map](REFACTORING_DOCS/interaction-map.md) remains a coverage checklist,
not a requirement to finalize every future interaction before coding.

## MVP1 Predictable paths and shared rules

- [x] **MVP1.0 Detail the path increment.** Use the reference client's current
  input/results bases to settle project-root/working-directory behavior and split
  the implementation below into small tasks. Preserve the established local-only
  scope, selected storage roots and stable installation.
- [x] **MVP1.1 Centralize execution paths.** One context resolves the selected
  profile/storage once per operation. `project_root` anchors relative
  `working_directory` and declared `input_args`; results-relative `path_args`
  and `output_dir` retain their existing base. Preview and preflight share this
  policy, validate roots/required inputs and leave declarations unchanged.
- [x] **MVP1.2 Connect execution and saved-run lookup.** Script preparation,
  transfers/helper execution and path lookup consume the context; save logical
  and resolved execution locations. Share exact/nearest bundle loading and basic
  job naming; do not rebuild status/array identity or implement MVP2 recovery.
- [x] **MVP1.3 Verify the scientific workflow and publish the contract.** The
  same relative definition works under two separate profiles from an unrelated
  current directory. Preview/rendered/executed/artifact paths agree; missing
  roots/inputs fail before submission; recorded roots survive profile changes.
  Update human/agent examples, run offline checks and close with a local tag.

Design: [MVP1 paths and selection](REFACTORING_DOCS/design/MVP1_paths_and_selection.md).

**Outcome:** clients stop embedding absolute machine paths and all active paths
through the selected workflow use the same machine config, resolver and bundle
selection rule.

- Extract the existing machine/root resolution policy into one owner. Resolve
  the selected machine once per operation and pass that context through.
- Decide explicit relative bases and working directory for the reference client,
  including paths inside its own configuration. Start with the smallest project/
  results-root arrangement that fits it. No recursive rewriting of opaque config.
- Route script preparation, path existence checks and artifact lookup through
  that policy; keep relative definitions unchanged and save resolved locations.
- Share bundle selection and basic job/task identity instead of re-deriving them
  in each entry point. Existing dictionary/file representations may remain.
- Correct the relevant client integration guide with one working example.

*Done when:* the same relative workload resolves under two profiles in separate
single-machine tests, changing the submitting current directory does not change
its meaning, missing roots/inputs have clear errors, and preview/execution/
artifact locations agree. A local mock-cluster case validates the selected
environment and working-directory contract; real cluster validation is deferred.
No large package reorganization is needed to complete the local increment.

## MVP2 Safer submission

Design: [MVP2 submission safety](REFACTORING_DOCS/design/MVP2_submission_safety.md).

- [x] **MVP2.0 Scope the submission contract.** Retain bundle files; add a small
  submission receipt, explicit outcomes and read-only refresh. Local-only tests.
- [x] **MVP2.1 Preserve execution evidence.** Validate the entire graph/scripts;
  save submission identity and each accepted ID on the execution side before
  continuing. Stop on rejection or uncertainty; no implicit alternative submits.
- [x] **MVP2.2 Connect clients and recovery inspection.** Return a plain receipt,
  attach it to submission errors, mirror known IDs, and expose exact local reads
  and explicit remote refresh without resubmitting. Protect uncertain records.
- [x] **MVP2.3 Validate and document.** Mock partial failures/response loss and
  duplicate helper invocation, exercise literal/runtime environment exports,
  update client guides and close the offline milestone with a local tag.

**Outcome:** a failed command or connection cannot trigger the current blanket
retry, and known accepted job IDs remain discoverable.

- Validate the complete dependency graph and scripts before the first submit;
  apply dependencies before every dependent job, including any retained path.
- Remove catch-all bulk-to-legacy fallback. A startup compatibility failure must
  happen before scheduler effects; select any supported alternative explicitly.
- Record a minimal submission identity and incremental accepted-job receipts on
  the execution side; return/persist partial IDs and per-job errors on ordinary
  failure. Keep this as small additive records rather than a new workflow engine.
- On transport loss, preserve available receipts, mark the outcome uncertain and
  stop. Give the agent the exact record and a reconciliation/manual-check path.
  No blind retry or exactly-once guarantee; automated adoption/resume is later.
  Stopping means no client-side retry/new submission action: a disconnected
  remote helper may still be running and writing receipts. Do not label its
  unreported jobs rejected or blocked without evidence.
- Add per-job environment exports with a clear literal/runtime-expansion rule,
  supporting CPU/thread limits without scientific application shell plumbing.
- Expose the same structured outcome through the supported Python/agent surface;
  retain useful human summaries. Add bounded regression tests for these cases.

*Done when:* an intentional second-job failure preserves the first accepted ID;
response loss does not submit the graph again; blocked dependents are visible;
the agent can distinguish rejected, partial and uncertain outcomes. Validate a
tiny DAG with mocked Slurm and transport failures; live checks are deferred.
Complete provenance and
package-version enforcement are not release blockers.

## MVP3 Trustworthy inspection for agents

Design: [MVP3 shared inspection](REFACTORING_DOCS/design/MVP3_shared_inspection.md).

- [x] **MVP3.0 Bound the observation contract.** Exact saved-run selection,
  one task view, explicit query errors/staleness, bounded logs and no recovery.
- [x] **MVP3.1 Centralize task and scheduler evidence.** Share array parsing,
  IDs and conservative aggregation. Query once per producing machine/operation;
  retain timestamps, errors, reasons and exit evidence. Overlay submission receipts.
- [x] **MVP3.2 Share inspection and log retrieval.** Python, ACP and terminal
  consume one result; exact selectors and local rediscovery survive context loss.
  Resolve bounded log reads from saved producing locations and update growing logs.
- [x] **MVP3.3 Verify and publish.** Exercise a mixed-outcome scientific array,
  missing/failed/stale observations, custom/raw-task logs and a second refresh;
  count external queries, update minimal human/agent guides and close locally.

**Outcome:** status, logs and agent inspection consume the same resolved job/task
view and show the evidence needed to continue after a context reset.

- Use one owner for task identity, array parsing, effective state and log mapping.
  Consolidate the selected active paths rather than building a general new index.
- Reuse the existing scheduler commands, query once per machine/operation where
  possible, and share their results across rendering and log resolution.
- Include observation time, query errors, unknown tasks and available failure
  reason/exit evidence. Label inferred causes and retain unknown causes honestly.
- Fix growing-log synchronization; preserve immutable definitions while updating
  mutable observations/logs. Reuse safe transfer tooling and recorded path roots.
- Provide structured list/inspect outcomes, exact saved-run selectors and bounded
  log excerpts; keep default terminal output compact. Avoid a second agent engine.
- Ship a short integration/operate/diagnose guide and a one-page human overview.
  A last-observed sidecar is acceptable if needed; a complete local memory layer
  and pervasive offline behavior are later enhancements.

*Done when:* one small array has completed, failed and unknown/active task cases;
terminal and agent agree on identity/status/log references; a fresh agent can
rediscover the run and explain observed failures; a second refresh updates an
existing log. Compare external-command counts for the exercised workflow to
catch duplicated cluster work. Do not promise a numeric speedup without a
measurement, or infer success because accounting returned no rows.

## MVP4 Submission responsibility boundaries

Design: [MVP4 submission boundaries](REFACTORING_DOCS/design/MVP4_submission_boundaries.md).

- [x] **MVP4.0 Review brittle concepts and bound this increment.** Shared preview/
  submit preparation, stable prepared scripts, explicit dispatch/evidence stages.
- [x] **MVP4.1 Extract preparation.** One validated/rendered in-memory bundle;
  separate data preparation from path preflight and shell checks. Preview and
  submission reject the same invalid definitions without scheduler effects.
- [x] **MVP4.2 Separate operation stages.** Public submission coordinates small
  record creation, script staging, dispatch and outcome persistence operations.
  Pass dependency IDs as scheduler arguments in both lanes; never edit prepared
  scripts during submission. Preserve partial/uncertain evidence on every failure.
- [x] **MVP4.3 Validate boundaries and close.** Exercise preparation parity,
  unchanged rendered scripts, pre/post-dispatch/storage failures and offline
  science runs. Record structure changes and full-suite results, then tag locally.

- [x] **MVP4.4 Activate local dev on explicit request.** Preserve baseline and
  user files, smoke-check an artifact, switch main to `dev`, verify base commands
  and isolated test imports, and update the working agreement/register.

**Outcome:** changing validation or rendering has one owner; tracking failures
cannot accidentally turn into a second submission or erase known IDs. This is
implementation modularity, developed locally with mocked Slurm/transport.

## MVP5 Inspection responsibility boundaries

Design: [MVP5 inspection boundaries](REFACTORING_DOCS/design/MVP5_inspection_boundaries.md).

- [x] **MVP5.0 Bound the responsibility changes.** Keep public selectors/results,
  command batching and cached no-network behavior. Identify hidden I/O, shared
  mutable dictionaries and cache/artifact failures that can corrupt evidence.
- [x] **MVP5.1 Separate collection and projection.** Load definitions/receipts
  and producing profiles explicitly, collect scheduler evidence, then project
  task/job states with a pure function. Malformed jobs cannot hide healthy runs.
- [x] **MVP5.2 Separate caches and artifacts.** Give observation/excerpt storage
  one owner, separate artifact attachment from state, decompose log transport and
  decoding, and eliminate the log-reader dependency on inspection orchestration.
- [x] **MVP5.3 Verify and close.** Test pure projection, no-network cached reads,
  cache/schema/write failures, partial scheduler evidence, immutable source data,
  bounded logs and existing CLI/Python/ACP/scientific workflows. Record remaining
  responsibilities and close with a local tag; no cluster operations.

**Outcome:** collection, state calculation, cache storage and artifact retrieval
have explicit interfaces. Keep existing JSON records and public signatures; no
persistent index, automatic recovery, storage migration or general backend layer.

## MVP6 Persistence and transport boundaries

Extract file transfer from bundle storage, consolidate configuration/transport
helpers, and make public exports explicit. Keep one active implementation per
concern and existing JSON records. Start with mechanical extraction before
changing behavior. No migration or module tree redesign required.

Design: [MVP6 persistence and transport](REFACTORING_DOCS/design/MVP6_persistence_and_transport.md).

- [x] **MVP6.0 Bound the change.** Read the active installation and take a 366-test
  offline baseline. Preserve public contracts/records and unrelated user files.
- [x] **MVP6.1 Extract owners.** Separate selection, configuration, file movement
  and transport helpers from local persistence; verify existing workflows.
- [x] **MVP6.2 Harden persistence and boundaries.** Share atomic JSON writes,
  prevent snapshot clobbering, consolidate configuration/transport use and make
  public exports explicit. Add focused failure checks before changing behavior.
- [x] **MVP6.3 Verify and close.** Run offline scientific/CLI/agent workflows;
  update guides, responsibility map, installation register and milestone tag.

**Outcome:** existing JSON formats and intended public functions retained;
configuration and bundle updates use the shared local record writer, transfers
have a dedicated adapter, and internal callers depend on their owning services.
No multi-writer locking, migration, retries or deployment framework was introduced.

## MVP7 Bundle-driven cluster software preparation

Design: [MVP7 cluster software preparation](REFACTORING_DOCS/design/MVP7_cluster_software_preparation.md).

**Outcome:** a bundle requests Git projects and a verified prepared runtime.
Omitted revisions resolve the current remote default-branch tip during preparation;
explicit revisions remain supported. Record exact resolved commits for each release.
The target machine owns dependency setup; a workstation/package lockfile is not
required. Resolve/fetch/install on the login/preparation host; compute jobs use
ready isolated releases. Existing jobs keep their code/environment. First-time
preparation clones missing repositories; managed code/environments use a separate
configurable root from scientific inputs and results (proposed `software_root`).

- [x] **MVP7.0a Confirm source/dependency defaults.** Record latest-by-default
  Git selection, exact resolved evidence and target-machine dependency ownership.
  Planning only; remaining MVP7.0 format/API/environment-role decisions stay open.

- [x] **MVP7.0b Confirm cloning and filesystem separation.** Record first-time
  clone support and independent code/results locations, preserving project-relative
  inputs/cwd. Naming/layout/configuration changes remain planned.

Start with the manifest attachment and helper/runtime environment separation;
then implement source materialization, installation checks, release readiness
and execution/agent evidence. Module responsibilities, detailed tasks and failure
cases are in the design. This MVP is planned, not implemented; live cluster
operations remain outside the current local-only scope.

## Optional scientific result retrieval (formerly proposed MVP4)

Deferred behind the modularity increments requested on 2026-11-11.


**Outcome:** pull a declared results subtree with include/exclude filters, so
merged summaries/figures can return without all large partial files.

*Done when:* paths use MVP1's resolver and producing-run identity; an interrupted
transfer is reported as retrieval failure without resubmitting compute; the
reference client receives only selected files. Keep scientific validation in the
client. Schedule this immediately after MVP2 if results retrieval blocks actual
science; otherwise finish trustworthy inspection first.

## Scientific reference case

Use a cheap application with an installed command, relative inputs/outputs,
explicit workers/resources and useful nonzero failures. Evolve it from one job
to a four-task array plus a reducer with one deliberately failing task. Verify:

- Every accepted submission and uncertain outcome has an identifiable record.
- A new agent finds the exact run/task and evidence without private filesystem
  conventions, a copied terminal table, or prior chat context.
- Output ownership and original task indices are explicit; successful shards
  do not become evidence that the whole study succeeded.
- Existing array/dependency primitives remain sufficient for initial map/reduce.
  A retry with changed code/inputs must not silently merge incompatible results;
  automated retry and downstream repair remain deferred.

## Later product layers

These remain desired outcomes with no near-term delivery estimate. Open a design
only when its user benefit justifies the next increment.

| Layer | Work deliberately deferred |
|---|---|
| L1 Richer tracking and recovery | Full versioned definition/run/attempt model, persistent offline index, automatic interrupted-submission reconciliation/resume, historical import/migration |
| L2 Scientific workflow conveniences | Failed-shard retry automation, reducer replacement/repair, map/reduce helper, stronger provenance/version checks and optional completion manifests |
| L3 Complete distribution and documentation | Public index release, broad wheel/source/Python/OS matrices, polished/versioned human site, complete installed agent resource delivery, upgrade automation |

Keep basic development installation and accurate minimal guides working in each
MVP. Perform a narrow wheel smoke check before promotion. Complete publication,
site structure, reference generation and comprehensive compatibility are not
prerequisites for improving daily reliability. No automatic deployment,
multi-machine routing or monitoring service is included.

## Interaction coverage

The [interaction map](REFACTORING_DOCS/interaction-map.md) still describes the full
product. Early MVPs support bounded parts, not every outcome in that map.

| Interactions | First useful delivery | Later depth |
|---|---|---|
| I00 installation; I01 context | MVP0 recipe and promotion smoke check | L3 public distribution and complete capability/docs packaging |
| I02 client integration; I03 readiness; I04 definitions; I05 preview | MVP1 shared roots/selection, small reference client; MVP2 validation/env | L1 richer models; L2 full version checks |
| I06 submission; I07 interruption | MVP2 known/partial/uncertain outcomes and receipts | L1 automated reconciliation and resume |
| I08 rediscovery; I09 refresh; I10 inspect; I11 diagnosis; I16 handoff | MVP3 shared task view, bounded evidence and minimal structured interface | L1 persistent index and richer context |
| I12 results | Optional result retrieval when needed | Broader artifact policies only when justified |
| I13 cancellation; I15 cleanup | Retain working commands in their release lane; protect unknown work | Consolidate when touching their shared state; broader retention policies later |
| I14 retry/downstream repair | Manual explicit recovery using recorded evidence | L2 automation and compatible-output rules |

## Decisions log

| Date | Decision | Reason |
|---|---|---|
| 2026-11-09 | Follow Gaia's living plan, one-task workflow, completion criteria and task-ID commits | Keep work reviewable across sessions |
| 2026-11-09 | Keep AutoSlurm's implementation; agents operate from the workstation and compute jobs use prepared environments | Fit the existing workflow without a platform migration |
| 2026-11-09 | Map interactions and teach client software practices as well as operating commands | Reduce agent context gaps and fragile client integration |
| 2026-11-09 | Applications declare relative paths; AutoSlurm resolves one selected machine per run | Centralize portability without multi-machine orchestration |
| 2026-11-09 | Human docs teach purpose, system map and examples; agent docs carry detailed supported contracts; pip distribution remains a goal | Complementary audiences for one engine |
| 2026-11-09 | Deliver small reliability/agent MVPs before a complete package; allow intentional breaking releases | Improve the working software quickly instead of gating benefits on the full roadmap |
| 2026-11-09 | Establish the shared working rules before creating installations or changing runtime behavior | Keep daily use and application agents operational while identifying the actual stable/development setup |
| 2026-11-09 | Work locally and mock Slurm/remote interactions; defer cluster discovery and live checks | Explicit user instruction; base Conda installation supplies local installation evidence |
| 2026-11-09 | Retain the original checkout at detached baseline HEAD; implement in `.development/checkout` with a separate environment/state | Protect base Conda imports without reinstalling its package or moving its tracking root |
| 2026-11-09 | Use `AUTOSLURM_STORAGE_ROOT` locally and explicit remote machine `storage_root`, with helper support/root verification | Keep configuration, scripts, observations and default results in the chosen installation; reject invalid/mismatched selections |
| 2026-11-11 | Publish a current client recipe in task-specific agent context; validate with an independent installed application | Teach scientific software boundaries, actual relative-path bases, exact selection and evidence handoff before broader refactoring |
| 2026-11-11 | Pull a narrow exact-file submission fix forward from MVP1 | The reference test showed an imported definition could reload a neighboring draft; return the saved path and load it directly, retaining timestamp identity independently of mtime |
| 2026-11-11 | Implement one execution context with project-relative inputs/cwd, results-relative outputs and saved producing roots | Same relative science definition works from unrelated directories under two profiles; remote submission resolves storage once and batches required-input checks; no input staging or broader recovery engine |
| 2026-11-11 | Use the existing DAG driver for both lanes with incremental execution-side receipts; retire implicit legacy graph submission | Preserve accepted IDs before the next scheduler call, distinguish partial/unknown outcomes, and refresh exact evidence without any automatic resubmission or adoption |
| 2026-11-11 | Consolidate inspection around exact saved paths, one scheduler/task view and producing-path log tails | Preserve missing/error/stale evidence, reduce duplicated queries, and give terminal/ACP/Python the same identity/state contract; no retry or scientific-success inference |
| 2026-11-11 | Prioritize small modularity MVPs: submission, then inspection, then persistence/transport | User requested careful decomposition of brittle concepts and overloaded functions; defer optional result retrieval and preserve existing records/failure guarantees |
| 2026-11-12 | Activate `dev` in the main folder for base Conda daily use, preserving rollback source and user files | Explicit user choice replaces the initial pinned-main/nested-development editing arrangement; cluster installations remain unchanged |
| 2026-11-12 | Add MVP7 for bundle-specified Git projects and verified prepared environments | User requested less manual cluster maintenance; prepare isolated releases before dispatch and separate helper/runtime environment roles |
| 2026-11-12 | Split inspection into explicit collection, pure projection, cache storage and artifact retrieval | Remove hidden scheduler/config reads, isolate malformed records and make cache/artifact failures unable to erase or contaminate scheduler evidence |
| 2026-11-12 | Separate local record/selection/configuration/transport owners, share atomic publication and explicit exports | Mechanical extraction retained all 366 existing tests; seven reproduced bugs motivated scoped fixes without changing JSON shapes or submission uncertainty rules |
| 2026-11-12 | MVP7 omitted revisions resolve latest upstream; dependency setup belongs to the selected machine | User requested less friction and different dependency sets for local and cluster use; resolved commits and actual installations remain recorded, with no silent stale-source fallback |
| 2026-11-12 | MVP7 prepares missing Git repositories and separates managed software from input/result filesystems | User needs first-time cloning and independent package/results placement; preserve existing path bases and record producing paths so agents can locate both |

Technical details of lane setup and promotion are proposed in MVP0. The user's
priority change accepts the smaller scope; it does not mean every future schema
or migration decision has already been accepted.

## Done log

| Date | Task | Validation and commit reference |
|---|---|---|
| 2026-11-09 | Prior M0.0 and M0.0a planning drafts | Preserved in the archived roadmap; no implementation task completed |
| 2026-11-09 | MVP0.0 Layer the plan into usable MVPs and defer product completion | Documentation/traceability checks; commit reference: `git log --grep '^MVP0.0:'` once committed |
| 2026-11-09 | MVP0.0a Working agreement, unverified installation register and initial agent operating guide | Documentation/link checks and read-only agent-context smoke check; files remain uncommitted pending baseline identification |
| 2026-11-09 | MVP0.1 Local installation inventory and executable baseline | Source reference `33bcbd34fb167fca67aa64739a013073c64167b1`; 195 unit tests and four mocked three-job submission cases pass in a disposable offline environment; accounting-probe mock gap recorded in MVP0 design. Source/tests and base installation unchanged; no stable pin, cluster access or promotion; documentation remains uncommitted |
| 2026-11-09 | Initial planning/baseline documents saved | `efff9b6` on the development branch; pre-existing README and Gaia requirements edits excluded |
| 2026-11-10 | MVP0.2 Local isolation and explicit storage selection | 238 full offline tests pass, including 18 new root/isolation cases; editable development install and fresh-process discovery verified. Stable source remains unchanged at detached baseline HEAD. Task commit: `git log --grep '^MVP0.2:'` on `codex/mvp0-isolation`; no push, promotion or remote operations |
| 2026-11-11 | MVP0.3 Current client recipe and scientific reference workloads | 245 full offline tests pass; 13 focused client/context checks pass after final failure-case/documentation updates. Installed standalone application produces matching single/reduced summaries. Expected timestamp-collision warnings exercised by competing-draft tests. Task commit: `git log --grep '^MVP0.3:'`; local milestone tag `mvp0` at closure, without promotion |
| 2026-11-11 | MVP1.0–MVP1.3 Shared paths, selection, saved execution and scientific integration | 270 full offline tests pass in 2.27 s; five expected timestamp-collision warnings. Two-profile array/reducer runs, nested cwd/space handling, activation failure, invalid/missing inputs before submission, one remote root probe plus batched preflight, and saved local/remote artifacts without current-profile discovery verified. Report: `.development/test-runs/mvp1-final.xml`. Guides/schema and examples updated. Task commit: `git log --grep '^MVP1.3:'`; local tag `mvp1` at closure. Stable source/runtime unchanged; no push, cluster access or promotion |
| 2026-11-11 | MVP2.0–MVP2.3 Safer submission, receipts and exact inspection | 295 offline tests pass in 2.62 s; 28 expected snapshot-collision warnings. Same-level/later rejection, interruption/malformed output, response loss after final and unfinished helper execution, persisted/in-memory accepted IDs on storage failure, capability/replay guards, read-only refresh with recorded transport, rejection of changed identities/IDs, protected cleanup, shell syntax and literal/runtime exports verified. Report: `.development/test-runs/mvp2-final.xml`. Task commit: `git log --grep '^MVP2.3:'`; local tag `mvp2` at closure. Stable source/runtime unchanged; no push, cluster access or promotion |
| 2026-11-11 | MVP3.0–MVP3.3 Shared inspection and bounded log refresh | 313 offline tests pass in 3.87 s; 29 expected snapshot-collision warnings. Mixed scientific array, missing/failed/stale observations, queue/accounting conflicts/errors, raw/dot task IDs and excluded steps, saved transport after profile edits, exact receipt overlay without writes, remote second refresh, checksum log sync and cached no-network reads verified. Shared status/inspect/ACP evidence and task-context handoff checked. One scheduler SSH plus one selected-log SSH in the remote scenario; two local scheduler commands across multiple runs. Report: `.development/test-runs/mvp3-final.xml`. Task commit: `git log --grep '^MVP3.3:'`; local tag `mvp3` at closure. Stable source/runtime unchanged; no push, cluster access or promotion |
| 2026-11-11 | MVP4.0–MVP4.3 Shared preparation and submission responsibility boundaries | 333 offline tests pass in 3.22 s; 39 expected snapshot-collision warnings. Four preview/submit inconsistencies and accepted-ID loss on receipt-write interruption reproduced and fixed. Pure preparation, copied values, exact preview/script/path parity, dependency flags for both lanes, initial/staging/transport/session/response/final-tracking failures and known-ID retention verified. `submit_jobs`: 116 to 20 lines; preparation, preflight, record/staging/dispatch/outcome persistence have explicit owners. Report: `.development/test-runs/mvp4-review.xml`. Task commit: `git log --grep '^MVP4.3:'`; local tag `mvp4` at closure. Stable code/import/runtime unchanged; development-only changes, no push, cluster access or promotion |
| 2026-11-12 | MVP4.4 Local dev activation and MVP7 scope | Main switched to `dev` at tested MVP4 revision `89e2781`; existing base editable import/commands now use it without a base environment reinstall. Baseline retained in `.development/stable`; original files backed up/stashed and two user documents restored unchanged. Isolated wheel import/preview/cached-inspection smoke passed. Test environment repointed to main source with separate test state; 333 tests passed again in 3.55 s from the active checkout (`.development/test-runs/dev-main-activation.xml`). MVP7 planned with explicit Git/release/environment responsibilities; no remote operations performed. Activation commit: `git log --grep '^MVP4.4:'` |
| 2026-11-12 | MVP5.0–MVP5.3 Inspection responsibility boundaries | 366 offline tests pass in 3.15 s; 39 expected snapshot-collision warnings. Four initial failure regressions reproduced and fixed; 33 added checks cover pure projection/reference selection, invalid IDs/producing profiles, schema/cache-write failures, bounded remote decoding, cached identity/no-network behavior, receipt identity and changing definitions. Existing science/CLI/ACP/receipts pass. `inspect_bundles` 80→22 lines; `read_job_logs` 114→24, with effectful stages separated from pure calculation. Report `.development/test-runs/mvp5-final.xml`. Task commit: `git log --grep '^MVP5.3:'`; local tag `mvp5` at closure. Main dev/base imports retained; daily/rollback state untouched; no cluster operations, migration, dependencies or push |
| 2026-11-12 | MVP6.0–MVP6.1 Boundaries and mechanical extraction | 366 existing offline tests pass in 3.52 s, 39 expected warnings. Configuration/transport/file transfer/selection now have dedicated owners, with historical import aliases. No behavior fixes yet. Task commit: `git log --grep '^MVP6.1:'` |
| 2026-11-12 | MVP6.2–MVP6.3 Persistence hardening and closure | 392 offline tests pass in 3.27 s, 39 expected warnings; 26 added checks. Reproduced and fixed serialization corruption, partial new files, timestamp clobbering, explicit-profile replacement, key-path splitting and sync transport failure presented as success. Verified interruption/publication failures, exclusive collision races, atomic batch append, staging/copy failures, no hidden process in local operations, pure SSH construction, exports and all prior scientific/CLI/ACP/receipt cases. Report `.development/test-runs/mvp6-final-reviewed.xml`. Task commit: `git log --grep '^MVP6.3:'`; local tag `mvp6` at closure. Base import/help verified; baseline source and all persistent runtime roots unchanged; no cluster/dependency/migration/push operations |
| 2026-11-12 | MVP7.0a Source and dependency defaults | User-confirmed design refinement: optional revisions resolve latest remote default-branch commit per new preparation; target-machine dependency policy replaces mandatory package/local locks. Planning text and failure criteria reviewed; no code changes or application tests. MVP7 implementation and remaining contract decisions remain open |
| 2026-11-12 | MVP7.0b Cloning and filesystem separation | User-confirmed requirements recorded with proposed software_root, first-clone/fetch behavior, independent input/result locations, configuration visibility and producing-path evidence. Reviewed local path/configuration implementation and design links; documentation only, no application tests or cluster operations |

## How we work

Follow [WORKFLOW.md](WORKFLOW.md) for the task loop, test gates, operational
context, session handoff, and promotion/rollback. This plan records what is
next and complete; do not maintain a conflicting second procedure here.

Development can proceed on main in an isolated checkout. At an MVP boundary,
record checks/limitations and a collision-free tag such as `mvp1`; push according
to the implementation session's instructions. Neither those Git actions nor
completion of an MVP selects a new production installation. Keep the previous
installation managing its jobs until an explicit release action changes routing.

Commands: `python -m pip install -e '.[test]'`; fast tests:
`python -m pytest -q tests/unit`; full offline tests after isolation review:
`python -m pytest -q tests`. Documentation-only changes need diff and link checks,
not application tests. Real cluster checks are explicit and separate from default
tests. Planning does not authorize creating installations, submitting test jobs,
changing the active environment, migrating records or publishing a release.
