# Update the existing project checkout

AutoSlurm can send a Git pull to a configured machine. The software layer keeps
one existing checkout per project and creates no clones, caches, release copies,
installations or preparation records. This keeps the cluster's file usage small.

```sh
asl software update --machine cluster --project gaia-asteroseismology
```

The project path is relative to the machine's `software_root`. Its existing
branch and configured upstream determine what gets updated. The command runs
`git pull --ff-only` and prints the before/after commits, or says it is already
up to date. Use `--json` for structured results. Empty software commands show help.

The checkout must already exist and be clean. Local changes, untracked files,
a detached HEAD, an absent upstream or diverged history produce a clear error.
AutoSlurm does not stash changes, reset branches, merge history or clone a
missing project. Git authentication belongs to your existing Git/SSH setup;
the machine profile selects only an SSH alias.

Inspect the project independently:

```sh
asl software status --machine cluster --project gaia-asteroseismology
asl software status --machine cluster --project gaia-asteroseismology --local-project /path/to/local/project
```

The second form also compares important declared dependencies and the expected
application version/commit with metadata from the configured environment.
A pull changes source files, while package/environment installation stays
operator-managed. An editable installation can use updated source; a non-editable
installation needs its own installation step. This layer never runs pip.

Python callers use:

```python
from autoslurm import update_software, SoftwareUpdateError

try:
    result = update_software(machine="cluster", project="gaia-asteroseismology")
except SoftwareUpdateError as error:
    result = error.evidence
```

Success states are `updated` and `up_to_date`. Errors report `failed` or `unknown`
and include the available before/after commit evidence. No update records are
saved by this layer. If a connection is lost, the pull may have completed: inspect
the current project status before trying again. There is no automatic retry.

Submission continues to use your configured environment. Updating code is an
explicit action, separate from job submission; coordinate its timing for jobs
sharing the checkout. Compute jobs never run Git or package installation.

The earlier release-copy mechanism and its prepare/release selectors have been
removed. Existing records/directories are retained without automatic cleanup;
`software_runtimes` is no longer used for job runtime selection. The
[agent recipe](../agent/13_software_preparation.md) records the interface boundary.
Development validation uses temporary local repositories and mocked SSH/Slurm;
no live cluster update was performed during this implementation.
