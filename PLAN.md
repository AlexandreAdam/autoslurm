# AutoSlurm MVP plan

Improve the working package in independently usable increments. Prioritize
relative paths, one implementation of each core rule, submission safety, and
agent usability. Keep the larger product design as a direction rather than a
prerequisite for using the first improvements.

This file is the source of truth for active scope, task order and progress.

## Status

- **Current milestone:** MVP10 in progress; MVP10.1 audit, MVP10.2 diagnostic
  foundation, MVP10.3a configuration, MVP10.3b authoring/selection/path/render
  and MVP10.3c.1 shared JSON publication diagnostics complete
  locally. MVP9 complete locally; MVP7.2f editable-update amendment
  and FIX.CONFIG.1 optional-account fix complete; FIX.LOGS.1 navigation complete.
  FIX.SOFTWARE.1 simplifies editable builds and composes setup/activation.
  FIX.DEPENDENCY.1 defaults dependent jobs to kill-on-invalid-dep=yes.
  MVP9.1–3 typed command contracts, literal compiler and public adoption are
  complete. A local `mvp9` tag records closure without a remote rollout.
  MVP7 single-checkout software updates are complete. The user has
  superseded the source-copy/installed-release architecture because cluster file
  limits require one existing checkout per project.
- **Stage:** main checkout remains active on `dev` through base Conda's editable
  install; tests use `.development/python` and separate temporary state. Pinned
  rollback source remains unchanged. Full offline suite: 1058 passed, 43 expected
  collision warnings. Historical MVP7.2 test evidence describes the removed design.
- **Latest completed task:** MVP10.3c.1 adopts shared JSON publication diagnostics.
  RecordWriteError retains destination/stage/native cause and separates publication
  from directory durability; syscall failures keep unknown outcomes. Cleanup cannot
  mask primary errors or interruption. Only clean exclusive collisions advance a
  snapshot timestamp. Serialization now uses this explicit dev exception family.
  1058 full offline tests and clean-wheel smoke pass.
  Coverage: 260 routes/135 owners/18 broad catches; two new resource/evidence
  safeguards explicitly reviewed. No daily profile,
  environment, cluster, persisted-format or rollback change.
- **Next task:** MVP10.3c.2 bundle/config record boundaries, using the
  [completed audit](REFACTORING_DOCS/design/MVP10_api_failure_audit.md).
  Integrate the diagnostic model at meaningful operation boundaries; most current
  service errors still have no diagnostic. c.2 domain reads/enrichment/CLI and
  c.3 receipt/cache/script persistence remain open;
  stale-venv correction is MVP10.4.
  MVP11 and MVP12 are
  separately scoped, unimplemented milestones; their numbers do not require a
  single large combined release. Their API/record details remain proposals.
  MVP9 implements readable command integration; MVP10 follows with
  an API-wide error review and dedicated shared error module. MVP10 now starts
  with a complete interface/failure inventory before migrating operation boundaries;
  the stale-venv case is one regression among many. The error module is implemented;
  service integration and public route parity remain pending.
  Cluster access/installations
  remain outside the local development scope; tests mock transport and use a
  disposable local environment. Machine-owned dependencies are not updated.
- **Scope update:** local code/tests only, with temporary Git repositories and
  mocked SSH/Slurm. No actual cluster pull, install or cleanup is performed.
  Source is intentionally shared/mutable under the single-copy requirement;
  the operator coordinates update timing for jobs using it.
- **Last updated:** 2026-11-14.
- **Working agreement:** [WORKFLOW.md](WORKFLOW.md).
- **Repository workflows:** removed the two GitHub Actions workflow files on
  `dev`; GitHub repository settings and documentation integrations stay as they were.
- **Installation evidence:** [installation register](REFACTORING_DOCS/installation-register.md)
  and [baseline results](REFACTORING_DOCS/design/MVP0_safe_development.md#local-baseline-mvp01).
- **Current execution scope:** local only. Mock Slurm and remote commands in
  tests; no SSH, live submissions, remote discovery or cluster installation.
  User-authorized exception: read-only Git and installed-package inspection on
  `rusty` for the software status demonstration; no remote writes or live jobs.
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
| MVP7 | Update one checkout and refresh its editable project install | Delivered in small slices | Operator-managed existing environment/dependencies; update timing coordinated for shared jobs |
| MVP8 | Clear bounded stdout/stderr inspection with failure evidence | Half to one day | Execution logs only; scientific results remain application-owned |
| MVP9 | Declare command options once; validate readable job arguments and render the same invocation | Two to three focused days for the narrow profile | Static scalar options first; no remote Python launcher or universal CLI adapter |
| MVP10 | Consistent actionable diagnostics across the public API, backed by an isolated error module | Multi-slice milestone; estimate after the API audit | Audit all Python/CLI/ACP boundaries; migrate deliberately without flattening partial/unknown outcomes |
| MVP11 | Readable status reasons in the job row, including named dependency waits | Three bounded slices; estimate after the reason/projection contract | Reuse observations; no queue ETA, extra queries or automatic recovery |
| MVP12 | Reusable resource/review/run/retry workflows, with an optional task runtime | Layered milestone; estimate each slice before implementation | Public API and agent/human adoption per slice; runtime packaging and scientific-result fetching have separate decision gates |

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

## MVP7 Software status and single-checkout Git updates

Design: [MVP7 software updates](REFACTORING_DOCS/design/MVP7_cluster_software_preparation.md).

**Outcome:** explicitly pull the latest upstream changes into the existing
project checkout selected relative to `software_root`. One source copy per
project. This layer creates no clones, Git mirrors/worktrees, source sets,
additional environments or preparation/release records. MVP7.2f refreshes the
editable project installation in the configured existing environment.
Submission and compute jobs stay independent and use configured environments.

The user's 2026-11-12 clarification supersedes the earlier immutable-release and
source-pin strategy. Update the current branch's configured upstream with
`git pull --ff-only`; do not guess or switch branches. The user's subsequent
MVP7.2f amendment adds editable installation without restoring the release engine.

- [x] **MVP7.0a/b Initial source/dependency/clone planning.** Historical decisions;
  clone/source-copy requirements are superseded by MVP7.2e. Dependencies remain
  machine-owned; optional first-clone and revision deployment are out of scope.
- [x] **MVP7.0c Simplify config and application roots.** Canonical `config`,
  `software_root`, shared inputs/cwd/outputs under `results_root`, historical paths.
- [x] **MVP7.0d Use SSH config aliases only.** SSH owns host/user/key settings.
- [x] **MVP7.1 Source/manifest engine.** Delivered then superseded: copy-producing
  source/cache engine is removed by MVP7.2e. Pure historical manifest validation
  remains; runtime requests do not select an installation.
- [x] **MVP7.1b Inspect software/environment compatibility.** Existing read-only
  Git and selected-interpreter metadata comparisons remain supported. Status does
  not fetch, update code or establish scientific correctness.
- [x] **MVP7.2a–d Installed releases and job selection.** Delivered then superseded:
  release/wheel/installation/record machinery and job release selectors are removed
  by MVP7.2e. Historical operation evidence is retained without migration/deletion.
- [x] **MVP7.2e Replace preparation with one-checkout updates.** Remove all active
  duplicate-copy and installation paths. Expose `asl software update --machine
  NAME --project PATH` and `update_software`, pulling an existing clean tracking
  branch once with fast-forward only. Return before/after commit evidence; keep
  local changes and fail detached/missing/untracked/diverged branch cases. Lost
  responses/timeouts are unknown, without retry or local fallback. Use existing
  SSH/profile/status owners and create no additional files outside normal Git
  metadata/working-tree changes. Preserve configured job execution and saved data.
  Verify with mocks and real temporary local Git repositories, full offline tests,
  accurate human/agent documentation and artifact/help smoke. No live cluster work.

- [x] **MVP7.2f Refresh the editable installation after pulling.** User requested
  default editable installation so new command-line tools are available. Preflight
  the configured environment, pull once, then run its Python/pip against the same
  checkout even if HEAD is unchanged. No dependency updates, release copies or
  environment creation. Report install success separately from Git changes and
  preserve post-pull commit evidence on install failure/timeout/response loss.
  Test failures, exact SSH stdin worker, and a real temporary editable package
  gaining a CLI; update human/agent docs and run full offline/package checks.

The [agent recipe](agent/13_software_preparation.md) is the current integration
boundary. `prepare_software_sources`, `prepare_software`, `inspect_software_release`
and release selectors are removed. Existing source/release copies and records are
not automatically deleted: actual cluster cleanup is a separate operator action.
There is no broader deployment/ACP preparation/runtime manager planned in this
layer; scientific dependencies/build tools and environment creation remain operator-managed.

## FIX.SSH.1 Submission connection ownership

- [x] Inspect effective settings using non-connecting `ssh -G` through the shared
  adapter. With a configured ControlPath and automatic master/persistence, yield
  no overrides and never explicitly open/close the user's connection.
- [x] Otherwise retain an owned session with a short `/tmp/asl-ssh-*/cm-%C` path
  on POSIX, falling back to the default temp directory if `/tmp` is absent.
  Failed/malformed configuration inspection falls back once. Local sessions
  remain no-ops; no new settings, keys, passphrase handling or SSH config edits.
- [x] Verify ownership/options, long TMPDIR, fallback and both submit callers,
  then run the full offline suite and update the SSH docs/Done log. No cluster
  commands; push the completed dev commit. Resume the separately saved MVP8 work.

## MVP8 Robust execution-log retrieval

Design: [MVP8 execution logs](REFACTORING_DOCS/design/MVP8_execution_logs.md).

The user explicitly narrowed retrieval to AutoSlurm execution evidence:
stdout/stderr, Slurm `.out` files and scheduler status explaining job outcomes.
Scientific datasets/results stay application-owned. No generic result downloader,
file-type allowlist or recursive output-directory scan is included.

- [x] **MVP8.1 Clear log interface.** Expose `inspect_logs` and make `asl logs`
  retrieve logs by default for one exact saved bundle/receipt. Support job, task,
  stdout/stderr, existing tail/byte/file bounds and explicit cached inspection.
  Reuse the inspection pipeline and keep producing paths/transport stable.
- [x] **MVP8.2 Harden reads and evidence.** Share a bounded regular-file reader
  between local and SSH paths; distinguish empty, missing, unreadable, transport
  failure and cache absence/staleness. Detect concurrent changes, reject malformed
  responses, deduplicate candidate reads and preserve partial evidence. No fallback
  to another host or datasets, no job retry, no full-log mirroring.
- [x] **MVP8.3 Verify and document.** Exercise array/custom/merged/separate logs,
  failure and cache cases, exact SSH payload, CLI/Python parity and existing science
  workflows. Update human/agent rules, full offline tests and package smoke; local
  milestone tag at closure. Actual cluster access remains outside this task.

## DOCS.1 Lasting client argument preference

- [x] Save Alexandre's explicit, named, readable job-argument preference in
  AGENTS.md and the client/bundle/operating recipes. Prefer typed Typer commands
  per job kind; one scalar script_args value per setting, CSV lists, default-off
  booleans and shell-safe strings. Reject opaque configuration payloads and teach
  client-side signature/name/type/value validation before saving/submitting.
- [x] Record the accepted preference in the agent documentation design, review
  the renderer for accuracy, inspect the documentation diff and relative links.
  This task changes no implementation, saved jobs, application source or cluster.
  Application tests are not rerun for this documentation-only change.

## DOCS.2 Map job script interactions before choosing another style

- [x] Trace direct application/manual Slurm use, AutoSlurm CLI, embedded Python
  planner, client CLI, existing bundle JSON and ACP through definition saving,
  preview/preparation, Slurm rendering/dispatch, execution and receipt/log evidence.
  Record the current CLI/Python/path/argument differences and the roles of JSON.
- [x] Compare command-based execution, simpler Python authoring, application-read
  job JSON and remote Python function invocation. Mark working principles and
  future argument-contract changes proposed, preserving accepted DOCS.1 guidance.
  Check source references, Markdown/diagram and links. No execution behavior,
  client application, bundle records, cluster operations or test baseline changes.

See [the job-script map](REFACTORING_DOCS/interaction-map.md#job-script-interactions-current-code-and-design-review).

## DOCS.3 Investigate a readable command/job pattern

- [x] Compare the existing engine, argparse reference client and Gaia's typed
  registry/CLI/builder to identify reusable plumbing and client-owned policy.
  Exercise command metadata, typed parsing, current renderer round-trip and
  callbacks in an isolated disposable design probe; no scientific task execution.
- [x] Write a concrete proposed client/JSON/preview walkthrough, validation and
  human-review contracts, version/callback limitations and small candidate slices.
  Keep hypothetical APIs/format changes unimplemented and DOCS.1 unchanged.
  Check documentation links/examples; retain the existing full-suite baseline.

Design: [readable command/job pattern](REFACTORING_DOCS/design/job_command_pattern.md).

## FIX.CONFIG.1 Optional Slurm account and clearable config

- [x] Normalize absent/null/blank accounts as unset; remove the required-account
  selection check. Preserve configured/explicit job accounts and existing records.
- [x] Add direct account set/clear flags without remote checks; let the interactive
  editor clear optional fields explicitly while Enter keeps existing settings.
- [x] Verify config persistence, preview and mocked submission without an account;
  run the full offline suite, update human/agent docs and the config design.

## FIX.CONFIG.2 Edit environment setup interactively

Requested ahead of MVP10.3; no MVP10.3 implementation started.

- [x] Prompt for optional env_command when creating/editing a machine; Enter
  retains it and `-` clears it. Persist through the existing config writer and
  retain setup-before-activation and post-save validation behavior.
- [x] Verify public interactive creation/editing, saved settings, validation and
  rendered preambles offline; update human/agent guidance and configuration design.

## FIX.LOGS.1 Logs navigation consistent with status

- [x] Accept status bundle names/indices/ranges, latest/date selection and job
  names/row indices, including expanded array rows and exact task selection.
  Share the existing inspect selection rule rather than duplicating it.
- [x] Keep exact bundle/receipt selectors for durable agent identity, cached
  no-contact behavior and bounded reads; apply array filters before file limits.
- [x] Add offline navigation/identity/invalid-selection regressions, run the full
  suite and update terminal/agent examples, design and verification evidence.

## FIX.SOFTWARE.1 Plain isolated editable install and composed activation

- [x] Remove no-build-isolation/no-index from editable reinstall; retain no-deps,
  selected interpreter, cache/redirection guards and existing update semantics.
  Temporary pip build environments/downloaded build requirements are allowed on
  the login host; scientific dependencies and persistent environments stay unchanged.
- [x] Include a bounded last-20-line pip output tail in failed install evidence
  and messages, omitting credential-bearing URL lines. Preserve pulled commit,
  failed/unknown states and no-retry behavior; the broad MVP10 remains separate.
- [x] Compose env_command then venv activation, retaining single-setting behavior.
  Verify scripts and local shell execution plus real offline isolated editable
  installation through the local/fake-SSH fixture. Update docs/rules, full offline
  checks and package smoke; no cluster operation or daily environment/config edit.

## FIX.DEPENDENCY.1 Cancel jobs with impossible dependencies by default

- [x] Add `#SBATCH --kill-on-invalid-dep=yes` when a job declares dependencies,
  preserving explicit per-job Slurm overrides and leaving root jobs unchanged.
  Keep preview/staged scripts identical across local/remote execution, do not
  mutate saved definitions, and retain command-line dependency ID binding.
  Verify mocked submission and offline regressions; update human/agent guidance.

## MVP9 Readable command arguments without duplicated client plumbing

Design: [command/job pattern and MVP9 scope](REFACTORING_DOCS/design/job_command_pattern.md#mvp9-delivery-scope-planned).

The user requested this MVP after the DOCS.3 investigation. Keep ordinary
Python scripts/installed commands and readable named `script_args`; the
architecture sketches remain proposals until each task settles its interface.

- [x] **MVP9.1 Single-declaration proof.** Support a deliberately small typed
  named-option profile in the reference client. Derive names/types/static defaults
  from one lightweight command declaration; validate native values before save.
  Reject unknown/unsupported options without running science, callbacks, prompts
  or dynamic defaults. Keep Typer optional and capability-checked; core contracts
  contain plain data. Settle the public helper syntax and saved-data boundary.
- [x] **MVP9.2 One argument compiler.** Resolve declared paths through existing
  policy, compile literal argument tokens once, then quote for Slurm shell output.
  Preview and submission consume the same result. Verify parser round-trips,
  including spaces/metacharacters, static defaults, booleans and path values.
  For this small release retain scalar/CSV/default-off guidance; reject unsupported
  list/tuple/default-on boolean semantics in the typed authoring contract rather
  than silently guessing. Raw bundles retain existing space-style lists and
  positionals with literal quoting; no new list/boolean style is introduced.
- [x] **MVP9.3 Supported authoring routes and adoption.** Expose the agreed builder
  to Python/client CLI/agent recipes, alongside existing raw-script authoring.
  Avoid help-text guessing for supported declarations. Demonstrate one client
  end to end with flat JSON, readable preview/script, arrays/dependencies and
  unchanged receipts. Record the compatibility/release boundary before changing
  any persisted shape or argument meaning; run offline and package checks.
  Public helpers retain the proven names; validate_job requires a supplied trusted
  contract and every saved setting. No schema/import lookup or migration added.

Completion: an agent declares a supported command once, builds and validates
named settings locally, and a human can understand the job from JSON/script.
Repeated options, tuples, arbitrary parser integrations and broader boolean
styles are later slices; no per-job style switches are adopted by this plan.

## MVP10 Actionable failures with preserved evidence

Design: [error handling](REFACTORING_DOCS/design/MVP10_actionable_errors.md).

The user's PLAN.2 amendment expands this from selected message fixes into a
full public-interface reliability milestone. The initial failure/placement map
is in the design; every callable/action and its outcome contract must be reviewed.

- [x] **MVP10.1 API and failure inventory.** Account for every supported Python
  export, CLI action/alias/standalone entry point and ACP action. For each record
  inputs, failure types, effect boundaries, current exception/returned-error shape,
  translation owner, desired diagnostic, next action and regression evidence.
  Identify broad catches, swallowed causes, false 'missing' results, inconsistent
  exit behavior and loss of partial success; finalize the coverage register.
  Completed [audit and priorities](REFACTORING_DOCS/design/MVP10_api_failure_audit.md)
  with a per-owner plain-data register, canonical alias mapping and read-only
  AST coverage checker. Operation adoption remains pending in MVP10.3–9.
- [x] **MVP10.2 Dedicated error module.** Add one dependency-light owner for error
  codes/categories, structured diagnostics, context/cause preservation, named
  diagnostic constructors and safe serialization. Keep CLI rendering in a thin
  presentation adapter using those same diagnostics. Isolate unit tests; do not
  import backends, run commands or decide recovery in this module. Preserve public
  exception/receipt contracts and settle additive data/debug/exit-code conventions.
  Implemented errors.py and opt-in apps/error_output.py, with explicit public
  submodule imports and packaged diagnostic recipe. No universal service/CLI/ACP
  migration or automatic outcome classification; later slices adopt the core.
- [ ] **MVP10.3 Configuration, authoring and persistence.** Integrate at config,
  selector, command/argument/path validation, bundle graph/render/preflight and
  local record publication boundaries. Distinguish invalid/missing/inaccessible/
  corrupt data and before-vs-after-publication failures. Show exact fields, named
  job options and logical/resolved paths without altering historical evidence.
  Split before implementation to keep each adopted boundary reviewable:
  - [x] **MVP10.3a Configuration diagnostics.** Diagnose read/JSON/profile/selection
    and setting-validation failures through the shared core. Wire the config CLI
    aliases/standalone entry points; preserve unreadable/corrupt existing files,
    explicit root selection and original causes. Unexpected bugs stay visible.
    Publication I/O effects remain with MVP10.3c.
  - [x] **MVP10.3b Authoring, selection and paths.** Adopt diagnostics in command/
    argument/graph/manifest validation, snapshot selection and pure path/render
    preparation; keep invalid requests distinct from per-entry broken evidence.
    Split before implementation into independently verified boundaries:
    - [x] **MVP10.3b.1 Authoring diagnostics.** Typed command/adapter/literal
      arguments, dependency graphs, software-intent metadata, save/schedule input
      guards and in-memory bundle preparation. Preserve explicit options, attach
      field/option/job context and native causes; wire the schedule CLI. Invalid
      requests stop before publication/dispatch; no broad bug-to-validation catch.
    - [x] **MVP10.3b.2 Snapshot selection diagnostics.** Exact/index/latest/filter
      selection and per-entry broken/unavailable evidence, without silently
      turning unreadable records into empty jobs or choosing a different bundle.
    - [x] **MVP10.3b.3 Path/render preparation diagnostics.** Pure path resolution,
      logical/resolved/job identity and render validation; keep external readiness
      failures and record publication with their separately planned owners.
  - [ ] **MVP10.3c Record persistence.** Adopt local JSON read/publication diagnostics
    for bundles/config/receipts/cache, distinguishing not-published/published/unknown
    effects and secondary cleanup failures. Preserve saved data and accepted IDs.
    Split before implementation into independently tested boundaries:
    - [x] **MVP10.3c.1 Shared JSON publication.** Diagnose serialization and
      filesystem stages at the atomic writer, retaining known/unknown publication,
      durability and secondary cleanup failures. Preserve exclusive collision
      behavior without retrying a write whose publication or cleanup is uncertain.
    - [ ] **MVP10.3c.2 Bundle/config record boundaries.** Adopt direct bundle reads,
      append/metadata records, config writes and related CLI presentation; preserve
      existing files and enrich shared publication diagnostics with domain identity.
    - [ ] **MVP10.3c.3 Receipt/cache/script persistence.** Adopt local receipt/cache
      reads/writes and script publication, retaining accepted IDs and useful live
      evidence. Submission orchestration and observation policy remain 10.5/10.6.
- [ ] **MVP10.4 Transport, readiness and software.** Classify process launch,
  SSH/session/helper/protocol/transfer and environment/Git/pip failures at adapters
  with operation context. Reproduce the stale-venv case with its attempted Python
  path and correction. Preserve probe/status unknowns and partial pull/install
  effects; do not infer auth causes without evidence or fall back to another host.
- [ ] **MVP10.5 Submission and recovery evidence.** Apply the module through
  preparation/staging/session/dispatch/scheduler-response/receipt-persistence
  failures and interruption. Preserve accepted IDs, partial results, original
  causes and receipt references; secondary cleanup/tracking errors cannot mask
  them. Rejection differs from unobserved acceptance; no blind retry.
- [ ] **MVP10.6 Inspection, logs and cached evidence.** Integrate scheduler query,
  path lookup, log reads, response decoding, cache and artifact failures. Distinguish
  absent/empty/not-cached/stale/failed/unknown and per-item vs operation failures;
  retain good evidence when another item fails. An SSH failure is not path absence
  or job failure. Bounds and timestamps remain visible.
- [ ] **MVP10.7 Cancellation, cleanup and sync.** Review destructive and partial
  operations, selection/config failures, changed files, denied writes and lost
  responses. Report each known/unknown effect; scancel acceptance is not observed
  cancellation. Keep existing preview/confirmation rules, no added retries or
  automatic deletion/rollback. Include discovery/context helper failures too.
- [ ] **MVP10.8 Python, CLI, ACP and client integration.** Make all public routes
  expose equivalent diagnostics/evidence, with expected failures rendered once
  and unexpected bugs debuggable. Exercise root and standalone CLIs, aliases and
  embedded clients; ACP must not flatten bugs/partial data into generic messages.
  Publish the agent contract, human diagnosis guide and reference-client pattern.
- [ ] **MVP10.9 Systematic failure gates and closure.** Close every audited row
  with a verified handler/observation policy and meaningful regression; no silent
  omissions. Cover phase-specific effects, interrupts, secondary failures,
  diagnostic serialization/bounds and old records. Run full offline/package and
  reference-client checks; record any intentionally changed API/data boundary.

Completion: every public operation has an explicit failure contract and strategic
translation owner; the dedicated module supplies consistent diagnostics without
duplicate catch-all handling. The stale-venv case must name the attempted path,
but that fix alone does not close MVP10. No environment auto-switch/repair,
tracking database, automatic recovery or resubmission is included.

## MVP11 Readable dependency-aware status

Design: [status explanations](REFACTORING_DOCS/design/MVP11_status_explanations.md).
Requested after MVP9.1; this section plans behavior, not an implemented command.

- [ ] **MVP11.1 Reason contract and classification.** Define normalized waiting
  categories beside unchanged scheduler state/raw reason; distinguish dependency,
  priority, resources, array limits, holds, policy limits and unknowns. Settle
  structured-field/cache compatibility and freshness rules; pure shared owner,
  no extra scheduler calls. Include impossible dependencies as attention cases.
- [ ] **MVP11.2 Dependency-aware projection.** Explain outstanding direct
  dependencies using exact bundle names, accepted IDs and complete array evidence.
  Qualify stale/unknown parents; preserve actual dependency conditions. Summarize
  mixed arrays without losing per-index reasons or status/log selection parity.
- [ ] **MVP11.3 Table and public adoption.** Put concise reasons in normal rows;
  retain full raw/exit evidence through supported details/JSON. Verify narrow/wide
  ANSI-safe output, no ordinary second-line clutter, and correct walltime labels.
  Align Python/CLI/ACP views and human/agent examples; run offline regressions.

Completion includes the reported graph: merge waits for shards; summary waits
for merge when set has freshly completed. Priority/resources are distinct reasons,
not invented new scheduler states or estimates of when a job will start.

## MVP12 Reusable scientific workflow services

Design: [reusable workflows](REFACTORING_DOCS/design/MVP12_reusable_workflows.md).
Source: [user-supplied Gaia proposal](REFACTORING_DOCS/proposal-generic-workflow-from-gaia.md),
reference commit `8eaffec`. Reimplement generic behavior around existing services;
keep science/project layout in clients. Each task is a separate usable increment.

- [ ] **MVP12.1 Resource summary.** Pure bundle rows/totals for arrays, concurrency,
  CPU/GPU/memory/walltime and dependencies; share existing parsers and label unknown
  or partial totals. Expose a public Python operation and readable CLI preview.
- [ ] **MVP12.2 Truly offline planning.** Validate/save logical bundles and context
  without SSH/transfer/Git/network discovery. Expose unchecked/unresolved remote
  paths; explicit readiness remains separate. Verify no-contact public routes.
- [ ] **MVP12.3 Review-before-effects workflow.** Show context, resources, machine
  and intended preparation before confirmation. Decline performs no remote/update/
  submit effects. Define non-interactive authorization and context publication;
  compose existing services without adding implicit pulls/prompts to submit_jobs.
- [ ] **MVP12.4 Named run records and rediscovery.** Link exact plans, context,
  attempts/receipts, updates and warnings through public create/load/list routes.
  Reuse current outcomes; settle small record/retention/release boundaries first.
  A new agent finds the run without reading private storage.
- [ ] **MVP12.5 Preparation evidence and dependency-change stop.** Extend the
  existing updater with declared-dependency comparison and planned/before/after
  revision evidence. Warn about known local dirty/unpushed state; stop clearly on
  dependency changes without changing machine-owned packages. Preserve effects
  of an already completed pull and define explicit acknowledgement/resume.
- [ ] **MVP12.6 Safe retry-plan builder.** Pure failed/never-submitted index and
  downstream selection, original array identity, compatible-output checks and
  explicit lineage/reasons. Unknown/live/uncertain work blocks unsafe retries.
  Preview/review first; any execution reuses existing submission/receipt services.
- [ ] **MVP12.7 Task-runtime contract proof.** Use Gaia-shaped and independent
  second-client fixtures to settle scheduler-free imports/packaging, shared MVP9
  option semantics and a plain Run/Stage-to-bundle bridge. No new framework is
  required for ordinary command authoring; CLI/science integrations stay optional.
- [ ] **MVP12.8 Optional runtime services.** Implement the agreed registry,
  per-index execution, atomic matching markers, bounded provenance and reducer
  completeness checks. Test changed code/options/partial outputs and clean-artifact
  import isolation. Generated CLI and bridge keep every job argument readable.
- [ ] **MVP12.9 Combined adoption gate.** Verify the reference workflow through
  supported APIs, CLI and documented agent context. Every preceding slice must
  already include exports, discoverable help/recipes, human examples, structured
  outcomes and failure checks; do not defer these to this final task. Run offline
  and packaged-resource checks. Real Gaia migration is a separately scoped task.

Overlap is owned elsewhere: argument contracts/compiler by MVP9, shared diagnostics
by MVP10, waiting explanations by MVP11; log inspection and plain isolated editable
builds already exist. Optional scientific-result fetching remains decision-gated
because the earlier user instruction limits retrieval to AutoSlurm logs/evidence.
No recursive result mirror or automatic retry/deployment is included.

## PLAN.1 Schedule the next two reliability MVPs

- [x] Trace the reported preflight failure and current argument design; schedule
  MVP9 then MVP10 with scoped tasks, evidence requirements and clear exclusions.
  Update design references and review documentation links. Planning only; no
  runtime/client edits, config changes, cluster contact or new test-pass claim.

## PLAN.2 Expand error handling into an API-wide modular milestone

- [x] Review public exports, CLI/ACP routes and representative error owners;
  seed the failure/translation map, mandate a separately maintained error module,
  replace the narrow three-slice MVP10 with a complete audit and staged rollout,
  and remove the obsolete one-to-two-day estimate. Planning only; runtime baseline
  and MVP9 ordering remain unchanged.

## PLAN.3 Schedule status explanations and reusable Gaia workflows

- [x] Preserve/read the supplied proposal, compare representative source with
  existing/planned owners, and scope MVP11/12 in independently deliverable tasks.
  Require public API exposure, CLI/agent discovery and human examples per slice;
  identify offline planning, runtime import and result-fetch scope boundaries.
  Review links/diff. Planning only; no status/workflow implementation or Gaia edit.

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
  MVP12.6 later adds an explicit reviewed retry plan; automatic recovery remains
  deferred and output compatibility must stay explicit.

## Later product layers

These remain desired outcomes with no near-term delivery estimate. Open a design
only when its user benefit justifies the next increment.

| Layer | Work deliberately deferred |
|---|---|
| L1 Richer tracking and recovery | Full versioned definition/run/attempt model, persistent offline index, automatic interrupted-submission reconciliation/resume, historical import/migration |
| L2 Scientific workflow conveniences | MVP12 now scopes reviewed retry plans, workflow helpers and an optional task runtime; automatic recovery and live reducer replacement remain deferred |
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
| I02 client integration; I03 readiness; I04 definitions; I05 preview | MVP1 shared roots/selection, small reference client; MVP2 validation/env | MVP9 command contract; MVP12 resource/offline/review/preparation services |
| I06 submission; I07 interruption | MVP2 known/partial/uncertain outcomes and receipts | L1 automated reconciliation and resume |
| I08 rediscovery; I09 refresh; I10 inspect; I11 diagnosis; I16 handoff | MVP3 shared task view, bounded evidence and minimal structured interface | MVP11 reasons; MVP12 named run grouping; L1 richer index |
| I12 results | Application-owned retrieval/validation; MVP8 retrieves execution logs only | Gaia fetch proposal is decision-gated; no scope expansion yet |
| I13 cancellation; I15 cleanup | Retain working commands in their release lane; protect unknown work | Consolidate when touching their shared state; broader retention policies later |
| I14 retry/downstream repair | Manual explicit recovery using recorded evidence | MVP12.6 reviewed retry planning; automatic recovery remains deferred |

## Decisions log

| Date | Decision | Reason |
|---|---|---|
| 2026-11-13 | MVP9 public authoring uses CommandContract, CommandOption and optional from_typer; saved jobs are explicitly revalidated | Implemented the requested narrow public boundary with complete named settings and no persisted schema/import lookup. Changed defaults preserve old explicit values; missing/removed/incompatible options require deliberate rebuild. This establishes current-contract compatibility, not historical code or remote identity |
| 2026-11-13 | Dependent jobs default to kill-on-invalid-dep=yes | User requested Slurm cancel jobs whose dependencies can never be satisfied; explicit per-job Slurm overrides remain authoritative, roots and already queued scripts are unchanged |
| 2026-11-13 | Schedule readable status reasons and reusable Gaia workflow services | User requested same-row pending explanations and generic Gaia behavior in supported APIs with everyday human/agent documentation. PLAN.3 scopes MVP11/12; exact APIs, data and runtime packaging remain proposed, existing retrieval/update boundaries retained |
| 2026-11-13 | Expand MVP10 to full API failure review, a dedicated error module and strategic integration across all public operations | User rejected a narrow message/updater fix; shared error ownership and complete failure contracts must be independently maintainable. Exact error API details remain proposed; implementation follows MVP9 |
| 2026-11-13 | Investigate a concrete low-friction pattern while preserving human-readable cluster execution | User prioritized readable settings/scripts and less agent integration glue. DOCS.3 records a proposed single-declaration builder/command pattern with experiment evidence; no architecture or argument-policy change is accepted yet |
| 2026-11-13 | Map all job/script interfaces before selecting an argument or execution refactor | User requested a general working principle spanning terminal, Python and saved JSON. Current routes are audited; recommendations remain proposals, with no change to accepted argument preferences |
| 2026-11-13 | Job arguments are explicit, named and readable; typed CLI commands per job kind, Typer preferred | Alexandre's lasting preference: flat scalar script_args, CSV lists, default-off booleans, shell-safe strings and local client validation; replace opaque config payloads during reviews |
| 2026-11-12 | Editable install by default after each successful software pull | User requires new command-line entry points to be installed; refresh the same checkout in the configured existing environment while retaining machine-owned dependencies and the single-copy policy |
| 2026-11-12 | Retrieval is limited to execution logs and scheduler evidence | User clarified scientific datasets/results belong to applications; MVP8 replaces the proposed generic result downloader |
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
| 2026-11-12 | Make config canonical; configure only software_root and shared results_root | User requested simpler configuration and merging project/results. Old saved runs retain recorded bases; conflicting old profiles need an explicit root choice; only configuration/path behavior is implemented in this slice |
| 2026-11-12 | Delegate remote connection details to SSH config; store only ssh_alias in current profiles/new transports | User always uses SSH config and wants to remove hostname/username/key duplication. Preserve historical transport interpretation while rejecting obsolete new CLI fields |
| 2026-11-12 | Implement source preparation before environment creation, preserving the existing job dictionary | Shared per-job software requests are normalized and checked for equality; explicit current-host preparation produces source evidence only. Runtime opt-in fails closed until installation/execution are implemented; no changes to GitHub settings |
| 2026-11-12 | Pull read-only remote software/environment inspection forward before installation | User requested a visible CLI and potential-problem report for important dependencies and installed application identity. Compare declared ranges against the selected remote interpreter; allow compatible stricter pins, expose unknown source identity and avoid full workstation freezes. Read-only rusty inspection is explicitly authorized; remote writes remain out of scope |
| 2026-11-12 | Restrict the software layer to one existing checkout per project, updated only by git pull | User explicitly requires no duplicate code because of cluster file limits. Supersedes source copies, cloned caches, installed releases, package installation and release records; keep updates explicit and job submission independent |

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
| 2026-11-12 | MVP7.0c Config and two-root path implementation | 405 offline tests pass in 3.22 s, 39 expected warnings, report `.development/test-runs/config-reviewed.xml`. Added 13 checks, including nine initial failures for new behavior; shared input/cwd/output roots, configured software evidence, no-network edits, explicit legacy merge, invalid roots and historical/new producing paths verified. Existing scientific fixtures use temporary merged data roots. Base config help, pre-existing main config retention and empty job/runtime directories/rollback verified at closure. No cluster operations/install/migration; no mvp7 completion tag. Task commit: `git log --grep '^MVP7.0c:'` |
| 2026-11-12 | MVP7.0d SSH aliases only | 427 offline tests passed in 3.23 s, 39 expected warnings; 22 new cases (14 initially failing, one initial history check passing, seven later CLI/session cases). Canonical alias config/editor/CLI and SSH/SCP/rsync/status/session evidence verified, historical transports retained. Report `.development/test-runs/ssh-alias-final.xml`. Local rusty profile switched from a mistaken hostname value to ssh_alias rusty, with original backup and all other settings preserved; SSH config untouched. No cluster/install/push operations. Task commit: `git log --grep '^MVP7.0d:'`; full MVP7 stays open |
| 2026-11-12 | MAINT.1 Remove repository workflow files | Removed only the CI/Codecov and book-deployment Actions files. Reverted extra local documentation/hosting changes; unintended remote settings changes were restored and verified: Actions enabled, Read the Docs webhook active, Pages legacy source gh-pages at /. Diff checks passed; application code unchanged. Task commit: `git log --grep '^MAINT.1:'` |
| 2026-11-12 | MVP7.1 Git source and manifest engine | 485 full offline tests passed in 4.86 s (38 expected warnings), up from 427 baseline. Report `.development/test-runs/software-sources-final.xml`. Verified fresh upstream/default-branch changes, exact commits/annotated tags, first cloning, separate source sets/storage, partial/tracking/interruption failures, evidence-collision protection, stale-cache refusal, unsafe/unmanaged/redirected caches, locking and preview/submit guards. Real Git fixture uses temporary local repositories only; existing scientific/CLI/ACP workflows pass. Human/agent recipe and schema updated. No cluster commands, package installation or GitHub settings changes. Task commit: `git log --grep '^MVP7.1:'`; full MVP7 remains open |
| 2026-11-12 | MVP7.1b Read-only software status and compatibility | 523 offline tests passed in 6.19 s (39 expected warnings); report `.development/test-runs/software-status-final.xml`. Added 38 checks for focused constraints, target markers, selected-interpreter identity, missing/unknown/mismatched metadata, clean/dirty/invalid Git paths, malformed SSH responses and CLI failure reporting. A temporary Git/venv fixture exercised the exact standalone SSH payload without installing AutoSlurm or scientific packages in that venv. Live read-only rusty checks succeeded: AutoSlurm dev 213de79 and Gaia main d21f04d were clean and used by editable installs; Gaia major requirements satisfied but expected local commit 0155e17 differed. Reports `.development/test-runs/rusty-software-status.json` and `rusty-gaia-software-status.json`. No cluster writes/install/fetch/jobs or base environment changes. Task commit: `git log --grep '^MVP7.1b:'` |
| 2026-11-12 | MVP7.2-plan Remote application update delivery | Reviewed source, status, SSH, execution and script-generation boundaries. Proposed four slices covering runtime policy, verified application installation, remote CLI/evidence and explicit job binding; reuse the cluster dependency base without updating it. Recorded proposed CLI examples and failure gates in the MVP7 design. Documentation/link checks only; no implementation, live SSH or remote changes. Task commit: `git log --grep '^MVP7.2-plan:'` |
| 2026-11-12 | MVP7.2a–d Usable application preparation and job selection | 596 offline tests passed in 16.13 s (39 expected collision warnings), report `.development/test-runs/software-prepare-final.xml`; 73 cases added over MVP7.1b. Real temporary Git/wheel/venv fixtures verified changing upstream commits, explicit pins, same-version old editable code versus new non-editable installations, separate helper/runtime interpreters, exact SSH stdin worker without installed AutoSlurm imports, dependency conflicts, old/new scripts and mocked submission snapshots. Additional checks cover durable IDs, lost responses/stale evidence, no replay, publication failures, constraints/markers/extras, altered code/base inventory and machine/request/runtime/path guards. Offline wheel build and isolated install/import/worker/help smoke passed; artifact SHA256 `0f8f0dad71f2a84200e47379b4069183070182e9c47601468b2d85c0ae8ff796`. Base Conda still imports main dev; clean rollback source remains `33bcbd3`. No cluster connection, fetch, install, job, profile mutation or baseline changes. Task commit: `git log --grep '^MVP7.2:'`; superseded by the single-copy requirement in MVP7.2e |
| 2026-11-12 | MVP7.2e Single-checkout Git update and removal of duplicate-copy engines | 525 offline tests passed in 5.53 s (39 expected collision warnings); report `.development/test-runs/software-update-final.xml`. Removed source/cache/release/wheel/installation/record engines and job release selectors; 32 new checks replace obsolete copy-engine tests. Real temporary Git fixtures verify repeated in-place pulls, the exact SSH stdin payload, preserved dirty/untracked files and rejected divergent history. Mock checks cover missing/detached/upstream/path failures, before/after commits, unknown/lost/malformed outcomes without retries and no new code/record files. Clean temporary-source wheel build and isolated install/API/help smoke passed; retired modules absent, SHA256 `e43ec1dcaa52adabe467f4f8c65a385f75250cfecdb3051bedfdd306114377b0`. Main base import and clean rollback `33bcbd3` verified. Existing user files/operation evidence retained; no actual cluster contact, pull, install, cleanup, profile mutation or migration. Task commit: `git log --grep '^MVP7.2e:'`; local milestone tag `mvp7` at closure, no remote promotion |
| 2026-11-12 | FIX.SSH.1 Submission connection ownership and macOS sockets | 542 offline tests passed in 5.64 s (39 expected collision warnings), report `.development/test-runs/ssh-session-final.xml`; 17 new cases. Both submit callers inherit configured sharing without Control overrides or explicit open/close; own-session short paths, failed/malformed config fallback, long TMPDIR, cleanup errors and local no-ops verified. User/agent SSH docs updated. No actual SSH, cluster changes or environment installation. Gaia main pushed through ba97a0b first, preserving dirty PDFs/data. Task commit: `git log --grep '^FIX.SSH.1:'`. Resume separately saved MVP8 log work. |
| 2026-11-12 | MVP8.1–MVP8.3 Robust execution logs | 562 offline tests passed in 5.58 s (38 expected warnings), report `.development/test-runs/execution-logs-final.xml`; 20 net added cases after FIX.SSH.1. Public inspect_logs, direct asl logs and ACP stream selection share status/reasons/exit codes and bounded local/SSH excerpts. Verified exact SSH stdin reader, array/custom/merged/separate logs, stream-before-limit selection, empty/missing/permission/special files, sparse 1 GiB log bounded read, growth/rotation, malformed/oversized replies, cache failures and cached no-source/no-network reads. Clean-source offline wheel install/API/reader/entry-point/help smoke passed, SHA256 `9b3e5c18e04f3964fdb8ff0c2eabe4e55e9682f449a23ebe099b0179d0c634d4`. Main base import/help and clean rollback 33bcbd3 verified. Human/agent guidance and interaction scope updated; no scientific result transfers, base installs, daily config/state mutation, cluster contact or deployment. Task commit: `git log --grep '^MVP8:'`; local mvp8 tag at closure. |
| 2026-11-12 | MVP7.2f Editable installation after software pull | 576 offline tests passed in 9.61 s (39 expected collision warnings), report `.development/test-runs/software-editable-final.xml`; 14 net new cases plus expanded real Git/venv fixture. Configured interpreter identity is checked before pulling; every successful pull runs editable pip installation without dependency/build-isolation/index/cache preparation. Same-commit entry-point repair and new CLI at unchanged package version work through local and exact fake SSH payloads, with one source checkout. Failures/timeouts/lost or malformed replies retain commit/installation evidence and never retry/reset; target redirection is ignored. Clean-source wheel/isolated target/API/help smoke passed, SHA256 `4994986c18e649411b7fc27e2f1d45c73942a1f8b957e7df7622a5f5ecedc782`. Main base import/help and clean rollback 33bcbd3 verified; user files/evidence preserved. No actual SSH/cluster installs, base environment changes, daily state/config mutations or remote deployment. Task commit: `git log --grep '^MVP7.2f:'`; push completed dev commit. |
| 2026-11-13 | DOCS.1 Lasting client argument preference | Updated AGENTS.md, operating/client/bundle recipes and accepted agent-documentation design. Read current argument renderer to confirm list/boolean/string limits; reviewed Markdown diff, JSON example and relative links/anchors. Documentation only; no application tests rerun, code/runtime enforcement, existing bundle rewrites, client changes or cluster operations. Last code baseline stays 576 passing offline tests from MVP7.2f. Task commit: `git log --grep '^DOCS.1:'`; push completed dev commit. |
| 2026-11-13 | DOCS.2 Job script interaction map | Read current schedule/save/preparation/path/render/dispatch/ACP/inspection code at dev 297de16. Added authoring-route and lifecycle/evidence maps, a Mermaid overview, current brittle differences and explicitly proposed alternatives/decisions to REFACTORING_DOCS/interaction-map.md. Checked relative file links, anchors, diagram text and documentation diff. No implementation, new argument fields, callable launcher, accepted-preference changes, runtime data edits, cluster action or application tests. Last code baseline stays 576 passing offline tests. Task commit: `git log --grep '^DOCS.2:'`; push completed dev commit. |
| 2026-11-13 | DOCS.3 Readable command/job pattern investigation | Reviewed current AutoSlurm pipeline, argparse example and Gaia's typed registry/CLI/builder; inspected primary Typer/Click/Python docs. Isolated probe/report `.development/test-runs/job-interface-investigation.py` / `.json` on Typer 0.27.3 verifies scalar render/parser round-trip, typed/default/range/unknown-option handling, current space/list/default-on-bool limits, strict native-type binding/coercion gaps and parameter callbacks during parsing. Click metadata export assumption failed and is recorded as an adapter limitation, not a supported API. No scientific callback executed. Added concrete hypothetical builder/JSON/preview pattern, ownership/validation boundaries and candidate slices; links/examples reviewed. No package install, production code/API, preference change, cluster contact or full-suite rerun. Last baseline remains 576 passing offline tests. Task commit: `git log --grep '^DOCS.3:'`; push completed dev commit. |
| 2026-11-13 | FIX.CONFIG.1 Optional Slurm account and clearable config | 593 full offline tests passed in 10.57 s (41 expected collision warnings), report `.development/test-runs/optional-account.xml`; focused config tests 48 passed. Clean wheel config set/clear and account-free rendering smoke passed, SHA256 `491f184730042a666b49b448edb66be6a691296821a74de557da8a18ad7d3046`. Shared normalization removes unset account keys, selection no longer requires one, direct flags save locally, optional editor fields accept `-` to clear. Explicit accounts and historical records remain intact. Base editable import verified; backed up then cleared local rusty account and verified other settings unchanged. No cluster contact, base install or rollback edits. Updated human/agent/config design and installation register. Task commit: `git log --grep '^FIX.CONFIG.1:'`; push completed dev commit. |
| 2026-11-13 | FIX.LOGS.1 Status-compatible log navigation | 623 full offline tests passed in 10.38 s (40 expected collision warnings), report `.development/test-runs/log-navigation.xml`. Thirty new checks verify bundle/job/expanded-array identity, sparse task indices, filters before bounds, conflicting selectors, batched multi-run queries, cached no-contact navigation and shared inspect behavior. Clean wheel indexed/cached navigation smoke passed; SHA256 `af7088345b15a3205eb6d9e723f39a0ca960e5aadda11862f8453c7e97693e43`. Human/agent examples, design and installation register updated. No cluster contact, daily state edits, base installation or rollback change. Task commit: `git log --grep '^FIX.LOGS.1:'`; push completed dev commit. |
| 2026-11-13 | PLAN.1 Scope command arguments and actionable-error MVPs | Read DOCS.3, current updater/probe/CLI and missing-Python regressions. Confirmed broad preflight catch erases missing-executable detail and attempted Python is assigned only after probe success. Scheduled MVP9.1–3 then MVP10.1–3; wrote the bounded delivery/error contracts, failure matrix and client ownership limits. Reviewed documentation links/diff. No runtime/config/client change or cluster contact; full-suite baseline remains 623 passing tests from FIX.LOGS.1, not rerun for this planning task. Task commit: `git log --grep '^PLAN.1:'`; push completed dev commit. |
| 2026-11-13 | PLAN.2 API-wide modular error-handling scope | User explicitly broadened MVP10. Reviewed exported Python APIs, CLI actions/aliases, ACP and representative config/persistence/path/transport/software/submission/inspection/lifecycle errors. Documented dedicated error-module ownership, strategic translation boundaries, failure families and full-API coverage gates; expanded MVP10 to nine slices. Initial map is a seed, not a completed per-callable audit. Documentation links/diff checked; no runtime/client/config edits, cluster contact or test rerun. Baseline stays 623 passing offline tests. Task commit: `git log --grep '^PLAN.2:'`; push completed dev commit. |
| 2026-11-13 | FIX.SOFTWARE.1 Plain isolated editable builds and setup before venv activation | 634 full offline tests passed in 9.16 s (41 expected collision warnings), report `.development/test-runs/plain-editable.xml`; 11 added cases plus updated command/script expectations. Real local/fake-SSH Git/venv fixture uses a no-download standard-library backend and a conflicting runtime package to prove build isolation, same/new-commit CLI refresh, single checkout and unchanged non-project distributions. Pip failures expose last 20 lines/about 4 KiB with URL-userinfo lines omitted; shell tests verify setup precedes activation and failure stops rooted jobs. Config editor preserves setup; single-setting behavior retained. Clean wheel smoke and guidance checks passed. No actual cluster contact, network build, daily config/venv install or rollback edit. Broad MVP10 remains planned. Task commit: `git log --grep '^FIX.SOFTWARE.1:'`; push completed dev commit. |
| 2026-11-13 | MVP9.1 Single-declaration command proof | 674 full offline tests passed in 10.53 s (42 expected collision warnings), report `.development/test-runs/command-proof.xml`; 40 new cases. Experimental command-contract/optional Typer 0.27 adapter derives scalar options/defaults/ranges, rejects unsupported side-effectful/dynamic semantics before discovery, and builds current readable jobs. Reference CLI/parser/native-value round-trips, invalid options without writes, preview/mock submission identity and actual local science output passed. No contract serialized or top-level public API added. Clean wheel optional-dependency/contract/JSON smoke passed, SHA256 `17e2ab6c8a97b16a9eea104285a80082280f680e490b84750babb13171db9221`. Docs and links reviewed; no cluster, base install, daily state, external application or rollback changes. User's status/workflow planning requests remain next. Task commit: `git log --grep '^MVP9.1:'`; push completed dev commit. |
| 2026-11-13 | PLAN.3 Status explanations and reusable Gaia workflow roadmap | Preserved the supplied proposal unchanged; read representative Gaia bundle/command/registry/run code at `8eaffec` without executing it. Scheduled MVP11 reason/projection/table slices and MVP12 resource/offline/review/run/preparation/retry/optional-runtime services with per-slice public API, CLI/agent discovery, evidence and human examples. Mapped MVP9/10/11 and completed-update overlaps; retained separate fetch/runtime/data decisions and low-level submit boundaries. Reviewed diff, relative links and task references; documentation-only, no test rerun. Existing baseline remains 674 passing offline tests from MVP9.1. No cluster, config/state, external client, installation or rollback changes. Task commit: `git log --grep '^PLAN.3:'`; push completed dev commit. |
| 2026-11-13 | MVP9.2 Shared literal argument compiler | 723 full offline tests passed in 10.01 s (42 expected collision warnings), report `.development/test-runs/argument-compiler.xml`; 105 focused checks passed. One pure owner compiles resolved values into literal argv groups and shell-quotes them; retired the old renderer formatter. Actual Bash capture and Typer parsing preserve spaces/quotes/substitutions as text; reference preview matches dispatched script and actual scientific output, while invalid raw values stop before staging. Plain output and raw list/positional/omission semantics remain, typed authoring stays scalar/CSV/default-off. No saved shape change; new rendering does not expand expressions or rewrite old artifacts. Clean wheel import/path/actual-shell smoke passed without Typer, SHA256 `d8d846ed99b780dde236a8beb5c4e6e69d422aa1f7598991dd59c460177d9f9a`. Agent/human guidance and links updated. No cluster, base install, daily config/state, external scientific application or rollback edits. Task commit: `git log --grep '^MVP9.2:'`; push completed dev commit. |
| 2026-11-13 | FIX.DEPENDENCY.1 Default cancellation for impossible dependencies | 741 full offline tests passed in 9.69 s (42 expected collision warnings), report `.development/test-runs/invalid-dependency.xml`; 18 new renderer cases plus preview/dispatch assertions and updated dependent-script fixtures. Shared renderer adds one default yes directive only for nonempty dependencies, preserves underscore/hyphen explicit overrides, handles arrays and leaves definitions unchanged in local/remote contexts. Full-suite fixture mismatches were updated for the intended directive. Clean wheel/default/nonmutation/actual-shell smoke passed, SHA256 `62579a91072cc8989df90da81c178d4b83eca46242490d067c046440f9011e8a`. Human/agent docs and MVP4 design amended; links/diff checked. No cluster, configuration, daily state, base installation or historical/queued script change. Task commit: `git log --grep '^FIX.DEPENDENCY.1:'`; push completed dev commit. |
| 2026-11-13 | MVP9.3 Public authoring, saved validation and installed recipe | 761 full offline tests passed in 11.08 s (43 expected collision warnings), report `.development/test-runs/typed-authoring.xml`; 83 focused checks passed, 20 added cases. Public contracts/optional Typer adapter, strict no-default-injection saved-job checks, detached values and dependency authoring verified. Reference plan/validate/preview CLI runs four original-index tasks plus reducer through existing preview/dispatch/receipts/cached inspection and actual local science under mocked Slurm. Packaged recipe is discoverable through CLI/ACP without a checkout; complete historical guidance packaging remains L3. Clean AutoSlurm/client wheels verify optional Typer absence, public imports, installed recipe/action metadata, client CLI and scientific entry point; SHA256 `dbcca8ede6c0135729aead31aa83b1da75a24489542bc646dffdaec9ba167ccb`. Human/agent guides and links/diff checked. MVP9 complete locally, local tag `mvp9` at closure; no schema migration, cluster, base install, daily state/config, external client or rollback change. Task commit: `git log --grep '^MVP9.3:'`; push completed dev commit. |
| 2026-11-13 | MVP10.1 Complete public interface/failure inventory | Audited revision `6104372`: 233 routes (Python exports/methods, root/alias/subaction/standalone/helper CLI and eight ACP actions), 112 owners, 24 failure contracts and all 18 broad catches individually reviewed. Register records inputs/current outcomes/effects plus translation owner, desired diagnosis, next action, regression sources and pending adoption task. E01–E18 cover swallowed causes, false missing, publication/partial/unknown effects and presentation gaps; preserve evidence-saving catches. Read-only AST checker passed and rejected four drift controls (missing export, wrong alias, missing effects, unreviewed catch). Full offline suite: 761 passed, 43 expected collision warnings, 10.53 s; `.development/test-runs/error-inventory.xml`. Documentation links/diff reviewed. No package runtime, dependencies, daily state/config, external client, cluster or rollback changes; no artifact rebuild needed for an audit-only task. MVP10.2 is next; proposed diagnostic APIs are not accepted/implemented by this audit. Task commit: `git log --grep '^MVP10.1:'`; push completed dev commit. |
| 2026-11-13 | MVP10.2 Shared diagnostic foundation | Stdlib-only errors.py owns 17 codes/categories/default wording, immutable context/effects, named fact constructors, safe bounded serialization and primary/secondary facts; apps/error_output.py is opt-in text/JSON/exit/debug presentation. SubmissionError/SoftwareUpdateError retain positional messages, payload identity, RuntimeError compatibility and native causes with optional diagnostic=. 36 focused tests and 797 full offline tests passed (43 expected collision warnings), 10.62 s; `.development/test-runs/error-core.xml`. Clean-source offline wheel/temporary-target smoke verifies APIs, legacy payloads, redacted JSON and installed recipe via CLI/ACP without Typer; SHA256 `f6734a18963e0f64b64cd4c0365bcd0ba1572e96bae795e80402f939e53ae2cc`. Coverage checker: 248 routes/127 owners/18 retained broad catches. Human/agent docs and links reviewed. No cluster, base install, daily config/state, persisted-format or rollback change. Operation adoption, stale-venv fix and universal CLI/ACP parity remain pending; MVP10.3 is next. Task commit: `git log --grep '^MVP10.2:'`; push completed dev commit. |
| 2026-11-13 | FIX.CONFIG.2 Interactive environment setup | Added optional env_command prompt immediately after venv_path for profile creation/editing; Enter keeps, a command replaces, and `-` removes the key. Shared persistence/activation/validation are reused. Six new regressions reproduced the missing prompt, then verified public config/configuration interactive flows, exact profile preservation, quoted venv paths, mocked SSH/Python/helper-root validation and rendered setup-before-activation. Existing prompt fixtures updated. 84 focused tests and 803 full offline tests passed in 10.98 s (43 expected collision warnings), report `.development/test-runs/config-env-command.xml`. Clean-source offline wheel/temporary-target interactive/alias/clear/render smoke passed, SHA256 `61c2233cdd76b0107bc148111060e6349a7f3adaf7d64493b8e8206509d58a24`. Human/agent guidance, design, installation register and API audit updated; relative links/diff checked. No actual SSH, daily config/environment, base install or rollback edits. MVP10.3 remains unstarted. Task commit: `git log --grep '^FIX.CONFIG.2:'`; push completed dev commit. |
| 2026-11-13 | MVP10.3a Configuration diagnostics | Split MVP10.3 before implementation. Shared errors.py now owns ConfigurationError/configuration_failure; known reads/JSON/UTF-8/profile/selection/settings failures carry actual source path, machine/field, original cause, safe bounded detail, correction and config_write=not_started. Config root/alias/standalone routes use stderr/exit 1 and --debug; unexpected bugs stay visible. Existing invalid/unreadable/corrupt files, dangling links and entries appearing during failed reads never enter reset/first-use setup. Explicit root/legacy lookup and raw view shape preserved. Dev exception-family change documented; no saved-schema change. 851 full offline tests passed in 9.87 s (43 expected collision warnings), `.development/test-runs/configuration-diagnostics.xml`. Clean-source offline wheel/temporary-target API/config routes/debug/retained-file/installed-recipe smoke passed; SHA256 `0c3529f9e3af49e3b0674a611af7878a26c4568d7b3476419e75eb363b43e3de`. AST register: 251 routes/129 owners/18 broad catches; human/agent docs, design and installation register updated. No actual cluster commands, base dependency install, daily config/state, external client or rollback edit; user documents/evidence preserved. MVP10.3b is next; publication diagnostics stay 3c and stale-venv stays 10.4. Task commit: `git log --grep '^MVP10.3a:'`; push completed dev commit. |
| 2026-11-14 | MVP10.3b.1 Authoring diagnostics | Split b into authoring, snapshot selection and pure path/render tasks before implementation. Public InvalidRequestError reuses the shared core for known command/option/adapter/literal/graph/software-intent/input/preparation failures, retaining field/option/job/project/stage, exact bundle/machine and native causes. Save/schedule input guards replace old TypeError/KeyError; blank/nonstring commands stop before publication. dependency_graph now rejects cycles itself, retaining CycleError and named cycle. Explicit settings, raw argument styles and saved formats remain unchanged; no callbacks or blanket bug catches. Schedule root/standalone routes use shared stderr/exit 1 and --autoslurm-debug, preserving application --debug. Bounded identity enrichment no longer masks a repeated long identity. 54 new contract/evidence cases; 905 full offline tests passed in 11.45 s (43 expected collision warnings), `.development/test-runs/authoring-diagnostics.xml`. Clean-source offline wheel/temporary-target API/graph/retained-record/root/standalone/debug/optional-Typer/installed-recipe smoke passed; SHA256 `5d8685e83105132dc763100306945e286444d796a020738296adba27e5fa0187`. AST register: 253 routes/130 owners/18 broad catches. Human/agent docs, design and installation register updated. No actual cluster commands, daily config/state, dependency installation, external client or rollback edit; user documents/evidence excluded. Snapshot selection b.2 is next; b.3 paths/rendering, 3c publication and 10.4 stale-venv remain open. Task commit: `git log --grep '^MVP10.3b.1:'`; push completed dev commit. |

| 2026-11-14 | MVP10.3b.2 Snapshot/filter selection diagnostics | Shared snapshot analysis replaces duplicated graph checks and failure-to-empty listing. Public SelectionError/selection_failure retain exact selectors/paths, safe causes and absent/access/invalid distinctions; missing selections explicitly replace FileNotFoundError. Discovery returns per-entry state/diagnostic, unknown jobs/counts=None, healthy neighbours and observed graph-invalid counts. No directory creation; regular-file/nonblocking checks reject special files. Newest failures remain visible and block older-draft fallback; stable filename tie-breaks preserve equal-date index ordering. Config owns active/all validation and defaults only after absence. Internal save/append fallback checks resource_missing only; automatic stale/unsubmitted cleanup excludes unknown counts. Filter/submit/status/inspect/logs text/JSON/debug routes and ACP discovery retain adopted facts; submit validates strictly before connecting. Two masking broad catches removed. 60 new regressions; 965 full offline tests passed in 10.00 s (43 expected collision warnings), `.development/test-runs/selection-diagnostics.xml`. Clean-source offline wheel/temporary-target discovery/selection/retained-record/CLI/JSON/debug/ACP/installed-recipe smoke passed; SHA256 `b0b224f02f50fa2154b2f50349297e0263ff691e1e3d98ac73259d46cf2202cc`. AST register: 256 routes/132 owners/16 broad catches; human/agent docs, design and installation register updated. No cluster, dependency installation, daily config/state, persisted-format, external client or rollback changes; user documents/evidence excluded. Path/render b.3 is next; generic publication/read, readiness/stale-venv and universal observation/CLI/ACP adoption remain pending. Task commit: `git log --grep '^MVP10.3b.2:'`; push completed dev commit. |
| 2026-11-14 | MVP10.3b.3 Path/render preparation diagnostics | ExecutionContext reuses shared InvalidRequestError for known path/base/role/cwd/log guards, retaining job/machine/field/option/logical/attempted resolved identity; preview/submit add exact bundle context. Shared render guards diagnose malformed directives/exports without echoing values. Bash syntax rejection retains safe line/named-job evidence; other checker failures remain process errors. Saved producing-context lookup distinguishes missing/ambiguous/invalid evidence via SelectionError and preserves historical roots/transport without profile discovery. Direct scripts render before destination open, preserving existing/absent files on render failures; atomic publication stays 3c. Submit honors preparation --debug. 61 new regressions; 1026 full offline tests passed in 10.20 s (43 expected collision warnings), `.development/test-runs/preparation-diagnostics.xml`. Clean-source offline wheel/temporary-target path/render/producing-context/retained-script/CLI/debug/ACP/installed-recipe smoke passed; SHA256 `98345cd7e42c890ca3f32979addc82d3a02d6a41b3d33a7cb69f639106c3e9a6`. AST register: 256 routes/132 owners/16 broad catches; human/agent docs, design and installation register updated. No cluster, dependency installation, daily config/state, schema/history rewrite, external client or rollback edit; user documents/evidence excluded. MVP10.3b complete; 3c record read/publication is next, 10.4 readiness/stale-venv and broader observation/CLI/ACP remain pending. Task commit: `git log --grep '^MVP10.3b.3:'`; push completed dev commit. |
| 2026-11-14 | MVP10.3c.1 Shared JSON publication diagnostics | Split c into shared writer, bundle/config and receipt/cache/script boundaries before implementation. RecordWriteError/RecordCollisionError and pure fact constructor reuse the core catalogue; native causes and safe kind/errno/path/stage retained. Serialization explicitly replaces raw TypeError/ValueError at this dev boundary, while OSError and exclusive FileExistsError compatibility remain. Publication not_started/unknown/succeeded is separate from directory durability; post-publication failures preserve complete records, failed syscalls never imply rollback. Explicit temp/directory close and all cleanup retain primary plus bounded secondary/native evidence, including bugs/interrupts; two resource/evidence-only broad catches reviewed. Only clean exclusive collisions advance snapshot timestamps. 32 new cases and updated legacy failure assertions; 1058 full offline tests passed in 10.04 s (43 expected collision warnings), `.development/test-runs/record-publication-diagnostics.xml`. Clean-source offline wheel/temporary-target API/publication/durability/cleanup/retained-record/JSON/debug/ACP/installed-recipe smoke passed; SHA256 `fa3340a99969341c1498f11d521fc875db47d5a6f66d250a7981024f0153168b`. AST register: 260 routes/135 owners/18 reviewed broad catches; human/agent docs, design and installation register updated. No cluster, dependency installation, daily config/state, persisted-format, external client or rollback edit; user documents/evidence excluded. c.2 bundle/config boundaries next, c.3 receipt/cache/script and broader transport/submission/observation/CLI/ACP remain open. Task commit: `git log --grep '^MVP10.3c.1:'`; push completed dev commit. |

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
