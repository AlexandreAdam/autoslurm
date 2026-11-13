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

- **Alexandre's lasting client preference (2026-11-13): job arguments are
  explicit, named and readable in the bundle.** Apply this when building,
  reviewing or helping software that uses AutoSlurm:
  - Give each job its settings as individual named `script_args`, one key per
    setting. Saved JSON and rendered commands must make the invocation readable.
    Never hide job configuration in base64, JSON blobs, or a single config-file
    argument. Point out existing encoded configuration as something to replace.
  - Client entry points are CLIs with typed, named options; **Typer is preferred**.
    Expose one command per kind of job (`tool TASK --option-a 1 --option-b x`);
    put the fixed command in `script` and its options in `script_args`.
  - Argument values are `int`, `float`, `str` or `bool`. Encode a list as one
    comma-separated string, not a Python/JSON list: the renderer emits lists as
    `--flag a b`, which does not match the intended Typer option interface.
  - Boolean CLI options default to off: `True` renders as `--flag`, while `False`
    is omitted. Keep effective settings visible in the bundle, including false
    values; do not rely on omission to turn off a default-on option.
  - String values are single shell-safe words. Ordinary non-path values are
    unquoted by the current renderer; reject unsafe values locally.
  - Validate every job's option names, types and values against its command's
    signature **before saving a bundle**, and validate again before submission
    if the command/definition changed. This is a client requirement, not a claim
    that AutoSlurm already implements signature validation. See the
    [client argument contract](agent/01_client_workflow.md#explicit-named-job-arguments)
    and [bundle-writing recipe](agent/10_task_schedule.md).
- Current refactor scope is local only: mock Slurm and transport commands. No
  cluster discovery, SSH, live jobs or remote installs. See WORKFLOW.md for the
  dated scope and installation register for the editable base Conda install.
  The user's 2026-11-12 read-only software-status exception permits inspecting
  Git and installed distribution metadata on `rusty`; see WORKFLOW.md. It does
  not authorize remote preparation, writes or job submission.
- The user activated the main checkout for daily development on 2026-11-12.
  Write application code in `/Users/aadam/Projects/autoslurm`, branch `dev`.
  Base Conda's editable install imports this checkout. Use `.development/python`
  for tests; it imports the same source with separate test state/dependencies.
  `.development/checkout` is the retained MVP4 development snapshot, not the
  active editing location. `.development/stable` is the pinned baseline rollback
  source; never edit or advance it during ordinary work.
- Work on one planned task at a time. Split oversized tasks first.
- A request to plan or review does not start implementation of later tasks.
- Update the checkbox, Done log, Status, and affected design document alongside
  the completed code and tests. Use the task ID as the commit-message prefix.
- Follow PLAN.md for commits and milestone closure. Do not include unrelated
  changes already in the working tree.
- Push completed `dev` commits to `origin/dev` as part of each task, as requested
  on 2026-11-12. Use ordinary fast-forward pushes and report failures; cluster
  operations remain outside the authorized scope.
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
- **Single-copy software policy (2026-11-12):** the software layer runs
  `git pull --ff-only` in one existing checkout under `software_root`, then refreshes
  its editable installation with the configured venv_path/bin/python, even if HEAD
  is unchanged (user amendment MVP7.2f). Use --no-deps and normal pip build
  isolation: FIX.SOFTWARE.1 allows temporary build environments and downloaded
  build requirements on the login host. Scientific dependencies in the selected
  venv stay operator-owned; its build backend need not be installed there.
  Verify interpreter prefix first.
  Never create clones, Git mirrors, worktrees, release copies, additional
  persistent environments or preparation/release records. `update_software` / `asl software
  update` are explicit operations separate from submission; compute jobs never
  update code. The operator coordinates update timing for jobs using the shared
  checkout. Do not restore the superseded source/release preparation engine.
- With both profile settings present, env_command runs before activation of
  venv_path. Use it for module loads; updates still use venv_path/bin/python.
- No package installation, checkout changes, or Git/network preparation inside
  compute jobs. Automatic deployment is outside the initial refactor.
- Client application paths use the shared `results_root` base for inputs, cwd
  and outputs; `software_root` locates managed code/environments. `config` is the
  canonical module/command; `configuration` is a compatibility alias. Conflicting
  old project/results profiles need an explicit root choice, while saved runs
  retain their original path evidence. AutoSlurm
  owns machine-root discovery and one resolution policy for preview, execution
  and artifact retrieval; clients do not embed absolute machine paths or branch
  on hostname. Record logical and resolved paths per attempt. Each application
  run/bundle uses one selected machine; multi-machine routing is outside scope.
- Remote profiles use only `ssh_alias`, referencing operator-owned SSH config.
  Do not manage HostName, User, IdentityFile or keys in AutoSlurm profiles. New
  run transports store the alias alone; historical recorded transports remain
  readable. Never silently fall back to local execution or another profile.
- `slurm_account` is optional. An unset profile account emits no account
  directive; do not invent one in clients. `asl config --clear-slurm-account`
  removes it locally. Explicit job `slurm.account` values remain authoritative
  Slurm options and must also be omitted when the cluster needs no account.
- Tests use temporary storage and fake external commands. Real cluster tests
  are separate and must not be triggered by the default test suite.
- Retrieval covers AutoSlurm execution evidence only: recorded stdout/stderr,
  Slurm output and status/reason/exit codes. Use `inspect_logs` / `asl logs` with
  exact run selectors and bounded excerpts; cached means no scheduler/source-log
  access locally or remotely. Scientific results/datasets remain application-owned.
- Update human and agent documentation when public behavior changes.
- Treat client integration guidance and durable agent handoff as interface
  requirements, not late documentation polish. Map each service to an interaction
  and include its recipe, outcome/evidence contract, and behavior checks.
- Human docs explain purpose, the system map, examples, agent collaboration and
  failure interpretation. Agents use supported programmatic contracts; private
  backend modules and storage files remain implementation details.
- [The current client recipe](agent/01_client_workflow.md) and
  [reference client](examples/reference_client/README.md) are the verified MVP8
  integration boundary. Keep path bases, preflight, incremental receipts,
  uncertainty/inspection, stale evidence and bounded log limits accurate.
- [Software updates](agent/13_software_preparation.md) documents explicit
  single-checkout pulls/editable refresh and the retained read-only status surface. Source/release
  preparation has been removed. Do not infer authorization to update an actual
  cluster from the command's availability during local-only development.
  `asl software status` provides read-only Git and selected-environment metadata
  comparisons against local declared major dependencies/application identity. It
  reports mismatch/unknown; it does not establish runtime readiness or update code.
- Keep development installation working and use a narrow artifact smoke check
  before promotion. Complete packaged agent resources, public index release,
  broad compatibility matrices and polished documentation are later layers.
- Daily local commands follow `dev` in the main checkout, as explicitly requested.
  Keep test configuration/tracking/output separate through the test wrapper and
  temporary fixtures. Remote installations remain unchanged and must be mocked.
  Preserve pinned rollback source and historical evidence. The user's single-copy
  policy above supersedes the earlier isolated application-release design.
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
