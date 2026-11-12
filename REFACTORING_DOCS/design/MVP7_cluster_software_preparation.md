# MVP7 Bundle-driven cluster software preparation

## Status

In progress, 2026-11-12. The user requested Git-based preparation of several projects
and verification that the bundle's required versions are installed in its Python
environment. Configuration slices MVP7.0c/MVP7.0d and MVP7.1 source preparation
and MVP7.1b read-only status are implemented. Environment creation, runtime
readiness and execution wiring remain planned. Default tests remain local/mocked;
the Git engine is verified with fake remotes and temporary local repositories.
The user authorized read-only project/environment status on rusty, verified below.
No remote installation, source update or live Slurm operation has been performed.

## Problem and concepts

Agents currently depend on manually updating cluster checkouts/environments.
A version string or Git tag in JSON records intent but cannot establish that
installed code matches it. Pulling into a shared home checkout would change code
for queued/running jobs. Compute nodes have no internet; all preparation must
finish on a login/preparation host before submitting any compute.

Keep four concepts distinct:

1. **Requested software:** repositories, requested revisions and install targets.
2. **Resolved software:** exact commit IDs, target-machine dependency policy and
   actual installed dependency/interpreter/platform identities selected for the run.
3. **Prepared release:** isolated checkout(s) and an environment verified against
   that resolved manifest. Existing releases remain unchanged while referenced.
4. **Execution evidence:** which prepared release each job used; its readiness or
   preparation error is separate from scheduler acceptance and job success.

There is an existing conceptual collision: profile `venv_path` selects both the
AutoSlurm submission helper and the application's activation. The preparation
contract must separate helper/bootstrap and application-runtime roles explicitly;
never update a helper environment while using it to submit another run.

## Proposed module boundaries

| Module | Responsibility |
|---|---|
| `software_manifest` | Pure validation/normalization of requested and resolved project/environment specifications |
| `git_projects` | Clone missing repositories, resolve refs, fetch managed caches and materialize exact commits; no mutation of active release checkouts |
| `software_sources` | Implemented current-host source orchestration and exact preparation/failure evidence; no runtime readiness |
| `software_status` / `software_probe` | Implemented selected-machine read-only Git observations through the shared SSH adapter; portable probe needs no remote AutoSlurm upgrade |
| `software_requirements` / `environment_probe` | Implemented local declared expectations, selected-interpreter distribution/source metadata and pure compatibility comparison; no scientific imports |
| `python_environments` | Prepare an isolated environment, install specified projects through its own interpreter and verify installations |
| `software_releases` | Coordinate staging, readiness checks, locking, publication/reuse and preparation evidence |

The first, second and source-orchestration modules are implemented; the environment
and release modules remain proposed. Extract existing machine/transport policy rather than
adding another SSH implementation. Keep side effects behind adapters and make
pure manifest/fingerprint decisions testable without Git, pip or a filesystem.

## Bundle contract to settle first

Current bundle JSON is a dictionary of jobs, with no top-level metadata envelope.
MVP7.1 attaches an optional shared `software` request to every job, normalized
and compared by one manifest owner. `attach_software_manifest` copies/attaches
the request; no top-level metadata is interpreted as a job. Existing containers
remain dictionaries of jobs, and bundles without software retain current behavior.
Manifest version 1 is new metadata, not a new bundle-container version.

The implemented request contains named repository identities, optional revisions,
repository-relative install `subdirectory` and an optional logical `runtime`
name (default `default`). Distribution/import/entry-point checks are deferred to
the environment contract; unsupported fields fail rather than being ignored.
Infrastructure roots/interpreters and dependency sources belong to that machine's
profile; application manifests must not embed machine-specific absolute paths.
Support one prepared application environment for the selected bundle initially.

## User-confirmed defaults (2026-11-12)

- **D5 Latest source when revision is omitted — accepted.** Resolve the current
  tip of the remote repository's default branch during each new preparation.
  Explicit branches/tags resolve once in the same way; explicit commits remain
  exact requests. Record both the requested selector and resolved full commit IDs.
  Determine these identities before release selection/reuse. Do not choose an
  older cached setup because a revision was omitted. If current remote resolution
  fails, report preparation failure rather than silently falling back to a cache.
  Inspecting an existing preparation or submitting its selected ready release
  retains its recorded commits; it does not resolve latest again. Updating means
  preparing a new release. Default-branch tip is the proposed precise meaning of
  latest; it does not guess the newest tag, release version or workstation state.
- **D6 Dependencies belong to the target machine — accepted.** The selected
  machine/runtime policy owns Python selection, requirements/constraints or
  lockfiles, package indexes/wheelhouses and installation options. A workstation
  dependency freeze or a package-owned lockfile is not required. Different
  machines may prepare the same source commits with different dependency sets.
  Package-declared compatibility requirements still apply; installation checks
  must expose conflicts rather than bypass them. A project lockfile can be used
  when explicitly selected by the machine policy, but is not the default contract.

- **D7 Separate software and result locations — accepted requirement.** Machine
  configuration must independently locate managed repositories/prepared software
  and scientific results, so they can use different cluster filesystems. The
  field is `software_root`. **Amended by the user in MVP7.0c:** merge project and
  results into one `results_root` for inputs/working directories/outputs. Only two
  scientific roots are configured. `config` is the canonical command/module;
  expose both roots in its editor, summary and direct root-setting flags.
- **D8 First-time clone — accepted requirement.** Preparation can start from a
  repository identity without an existing cluster checkout. Clone missing repos
  into the managed cache, fetch updates there and create isolated releases. Do
  not require a manual clone or repurpose/mutate an unrelated user's checkout.
  Clone/fetch failures are preparation failures and submit zero jobs.

Keep the default client request small: repository identities, optional revisions
and, only if needed, a logical runtime name. Detailed environment rules are
configured once for the machine. Preserve the existing operator-prepared runtime
path for bundles that do not opt into software preparation. Helper/bootstrap and
scientific runtime roles still need separate configuration.

A package version string alone never proves VCS/install identity. Record actual
installed dependencies even when no lockfile is supplied. For unlocked dependency
inputs, a matching source/configuration fingerprint does not establish that an
old environment satisfies a fresh resolution: make dependency refresh/reuse an
explicit machine policy and do not silently claim reproducibility or freshness.
No dependency solver framework is required for this MVP.

## SSH alias ownership (MVP7.0d, accepted and implemented)

Remote configuration uses one `ssh_alias` that selects the operator's SSH config
Host entry. No hostname/hosturl/username/key_path setup, key handling or connection
mode choice belongs in current AutoSlurm profiles. `config --ssh-alias` edits the
selection without connecting; submit/schedule have the same override. Local
profiles omit the alias. New run transport evidence stores only the alias, and
all SSH/copy/session adapters use it without identity flags.

Old hostname aliases normalize to ssh_alias on read/save and obsolete fields are
dropped. Old explicit host/user profiles need an explicit alias selection; no
inferred user@host fallback for new preparation. Existing saved job/receipt
transports retain their old address/key interpretation for historical management.
A recorded alias does not freeze the server behind an SSH config entry. Future
release identity must not claim endpoint immutability from an alias string alone.

## Software, input and output locations

Configure these infrastructure paths once per target machine; application
manifests continue to name repositories and logical runtimes, not absolute paths.
The two root names and configuration/path behavior are implemented in MVP7.0c;
managed caches/checkouts are implemented in MVP7.1; environment/release readiness
and remote preparation commands remain planned.

```json
{
  "ssh_alias": "research-cluster",
  "software_root": "/home/scientist/autoslurm-software",
  "results_root": "/scratch/scientist/studies"
}
```

| Root | Responsibility |
|---|---|
| `software_root` | Managed repositories and isolated source sets; scientific environment preparation still planned |
| `results_root` | Shared base for application inputs, working directories and scientific outputs |

`storage_root` remains the internal AutoSlurm state location; it is not another
scientific directory to organize. No separate project root is required.

A possible managed layout is `software_root/repositories/<repository-id>` and
`software_root/releases/<release-id>/{projects,environment}`. There is one
software root per selected machine initially; it can serve multiple Git projects.
Omitted roots default to `<storage_root>/software` and `<storage_root>/results`.
Summary displays symbolic defaults without a remote probe; execution saves actual
resolved values. Configured roots are absolute infrastructure paths. Application
jobs keep relative inputs/working directories/output paths, all under
`results_root`, independently of source release location. Configured data roots
and required inputs/working directories must already exist before preview; future
output subdirectories need not exist yet. Legacy unrooted jobs with no input/cwd
declarations retain their absolute-output/current-directory behavior.

Do not change cwd to a cloned package directory. Installed commands run from the
application's declared data working directory; package resources and scientific
inputs are distinct. New machine profiles have no independent `project_root`.
Old project-only/equal-root profiles coalesce to results_root, while conflicting
old roots require an explicit data-root choice before new work. Root-setting flags
remove the retired profile setting without moving files; saved old execution paths
retain their original meanings. Do not put results into managed code releases,
copy them during Git updates, or attempt to track them with Git. Validate declared
paths against managed release locations before dispatch to prevent writable
working/output targets from corrupting prepared software.

Record the selected software root, actual project checkout/environment paths,
input/working paths and resolved result paths with each run. Agents retrieve
these through preparation/execution inspection rather than constructing paths or
remembering the current profile. Profile edits cannot redirect historical jobs.
Required runtime/code/input/result paths must be available to the compute nodes;
node-local scratch staging and result transfer remain separate capabilities.
Preparation only publishes readiness; environment creation/publication must keep
its interpreter and entry-point paths valid rather than assuming venv directories
can be moved freely between staging and final locations.

## Preparation and submission behavior

- Perform Git/network/install operations on the login/preparation host, before
  dispatch. Compute jobs only activate a ready environment and run their command.
- Use operator-configured Git access. Do not store credentials in manifests,
  receipts or logs, or make agents manage private keys.
- Clone missing repositories and fetch updates under the selected software root
  on the preparation host; no manual initial checkout is required.
- Materialize exact revisions in managed release directories. Do not `git pull`
  active scientific checkouts or rewrite a shared environment. An update creates
  a new release; running/queued jobs retain their producing release.
- Key reuse by resolved commits, installation specification, target machine/runtime
  dependency policy and content identities, interpreter/platform identity and
  verified resolved dependencies. Include lockfile content when used. Respect
  dependency refresh policy for unlocked inputs. Concurrent preparation must not
  publish partial environments or permit two writers to corrupt one release.
- Use the chosen environment's `python -m pip`, with the target machine's
  dependency policy (requirements/constraints, optional lockfile, wheelhouse or
  permitted preparation-host index access). Do not automatically copy the local
  environment or upgrade every dependency. No dependency resolution on compute
  nodes. Missing network/dependencies or incompatibilities stop before submission.
- Verify Git commits and the installed distributions/import origins/entry points
  from outside source directories. Run `pip check`; install from fixed sources
  rather than editable links to mutable home checkouts. Package checks establish
  installation consistency, not scientific correctness.
- Persist bounded preparation evidence: requested/resolved manifest, release
  roots, selected machine/runtime dependency policy, actual installed dependencies,
  interpreter/environment identity, verification results and errors.
  Save the ready release in job execution evidence and agent handoffs.
- A preparation failure submits zero jobs. A ready release can be reused after
  verification; do not couple preparation retries to scheduler retries.
- Preparation should be a public explicit operation usable before submission;
  decide separately whether an opted-in bundle can request it during submit.
  Unspecified software retains the existing operator-prepared environment path.

## Tasks and completion criteria

- [x] **MVP7.0d Use SSH config aliases only.** Current config and CLI use
  ssh_alias, adapters share selection and new evidence stores no duplicate user/
  host/key settings. Historical transports remain readable. Update the user's
  existing local profile with a backup; verify all cluster effects through mocks.

- [x] **MVP7.0c Simplify config and application roots.** Canonical config modules/
  command, software_root and shared results_root, explicit old-profile root edits,
  recorded historical paths and local-only verification. This implements the
  configuration slice, not the remaining manifest/environment/release operations.

- [ ] **MVP7.0 Settle the manifest and environment roles.** Concrete bundle
  examples with omitted and pinned revisions, machine-owned dependency policy,
  helper/runtime separation, software and merged data roots, ownership,
  readiness/errors and bounded client operations. Requirements D5–D8 and the two
  configuration root names are confirmed; release layout/container/API details
  remain proposed. Shared manifest attachment is implemented in MVP7.1; finalize
  helper/runtime roles and machine dependency policy before MVP7.2.
  Record the implemented boundary before changing formats.
- [x] **MVP7.1 Implement source and manifest primitives.** Resolve exact commits,
  materialize isolated project sets and return structured preparation evidence;
  mock fetch/transport, and test omitted revisions resolving current upstream,
  default-branch changes despite a cached release, first-time cloning into a
  distinct software root, clone/fetch failure with no stale fallback, unavailable
  commits and dirty/shared checkout protection.
- [x] **MVP7.1b Read-only status and dependency checks.** CLI/Python reports
  Git state and configured environment metadata, checks important declared
  dependency constraints and desired application version/commit, and reports
  known mismatches/unknowns separately. Verify the standalone transport with
  local fixtures, then the explicitly authorized read-only rusty demonstration.

- [ ] **MVP7.2 Implement environment preparation/verification.** Install the
  project set into a staged environment, check the actual selected interpreter,
  versions/import paths/dependencies/entry points and publish readiness only when
  every check passes. Test the same commits with different machine dependency
  policies, changed requirements/constraints/optional locks, unlocked refresh
  policy, conflicting projects, wrong interpreter, failed install, interruption
  and concurrent preparation.
- [ ] **MVP7.3 Wire bundle execution and handoff.** Select ready release paths
  through the existing execution context, preserve legacy opt-out behavior, and
  verify two requested software revisions never change each other's queued job
  code/environment. Verify software separate from the shared input/output root,
  current relative-path semantics, configuration editor/summary retention, rejection of
  writable targets inside releases, and lookup after profile edits. Expose exact
  prepare/inspect evidence to terminal/Python/ACP.

## Non-goals and limits

No arbitrary remote shell deployment scripts, credentials service, Git push of
uncommitted workstation changes, automatic mutation of existing environments,
scientific retry engine, generalized multi-machine orchestration, environment
solver framework or automatic release garbage collection. Start with Git
projects and Python virtual environments; Conda environments, binaries/modules,
containers and offline artifact shipping can be separate increments if needed.
Cluster compatibility remains unverified until a separately authorized live test.

## Log

| Date | Event |
|---|---|
| 2026-11-12 | User requested a dedicated MVP for Git project versions and verified bundle-specified installations; scoped as MVP7 |
| 2026-11-12 | MVP7.0a user confirmed omitted revisions mean latest source and dependency setup belongs to the target machine; recorded D5/D6 and associated failure checks; no implementation started |
| 2026-11-12 | MVP7.0b user requested first-time Git cloning and independent package/results locations; recorded initial D7/D8, superseded the proposed third project root in MVP7.0c |
| 2026-11-12 | MVP7.0c config/two-root slice implemented; 405 offline tests passed, software preparation remains planned |
| 2026-11-12 | MVP7.0d SSH config aliases replace current host/user/key fields; 427 offline tests passed; local rusty profile updated with backup, no live cluster operations |
| 2026-11-12 | MVP7.1 shared manifest and current-host Git source engine implemented; 485 offline tests passed, including real Git against temporary local remotes; environments and execution remain planned |
| 2026-11-12 | MVP7.1b read-only software status and major dependency/application metadata comparisons implemented; 523 offline tests pass; authorized live rusty observations found matching Gaia dependency ranges but different local/remote code revisions |

## Proposed next delivery: remote application updates (2026-11-12)

This is the implementation proposal requested after the live status demonstration.
The following commands and runtime mechanics are not implemented or accepted
technical decisions yet. D5–D8 remain the accepted source/dependency requirements.

The next delivery should prepare an installation that a bundle can actually use.
Keep source resolution and status code; add installation, remote orchestration
and the smallest execution binding together. Do not call this workflow complete
when only a fetched source directory or an environment exists without job routing.

### Proposed user interface

```sh
# Bundle software manifest drives a project set and logical runtime.
asl software prepare --machine rusty --bundle-file /absolute/local/study.json

# Convenience for an application checkout: infer its Git origin and name.
# Omitted revision resolves latest remote default-branch tip.
asl software prepare --machine rusty --local-project /absolute/local/science
asl software prepare --machine rusty --local-project /absolute/local/science --revision FULL_COMMIT_ID

# Inspect the exact installation, including after an interrupted connection.
asl software status --machine rusty --release RELEASE_ID --json

# Bind new work explicitly; never change an existing machine profile implicitly.
asl submit study --bundle-file /absolute/local/study.json --machine rusty --software-release RELEASE_ID
```

Preparation returns a request/release ID, requested/resolved repositories,
installed distributions, base interpreter/environment identity, dependency
checks, exact ready-runtime locations and bounded errors. Terminal presentation
and JSON/Python results share that evidence. Exact status must distinguish a
managed installation from the old manual checkout so an unchanged manual clone
does not look like a failed managed update.

`--local-project` here is a convenience request constructor. It does not upload
working files, push Git, pin to local HEAD by default, or transfer the laptop's
installed environment. Explicit branch/tag/commit selection has the same meaning
as the bundle manifest; source-only and convenience requests use one backend.
If the local default-branch tip has not been pushed, it cannot be prepared from
the remote repository. Multiple projects continue to use the bundle form.

### Proposed runtime policy for the first usable slice

Use the machine's explicitly selected existing scientific environment as an
unchanged dependency base. Install only the requested application distributions
into a new, non-editable, release-specific location. A mismatch in JAX/NumPy/Torch
or another required dependency produces a preparation error and the status report;
it does not authorize upgrading the base stack. Checking only the focused status
list cannot satisfy an installer's complete declared-dependency consistency gate.
Build requirements and transitive dependencies must likewise have an explicit
machine policy; missing prerequisites cannot trigger a hidden install into the base.

The configuration contract separates helper/bootstrap, scientific dependency
base and prepared application identity, without adding another scientific root.
The existing environment may serve as helper and dependency base while remaining
unchanged, but each job records its exact application release independently.
Managed locations stay below software_root and scientific data stays in
results_root. Bundle requests contain logical runtime names, not host paths.

The concrete mechanism needs a focused prototype in MVP7.2a: for example, an
isolated application installation and launch environment layered on the selected
Python, with verified import and distribution precedence. A nested venv with
system-site-packages does not automatically expose packages installed into its
creating venv; test the actual visible stack instead of assuming inheritance.
If a venv is chosen, create it at its final unique path because interpreter and
entry-point paths can be embedded. Never rename a prepared venv and assume it
remains valid. Build artifacts and installation must reference fixed source sets.

This first policy isolates application updates, not an independently reconstructed
copy of every scientific dependency. The base environment's continued stability
is an explicit operator-owned condition. Record its identity/version inventory
and revalidate it before new dispatch; never claim immutable dependency isolation
from a mutable base. A fully separate dependency stack remains a later runtime
policy when genuinely needed. No automatic garbage collection is introduced.

### Implementation slices and completion gates

1. **MVP7.2a Contract and runtime prototype.** Specify machine policy, helper/
   application roles, artifact layout, request/release identity and environment
   visibility. Prove a requested application can override an old editable install
   without importing code from its checkout, while the selected scientific base
   remains visible and unchanged. Keep an ambiguous result unready.
2. **MVP7.2b Installation and verification.** Reuse `software_manifest`,
   `git_projects` and `software_sources`; add `python_environments` for build/install
   effects and `software_releases` for stage ordering/publication. Publish ready
   only after all requested projects, installation origins/versions/commits,
   interpreter, dependencies and entry points verify outside source directories.
   Preserve the full installed dependency inventory, even though the human status
   summary focuses on major libraries. Conflicts/missing inputs/install failures
   submit zero jobs and leave earlier releases/base environments unchanged.
3. **MVP7.2c Remote operation and diagnostics.** Add prepare CLI/Python and
   exact-release status through the existing SSH adapter. Deliver a versioned
   preparation worker independently of the old remote AutoSlurm installation;
   do not update the environment executing the worker. Create request identity
   before dispatch and retain execution-side stage/error evidence. Suggested
   stages: preparing_sources, building, installing, verifying, ready, failed.
   Connection loss is client uncertainty; inspect the exact request rather than
   blindly restarting. Concurrent requests cannot write one installation, and
   an exact repeated request must not create an untracked duplicate attempt.
4. **MVP7.2d Job binding.** Add an exact ready-release selector to preview and
   submission, pass it through existing execution context/script rendering, and
   include its source/runtime evidence in snapshots and receipts. The submission
   helper keeps its own environment; only the scientific job uses the selected
   application release. A selected release must satisfy the bundle's resolved
   source/runtime contract. Bind recorded commits, not latest again during submit.
   With no explicit revision, preparing a new release resolves latest; submitting
   that selected ready release retains its recorded commits. Require explicit
   selection initially; no surprise default switch or automatic preparation inside
   submission. Legacy opt-out stays usable.

Verify with local fake SSH, temporary Git remotes, wheel/install fixtures and
fake Slurm. Cover latest/pinned commits, multiple projects, an old editable copy
on the base environment, install origin/path precedence, major/dependency conflicts,
missing build requirements, wrong interpreter, partial installs, interruption/
connection loss, identity collisions and concurrent preparation. Two jobs bound
to different releases must keep their original code after subsequent preparation.
No Git/pip/install work may enter compute scripts. Real remote preparation remains
outside the read-only exception until a concrete demonstration is authorized.

## MVP7.1b read-only inspection boundary

`asl software status --machine NAME` shows current Git evidence under the
configured software_root, including immediate projects and managed source sets.
`--project` narrows that relative location; limits/timeouts and omitted-project
indicators bound discovery. Unknown/missing state is never labeled clean.

`--local-project` reads local pyproject.toml and optional requirements.txt;
`--requirements` selects another file. Focus on NumPy/JAX/JAXlib/PyTorch/SciPy
unless `--dependency` adds another library. Requirements are PEP 508/440 declarations
evaluated against target Python/platform markers; requires-python checks the
selected interpreter version and compatible stricter target dependency pins
pass. Unsupported directives, unconstrained dependencies or unverified evidence
stay unknown. `packaging` and older-Python `tomli` are declared client dependencies;
both active local interpreters already had the required runtime support, so no
base/test package installation was performed for this change.

The selected profile's venv_path/bin/python reads distribution metadata, which
establishes availability/version and, where recorded, VCS identity. Editable
installs also expose source HEAD/changes; immutable VCS installs use direct-url
commit metadata. User/local-declared versions or commits are compared separately.
Absence of required commit evidence cannot become a version-based identity pass.
Markers use target information; missing target markers cannot fall back to laptop
values. A missing/wrong environment is unknown with no system-Python fallback.
The portable probes use standard libraries, suppress bytecode/Git index writes,
and do not import AutoSlurm or scientific applications in the target environment.

The result is observation evidence, not runtime readiness or a mandatory
submission gate. It does not verify imports, ABI/CUDA/GPU availability, transitive
packages, future queue-time immutability or latest upstream state. Exit 1 signals
failed/missing inspection or requested mismatch/unknown compatibility; JSON retains
individual checks. Installation, remote preparation writes and dispatch integration
remain open tasks. No GitHub repository settings were touched.

Verification: 38 added checks, 523 full offline tests passed in 6.19 s, 39 expected
collision warnings, report `.development/test-runs/software-status-final.xml`.
The local fixture exercises the exact SSH stdin payload against a temporary Git
repo and virtual environment containing only fixture metadata. It checks real
constraint comparisons, interpreter identity, editable install subdirectories,
application commits and unchanged
Git index mtime. Additional tests cover pure comparisons, malformed transport,
credential-bearing requirement URLs, missing markers and CLI reporting.

The user-authorized live read-only checks on rusty observed clean AutoSlurm dev
213de79 and Gaia main d21f04d, with matching editable installation paths/commits
in `/mnt/home/aadam/envs/python3.11`. Installed NumPy 2.2.4, SciPy 1.15.2, JAX
0.10.2 and Astropy 7.0.1 satisfy the selected local Gaia declarations; its local
HEAD 0155e17 differed from the installed d21f04d, so the report correctly flags
`potential_problem` despite equal package version 0.1.0. Local uncommitted work
was reported separately. Snapshot reports are retained under `.development/test-runs/`
as `rusty-software-status.json` and `rusty-gaia-software-status.json`. These are
timestamped observations, not a guarantee about later installs/commits. No remote
files, installed packages, Git refs or jobs were changed.

## MVP7.1 implemented boundary and verification

Public operations: `normalize_software_manifest`, `attach_software_manifest`,
`bundle_software_manifest`, `prepare_software_sources` and
`SoftwarePreparationError.evidence`. The [agent recipe](../../agent/13_software_preparation.md)
contains omitted/pinned source examples, role boundaries and failure/handoff rules.
Runtime names are logical; they do not select an installed environment yet.
The existing helper/operator `venv_path` behavior is unchanged. A managed software
request is rejected by preview/submission before script/tracking/scheduler effects.

The host-side engine uses `software_root/repositories/<repository-hash>.git`,
`software_root/sources/<preparation-id>/<project-name>` and exact preparation
records under `software_root/source_preparations`. These are internal layouts,
not client path-construction contracts. Each invocation resolves upstream before
materializing its sources and makes a fresh set. Source evidence has state
`sources_prepared`, never runtime `ready`. Old source sets and scientific data
are not edited. Git/network effects live behind `GitCommands`; source orchestration
uses the existing atomic JSON owner. No new SSH implementation was introduced.

Repository caches carry ownership markers and locks; unsafe paths, wrong origins
and unmanaged caches fail before modification. Omitted/branch/tag requests require
upstream resolution even with a cache. Exact pins are fetched and verified as
commits. Clone/fetch/checkout failures, interrupted preparation and record failures
produce failed/partial evidence; raw Git errors are not recorded because they can
contain operator credentials. A killed process may leave a cache lock needing
operator inspection. Incomplete source directories remain inspectable. Reuse,
cleanup, automatic recovery, submodules and LFS are outside this source increment;
submodules are explicitly rejected. Root setup failure can occur before a tracking
record exists, while later record failures retain in-memory evidence.

Baseline: 427 offline tests passed in 3.16 s. Final: 485 passed in 4.86 s with
38 expected collision warnings. Report `.development/test-runs/software-sources-final.xml`.
The 58 added checks cover normalization/copying/shared requests, Git adapter
boundaries, latest changes/default-branch changes, exact pins/annotated tags,
unavailable/ambiguous/malformed refs, no stale fallback, checkout/object verification,
distinct roots/checkouts, subdirectory containment, cache ownership/origin/locking,
partial progress, interruption/tracking failures, evidence-collision protection and saved-bundle submission guards.
The executable fixture creates only temporary local Git remotes and checkouts;
it performs no internet or cluster operations. Existing science/CLI/ACP checks pass.
Task commit: `git log --grep '^MVP7.1:'`; no full `mvp7` completion tag.

## Implemented configuration/path slice (MVP7.0c)

The user requested renaming configuration to config and only two scientific roots.
Implemented locally on `dev`: `asl config` canonical action and `config` owner
modules, `software_root` editor/summary/settings, shared results-relative input/cwd/
output mapping and producing evidence. Historical `configuration` commands/modules
remain aliases. New installs gain `autoslurm-config`; current base commands can
use `asl config` without reinstalling entry points.

Root-only flags (`--machine NAME --software-root PATH --results-root PATH`) edit
local configuration without probes. They also permit an explicit merged root
choice for old conflicting profiles, without moving data. Configured data roots
require relative application paths, including results-only profiles that formerly
allowed absolute output overrides. New execution records save software/results
roots; old records with separate project/results fields remain readable. The
context's project_root slot remains solely for historical input-base interpretation.
The current venv_path continues to select operator-prepared software; a software_root
setting alone does not move/install code or implement release preparation.

Baseline: 392 offline tests passed in 3.33 s (38 collision warnings). Nine new
checks initially failed and the historical-path check passed; after implementation,
405 tests pass in 3.22 s (39 expected warnings), including three additional root-edit/
identity checks. Report `.development/test-runs/config-reviewed.xml`. Scientific
fixtures now stage inputs and outputs under temporary shared data roots; existing
array/reducer, submission, inspection and CLI/ACP checks remain passing. No real
cluster commands, base reinstall, runtime data migration or code preparation.
Task commit: `git log --grep '^MVP7.0c:'`. No `mvp7` completion tag: remaining
software-manifest/helper/runtime/source/environment tasks are still open.

## MVP7.0d verification

Baseline: 405 offline tests passed in 3.32 s. Fourteen new checks initially failed;
one historical explicit-transport check already passed. Final suite: 427 passed
in 3.23 s, 39 expected collision warnings. Report
`.development/test-runs/ssh-alias-final.xml`. Twenty-two added cases cover alias
validation before discovery, no local fallback, canonical profile serialization,
local-only alias edits, simple editor/summary, SSH/SCP/rsync/session arguments,
saved-alias stability, old explicit transports and retired CLI flags stopping
before application argument discovery. All prior scientific/receipt/CLI/ACP
workflows remain covered.

At the user's request, main's existing rusty profile now selects ssh_alias rusty.
The prior hostname contained a username, while local SSH config defines Host rusty.
Only connection settings changed; all non-connection values were verified equal.
Backup `.development/backups/pre-ssh-alias-20261112-121325/config.json`; SSH config
was not modified. No cluster connection, job submission or dependency installation.
Task commit: `git log --grep '^MVP7.0d:'`; full software-preparation MVP stays open.
