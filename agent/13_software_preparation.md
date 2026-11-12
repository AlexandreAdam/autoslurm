# Software source preparation (MVP7.1)

This is a source engine for the preparation host. Environment installation,
remote preparation commands and ready-runtime submission remain planned. Current
development verifies remote behavior with mocks and temporary local Git repos.
Do not contact a cluster merely because this API exists. Compute jobs never
clone repositories or install packages.

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

`runtime` is a logical machine-policy selector. It does not mean the workstation
environment or the AutoSlurm helper environment. Runtime policies, Python and
dependency configuration will be implemented with environment preparation.
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

`sources_prepared` does not establish an installed or usable environment.
Preview/submission currently reject any managed `software` request before
scripts, receipts or scheduler dispatch, rather than running it in the legacy
environment. Do not remove the request to bypass this guard. Complete runtime
preparation and execution wiring are the next steps; no prepare CLI/ACP operation
exists yet. Scientific result validation remains application-owned.
