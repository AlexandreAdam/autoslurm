# AutoSlurm agent guidance

AutoSlurm runs scientific job bundles on Slurm, locally or through SSH. Agents
operate from the workstation; compute nodes use already-prepared environments.

## Read first

- [PLAN.md](PLAN.md) is the task and progress source of truth. Read **Status**
  and **How we work** before starting implementation.
- [WORKFLOW.md](WORKFLOW.md) is the working agreement: task loop, lane isolation,
  test gates, agent handoff and explicit promotion/rollback.
- [The installation register](REFACTORING_DOCS/installation-register.md) records
  actual code/environment/helper/state locations. Unverified entries are not
  proof of isolation; do not assume this checkout is development-only.
- Read the current milestone's document in
  [REFACTORING_DOCS/design](REFACTORING_DOCS/design/README.md). Technical
  decisions start as proposed; do not label them accepted without user agreement.
- Use [the interaction map](REFACTORING_DOCS/interaction-map.md),
  [agent documentation design](REFACTORING_DOCS/agent-documentation-design.md),
  and [human documentation and distribution requirements](REFACTORING_DOCS/documentation-and-distribution-design.md)
  as coverage/design references. Review the subset needed by the current MVP;
  full-product design and documentation are not prerequisites for early fixes.
- [README.md](README.md) describes the public workflow. The
  [legacy maps](REFACTORING_DOCS/legacy_maps/README.md) describe existing code;
  they do not define the new architecture.

## Working rules

- Current refactor scope is local only: mock Slurm and transport commands. No
  cluster discovery, SSH, live jobs or remote installs. See WORKFLOW.md for the
  dated scope and installation register for the editable base Conda install.
- Write application code only in the development worktree listed in the register
  (`.development/checkout` under the original repository). The original checkout
  is the pinned stable source used by base Conda. Use development Python/CLI
  wrappers for tests and operations; do not advance or edit stable source.
- Work on one planned task at a time. Split oversized tasks first.
- A request to plan or review does not start implementation of later tasks.
- Update the checkbox, Done log, Status, and affected design document alongside
  the completed code and tests. Use the task ID as the commit-message prefix.
- Follow PLAN.md for commits and milestone closure. Do not include unrelated
  changes already in the working tree.
- Follow WORKFLOW.md for the execution procedure. Initial planning/rules files
  may remain uncommitted until the stable baseline is identified. A commit,
  push or tag never implicitly promotes code to daily use.
- Keep moves separate from rewrites. Reuse working code and representations;
  extract one shared owner per concern rather than building a parallel engine.
  Follow [legacy-policy.md](REFACTORING_DOCS/legacy-policy.md) for the pinned
  stable reference and retirement of replaced active paths. No blanket backwards
  compatibility or complete architecture rewrite is required for an MVP.
- Use descriptive whole-word module/class names and explicit data contracts.
  Keep external commands behind adapters and presentation outside the core.
- Persist plain data; existing JSON shapes may remain for early MVPs. New record
  versions or breaking formats need explicit release boundaries, data retention
  and an agreed import/migration policy, not a migration framework in advance.
- Distinguish absent, stale, failed, and unknown observations. Never blindly
  retry a submission whose scheduler outcome may already have taken effect.
- No package installation, checkout changes, or Git/network preparation inside
  compute jobs. Automatic deployment is outside the initial refactor.
- Client application paths are relative to explicitly declared bases. AutoSlurm
  owns machine-root discovery and one resolution policy for preview, execution
  and artifact retrieval; clients do not embed absolute machine paths or branch
  on hostname. Record logical and resolved paths per attempt. Each application
  run/bundle uses one selected machine; multi-machine routing is outside scope.
- Tests use temporary storage and fake external commands. Real cluster tests
  are separate and must not be triggered by the default test suite.
- Update human and agent documentation when public behavior changes.
- Treat client integration guidance and durable agent handoff as interface
  requirements, not late documentation polish. Map each service to an interaction
  and include its recipe, outcome/evidence contract, and behavior checks.
- Human docs explain purpose, the system map, examples, agent collaboration and
  failure interpretation. Agents use supported programmatic contracts; private
  backend modules and storage files remain implementation details.
- [The current client recipe](agent/01_client_workflow.md) and
  [reference client](examples/reference_client/README.md) are the verified MVP1
  integration boundary. Keep their path bases, preflight, saved evidence and
  known submission/inspection limits accurate.
- Keep development installation working and use a narrow artifact smoke check
  before promotion. Complete packaged agent resources, public index release,
  broad compatibility matrices and polished documentation are later layers.
- Develop with isolated local/remote code, helper, configuration, tracking and
  test output locations. Daily jobs stay managed by their pinned stable lane.
  Promotion changes new-run routing explicitly; no shared mutable records and no
  in-place updates to environments referenced by queued/running jobs.
- Until the actual installations and isolation are verified, perform only
  documentation and read-only discovery. Do not install dependencies into an
  unidentified environment or run commands/tests with unreviewed side effects.

## Commands

- Install development dependencies: `python -m pip install -e '.[test]'`.
- Fast tests: `python -m pytest -q tests/unit`.
- Full offline tests: `python -m pytest -q tests` after MVP0 verifies isolation.
- Documentation edits: review the diff and relative links.

Baseline results and exceptions are recorded in the MVP0 design; do not claim tests
have passed until they have actually run in the stated environment.
