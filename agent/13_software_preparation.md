# Update and inspect existing software (MVP7.2f)

The software layer pulls the one existing checkout per project, then refreshes
its editable installation in the configured existing environment. This refreshes
new CLI entry points even when the Git commit is unchanged. Cluster file limits
rule out cloned caches, source sets, release copies and additional environments. The earlier preparation/release engine has
been removed. Compute jobs never update code. Current development tests mock
SSH/Slurm and use temporary local Git repositories; they do not update a cluster.

## Inspect a machine before deciding what to run

```sh
asl software status --machine rusty
asl software status --machine rusty --project gaia-asteroseismology --local-project /Users/aadam/Projects/gaia-asteroseismology --dependency astropy
```

`--project` is relative to the configured software_root. Omit it to discover
immediate existing Git projects (default limit 20). Status reports
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

## Pull the existing checkout explicitly

```sh
asl software update --machine cluster --project gaia-asteroseismology
asl software update --machine cluster --project gaia-asteroseismology --json
```

`--project` selects the existing Git checkout relative to `software_root`.
The checkout must already exist, be clean and have an attached branch with a
configured upstream. The operation verifies `venv_path/bin/python` belongs to the
selected environment before pulling, then runs `git pull --ff-only` once on that
branch. After every successful pull, including unchanged HEAD, that interpreter
runs pip install --editable against the same checkout with --no-deps,
--no-build-isolation, --no-cache-dir and --no-index. Dependencies/build tools stay
machine-owned; installer redirection/index configuration is ignored. No Python
fallback, package download, new source copy or environment creation is requested.
It does not switch branches, resolve the newest tag or select a different default
branch. Use the operator-configured branch; there is no revision selector.

```python
from autoslurm import update_software, SoftwareUpdateError

try:
    result = update_software(machine="cluster", project="gaia-asteroseismology")
except SoftwareUpdateError as error:
    result = error.evidence
    # Inspect the reported state. An unknown outcome must not trigger a retry.
    raise
```

Successful states are `updated` and `up_to_date`. Evidence contains `machine`,
`software_root`, `project`, `path`, `branch`, `upstream`, `before_commit`,
`after_commit`, `stage`, `observed_at` and `installation` (state, python, editable,
path and returncode). Success requires `installation.state=installed`; an unchanged
Git commit still has an installation observation. Failed/uncertain results are exposed
through `SoftwareUpdateError.evidence` or CLI JSON with exit 1. The software layer
writes no request, preparation or release records. Clients may retain returned
commit evidence in their existing experiment handoff.

Dirty/untracked files, a detached HEAD, absent upstream, missing checkout or a
project resolving outside the software root stop preflight. There is no stash,
reset, merge, clone or submodule checkout. Diverged history fails the pull.
Errors contain bounded explanations; raw Git output is omitted because operator
configuration can contain credentials. A failed pull can still have changed Git
metadata; inspect returned before/after evidence rather than assuming nothing
happened. The operation never retries automatically.

If pip exits nonzero, `stage=install` and `state=failed` retain the pulled commit;
the environment may be partially changed and Git is not rolled back. If Git/pip
times out, post-pull commit inspection fails or the SSH response is lost,
`state=unknown` means effects may have occurred. Inspect the current project and
selected environment before deciding what to do:

```sh
asl software status --machine cluster --project gaia-asteroseismology --json
```

This reads the current checkout; no operation ID or release record is required.
Unavailable status remains unavailable evidence. Do not automatically retry a pull
because the response was lost. SSH sends a standard-library probe through stdin;
no remote AutoSlurm upgrade or copied worker files are needed. An existing
configured environment with pip and the project's build backend is required.

## Job and installation boundary

Updating is an explicit operator action before submission, never part of
`preview_bundle`, `submit_jobs` or a compute script. Jobs continue to use the
configured `venv_path`/activation. Updates now refresh its editable project
installation by default; no environment or source-copy release engine is created.
Pip can write metadata/build artifacts in the existing checkout; the application
must ignore those generated files to keep future Git preflight clean.
Use existing software status with expected dependencies/commit to inspect the
configured installation separately. Coordinate update timing for jobs sharing the
checkout/environment; source and installation are mutable, not pinned per job.

The removed surfaces are `prepare_software_sources`, `prepare_software`,
`inspect_software_release`, `SoftwarePreparationError`, `asl software prepare`,
`software status --release` and submit/preview `software_release` selectors.
Historical request normalization helpers and saved job/record inspection remain
readable, but a bundle `software` runtime request is rejected before submission;
new definitions use the operator-prepared environment. `software_runtimes` no
longer selects application runtimes. No existing records, source copies or
installation directories are deleted or migrated automatically.

Empty `software`, `software update` and `software status` commands show help
without contacting a machine. Scientific output validation remains client-owned.
