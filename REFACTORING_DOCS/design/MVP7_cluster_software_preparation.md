# MVP7 Bundle-driven cluster software preparation

## Status

Planned, 2026-11-12. The user requested Git-based preparation of several projects
and verification that the bundle's required versions are installed in its Python
environment. This document creates the MVP scope; these modules/APIs are not
implemented yet. Local development/mocked commands remain the execution scope.
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
| `git_projects` | Resolve refs, fetch into managed repository caches and materialize exact commits; no mutation of active release checkouts |
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

## Preparation and submission behavior

- Perform Git/network/install operations on the login/preparation host, before
  dispatch. Compute jobs only activate a ready environment and run their command.
- Use operator-configured Git access. Do not store credentials in manifests,
  receipts or logs, or make agents manage private keys.
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

- [ ] **MVP7.0 Settle the manifest and environment roles.** Concrete bundle
  examples with omitted and pinned revisions, machine-owned dependency policy,
  helper/runtime separation, ownership, readiness/errors and bounded client
  operations. Defaults D5/D6 are confirmed; container/API details remain proposed.
  Record the implemented boundary before changing formats.
- [ ] **MVP7.1 Implement source and manifest primitives.** Resolve exact commits,
  materialize isolated project sets and return structured preparation evidence;
  mock fetch/transport, and test omitted revisions resolving current upstream,
  default-branch changes despite a cached release, failed latest resolution with
  no stale fallback, unavailable commits and dirty/shared checkout protection.
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
  code/environment. Expose exact prepare/inspect evidence to terminal/Python/ACP.

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
