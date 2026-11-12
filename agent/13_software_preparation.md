# Software preparation and release selection (MVP7.2)

This includes Git sources, read-only software status, application installation,
exact release inspection and explicit runtime selection. Default tests mock
transport and use temporary local Git repos, environments and package builds.
The user authorized a read-only status demonstration on rusty on 2026-11-12;
do not infer permission for other cluster operations. Compute jobs never clone
repositories or install packages.

## Inspect a machine before deciding what to run

```sh
asl software status --machine rusty
asl software status --machine rusty --project gaia-asteroseismology --local-project /Users/aadam/Projects/gaia-asteroseismology --dependency astropy
```

`--project` is relative to the configured software_root. Omit it to discover
immediate Git projects and managed source sets (default limit 20). Status reports
observed branches/commits/working-tree changes, missing/unreadable projects and
truncation. It does not fetch upstream refs or infer whether a branch is current.

`--local-project` reads local pyproject.toml plus requirements.txt when present,
inferring the application distribution, static version and local Git HEAD.
Uncommitted local source is flagged: HEAD cannot describe those changes.
`--requirements FILE` selects another local requirements/constraints file;
`--package`, `--expected-version` and `--expected-commit` supply explicit application
expectations. The local project's requires-python declaration is checked against
the selected interpreter. Requirements includes are bounded and cycles/unsupported options
are flagged. Direct-source dependency URLs are omitted from report evidence.

By default, focus on NumPy, JAX, JAXlib, PyTorch and SciPy. Repeat `--dependency`
to include other important distributions. Compare declared constraints against
target-environment metadata, not the workstation's installed freeze. A stricter
remote pin is compatible if it satisfies the local requirement; minor/transitive
libraries are outside this comparison. Markers use the target Python/platform.
An unpinned dependency, unsupported declaration or absent evidence stays unknown.

The machine's `venv_path/bin/python` reads installed versions and source metadata;
the probe verifies its environment prefix. It never substitutes system Python
for a missing/broken environment. No application/scientific packages are imported.
Editable installs expose their actual source commit/dirty state when readable;
VCS installs can expose a recorded commit. Matching version strings alone do not
establish source identity. Missing commit evidence for an expected commit stays
unknown. This is metadata inspection, not import-origin/GPU/scientific verification.

`--json` returns one object with projects, timestamp, environment, expectations
and compatibility checks. Compatibility is `compatible`, `potential_problem`
(a known mismatch), or `unknown`. Checks can mix compatible/mismatch/unknown;
inspect individual rows. Exit 1 means a project query failed, a selected path is
missing, or requested compatibility is mismatched/unknown; dirty Git status alone
is an observation. Exit 0 is scoped to checks actually requested. Git-only status
does not claim environment compatibility. An empty project list is not a clean
checkout. With `--project`, a missing repository is explicit and exits 1.

Python callers use `software_expectations(...)` and
`inspect_software(machine=..., project=..., expectations=...)` from `autoslurm`.
The SSH status path sends a standard-library probe over stdin using the shared
alias adapter. It needs system python3/Git and the selected environment, but no
remote AutoSlurm upgrade or copied helper files. Optional Git index locks and
Python bytecode writes are disabled. Status never clones, fetches, installs,
changes configuration or submits work, and does not certify runtime readiness.

## Bundle request

Keep scientific commands installed and independent of their source directory.
Keep inputs, cwd and outputs relative to the selected machine's `results_root`.
Software repositories and environments belong under its separate `software_root`.
Never put a machine-specific checkout path or workstation dependency freeze into
an application's software request.

```python
from autoslurm import attach_software_manifest, save_bundle

software = {
    "projects": [
        {"name": "science", "repository": "git@code-host:lab/science.git"},
        {"name": "tools", "repository": "https://code.example/lab/tools.git",
         "revision": "refs/tags/v2", "subdirectory": "python"},
    ],
    "runtime": "default",
}
# definition is the existing dictionary of jobs, including the reducer.
definition = attach_software_manifest(definition, software)
planned_path = save_bundle(definition, "study")
```

`attach_software_manifest` copies the jobs and request. Every job must carry the
same normalized request; mixed/missing declarations fail. There is no new bundle
container or metadata entry masquerading as a job. `normalize_software_manifest`
validates requests without side effects; `bundle_software_manifest(jobs)` extracts
the shared request from the loaded list of jobs. Version 1, runtime `default`,
revision `None` and subdirectory `.` are defaults. Project order is immaterial.

Omitted revisions resolve upstream HEAD on every new preparation, including
remote default-branch changes. Full 40/64-character lowercase commit IDs are
exact pins. Branches/tags resolve once; ambiguous short names need `refs/heads/`
or `refs/tags/`. A named tag must ultimately identify a commit. Repositories use
credential-free HTTPS, SSH URLs or SSH scp-style addresses. Git access belongs
to the operator's setup, including SSH config aliases. Local filesystem repo
addresses, credentials in URLs and arbitrary shell commands are not accepted.

`runtime` is a logical machine-policy selector. Its default Python is the
machine's `venv_path/bin/python`; `software_runtimes` can independently select
another interpreter and an absolute machine constraints file. The AutoSlurm
submission helper always retains its original configured environment.
Existing bundles without `software` keep their operator-prepared runtime behavior.

## Host-side operation and evidence

On an explicitly authorized preparation host, the supported Python primitive is:

```python
from autoslurm import prepare_software_sources, SoftwarePreparationError

try:
    evidence = prepare_software_sources(software, software_root=configured_software_root)
except SoftwarePreparationError as error:
    evidence = error.evidence
```

It acts on the current host and receives that host's configured absolute root.
It performs no SSH or machine discovery. Do not pass a cluster root to this
operation on a workstation and expect remote execution. A source cache is
managed by AutoSlurm; each operation makes fresh detached project checkouts.
Existing scientific checkouts, earlier source sets and data directories are
never pulled or replaced. Concurrent access to a cache reports a lock failure;
do not automatically remove another operation's lock. A process killed without
cleanup may need operator inspection before another preparation can proceed.

Retain the returned `preparation_id`, `evidence_path`, `manifest`, `software_root`,
and each project's requested `revision`, resolved `commit`, `checkout` and
`install_path`. Successful evidence has state `sources_prepared`. Failed Git or
tracking operations return `SoftwarePreparationError.evidence`, with state
`failed`, a bounded stage/message, the current project and completed projects.
`tracking_error` means the in-memory failure record could not be persisted.
Invalid requests/root arguments fail before Git; an unusable tracking root may
raise a filesystem error before an evidence record exists.

Inspect an existing result by its exact evidence reference; do not call prepare
just to inspect, because a new call resolves latest again and creates a new set.
Clone, fetch, resolution and verification failures never reuse an older result.
Raw Git diagnostics are omitted from stored errors because operator Git config
can put credentials in them. Failed/incomplete source sets are retained for
inspection; cleanup, source reuse and automatic lock recovery are not implemented.
Git submodules are explicitly rejected. LFS preparation is not supported.

`sources_prepared` does not establish an installed or usable environment. Use
the complete operation below and explicitly select the ready release. A managed
request without that selection fails before dispatch. Do not remove a request
to bypass validation. ACP preparation remains a later layer.

## Prepare, inspect and select a verified application release

```sh
asl software prepare --machine cluster --bundle-file /path/to/study.json
# Alternative: infer the name, literal Git origin and repository subdirectory.
asl software prepare --machine cluster --local-project /path/to/science
asl software prepare --machine cluster --local-project /path/to/science --revision FULL_COMMIT
asl software status --release RELEASE_ID --verify --json
asl submit --bundle-file /path/to/study.json --software-release RELEASE_ID
```

Every preparation makes a new ID and resolves omitted revisions upstream.
`--local-project` does not upload files, push commits or pin the local HEAD.
Use `--bundle-file` for multiple projects. Preparation never submits jobs or
changes configuration. Empty `software`, `software prepare` and `software status`
commands show help without contacting a machine.

```python
from autoslurm import prepare_software, inspect_software_release, preview_bundle, submit_jobs

try:
    release = prepare_software(machine="cluster", bundle_path=planned_path)
except SoftwarePreparationError as error:
    release = error.evidence  # Save the identity even when the outcome is unknown.
    raise
release_id = release["release_id"]
observed = inspect_software_release(release_id, verify=True)
preview = preview_bundle(planned_path, machine="cluster", software_release=release_id)
receipt = submit_jobs("study", machine="cluster", bundle_path=planned_path,
                      software_release=release_id)
```

The public function also accepts a normalized manifest as its first argument,
or `local_project=PATH, revision=REF`. Exactly one source selector is required.
An optional `on_created(ID)` callback runs after local identity publication and
before dispatch; CLI text mode prints that identity immediately. JSON mode emits
one final evidence object. Keep the same AutoSlurm storage selection when
inspecting a release: the local reference owns its original root and SSH alias.

Evidence states are `preparing_sources`, `building`, `installing`, `verifying`,
`ready` and `failed`. Client `requested`/`unknown` states describe a dispatch whose
remote outcome has not been established. Save `release_id`, `request`, exact
project commits, installation/wheel hashes and machine. Failure records retain
the current stage, completed projects and any source failure evidence. A
`tracking_error` means persistence failed; retain the returned evidence itself.

A lost/interrupted SSH response can leave work running. Inspect the exact ID;
never call prepare automatically to recover. Exact inspection never starts work.
`observation.state=unavailable` means saved state may be stale; it is not fresh
proof of readiness or failure. `state=missing` does not prove an earlier request
cannot still arrive. An interrupted remote stage may need operator inspection;
there is no automatic resume, lock removal or cleanup. Worker protocol 1 travels
through the shared SSH adapter over stdin, so preparation and inspection need no
remote AutoSlurm upgrade. Target preparation Python must be 3.11 or newer.

Readiness builds wheels from fixed commits with the target's existing build
tools, installs only the requested applications in a new release location and
checks installed code against wheel contents. It verifies distribution versions,
import origins, entry-point metadata/executables, Python requirements and the full
declared dependency closure, including markers/extras. Unlike the convenient
major-dependency status report, readiness enforces declared transitive requirements.
Dependencies are never downloaded or upgraded; conflicts fail. A machine constraint
file can add bounds; directives, includes and direct-source requirements are
unsupported. Existing pip/build backends must already be available. Relocated
wheel data/scripts, submodules and LFS are not supported in this first layer.

`--verify` freshly checks installed content, the recorded base inventory and
constraints. Preview/submission always perform that verification. A bundle's
runtime/projects/revisions must match; an omitted revision retains the selected
resolved commit during submission. Select a new release explicitly to update.
Even bundles without a software request can opt in through the explicit ID.
Jobs must invoke an installed application console command or
`python -m application.module`; direct source scripts/shell pipelines fail.
AutoSlurm pins the interpreter/application paths and rejects job overrides of
those runtime variables. Declared data/log paths cannot enter managed storage.
Submission snapshots/receipts retain producing release evidence alongside paths.

The scientific base remains operator-managed and must stay stable while jobs
are queued/running. Verification compares versions/locations, not every byte of
scientific libraries, drivers or external datasets. It checks metadata/origins
without importing applications or scientific libraries, and does not prove GPU
availability, console-callable correctness or scientific validity. Clients still
need cheap import/smoke checks and output validation. No job-side Git, installs,
automatic profile switch, dependency rebuild, live deployment, or release garbage
collection is performed.
