# MVP7 Bundle-driven cluster software preparation

## Status

Planned, 2026-11-12. The user requested Git-based preparation of several projects
and verification that the bundle's required versions are installed in its Python
environment. This document creates the MVP scope; these modules/APIs are not
implemented yet, except the configuration/path slice MVP7.0c described below.
Local development/mocked commands remain the execution scope.
No repository fetch, remote installation or cluster command is authorized by
this planning step alone under the current local-only working agreement.

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
| `python_environments` | Prepare an isolated environment, install specified projects through its own interpreter and verify installations |
| `software_releases` | Coordinate staging, readiness checks, locking, publication/reuse and preparation evidence |

These names are proposed. Extract existing machine/transport policy rather than
adding another SSH implementation. Keep side effects behind adapters and make
pure manifest/fingerprint decisions testable without Git, pip or a filesystem.

## Bundle contract to settle first

Current bundle JSON is a dictionary of jobs, with no top-level metadata envelope.
MVP7.0 must choose an optional shared manifest attachment without accidentally
interpreting metadata as a job. Keep current bundles usable; a new versioned
container would require an explicit release boundary. Do not silently invent one.

The specification needs repository identity, an optional revision and optional
project-relative install subdirectory/distribution/import/entry-point checks.
An optional logical runtime name may select a target-machine environment policy.
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

## Software, input and output locations

Configure these infrastructure paths once per target machine; application
manifests continue to name repositories and logical runtimes, not absolute paths.
The two root names and configuration/path behavior are implemented in MVP7.0c;
managed release layout, cloning and environment preparation remain planned.

```json
{
  "software_root": "/home/scientist/autoslurm-software",
  "results_root": "/scratch/scientist/studies"
}
```

| Root | Responsibility |
|---|---|
| `software_root` | Configured/recorded location for managed repositories, source releases and scientific environments; preparation still planned |
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

- [x] **MVP7.0c Simplify config and application roots.** Canonical config modules/
  command, software_root and shared results_root, explicit old-profile root edits,
  recorded historical paths and local-only verification. This implements the
  configuration slice, not the remaining manifest/environment/release operations.

- [ ] **MVP7.0 Settle the manifest and environment roles.** Concrete bundle
  examples with omitted and pinned revisions, machine-owned dependency policy,
  helper/runtime separation, software and merged data roots, ownership,
  readiness/errors and bounded client operations. Requirements D5–D8 and the two
  configuration root names are confirmed; release layout/container/API details
  remain proposed.
  Record the implemented boundary before changing formats.
- [ ] **MVP7.1 Implement source and manifest primitives.** Resolve exact commits,
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
