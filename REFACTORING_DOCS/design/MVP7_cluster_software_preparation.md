# MVP7 Bundle-driven cluster software preparation

## Status

In progress, 2026-11-12. The user requested Git-based preparation of several projects
and verification that the bundle's required versions are installed in its Python
environment. Configuration slices MVP7.0c/MVP7.0d and MVP7.1 source preparation
are implemented. Environment creation, runtime readiness and execution wiring
remain planned. Local development/mocked commands remain the execution scope;
the Git engine is verified with fake remotes and temporary local repositories.
No live cluster or remote installation has been performed.

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
