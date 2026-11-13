# Update the existing project and its command-line tools

AutoSlurm pulls one existing project checkout and refreshes its editable install
in the machine's configured virtual environment. New command-line tools are
installed as part of the update. No additional source copy or environment is
created, keeping cluster file usage small.

```sh
asl software update --machine cluster --project gaia-asteroseismology
```

The project path is relative to the machine's `software_root`. Its existing
branch and configured upstream determine what gets updated. The command runs
`git pull --ff-only`, then uses `venv_path/bin/python` to run an editable pip
install from that same checkout. Installation runs even when Git is already up
to date, refreshing metadata and command-line entry points. The existing selected
environment must be configured and its interpreter verified before pulling.
Use `--json` for commit and installation evidence. Empty commands show help.

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
Updates refresh the project using `pip install --editable` with `--no-deps`,
`--no-build-isolation`, `--no-cache-dir` and `--no-index`. Machine-specific scientific
dependencies and build backends remain operator-managed; no dependency upgrades
or downloads are requested. Install missing build requirements/dependencies through
your machine's usual setup. Pip may write normal package metadata/build artifacts
in the existing checkout; keep those ignored by Git so the next update stays clean.
The install uses the configured interpreter and ignores pip environment/config
redirection; it never falls back to system Python or creates an environment.

Python callers use:

```python
from autoslurm import update_software, SoftwareUpdateError

try:
    result = update_software(machine="cluster", project="gaia-asteroseismology")
except SoftwareUpdateError as error:
    result = error.evidence
```

Success states are `updated` and `up_to_date`; both require
`installation.state=installed`. Git change and editable refresh are separate
observations. Installation evidence includes its interpreter, source path and
exit code. Errors report `failed` or `unknown` and retain available before/after
commit evidence. No update records are saved by this layer. If pip fails, the pull
remains in place and the environment may be partially changed. Installation timeout or a lost connection is unknown; inspect both
checkout and configured environment before deciding what to do. No automatic
retry or Git rollback is performed, and a failed install never reports success.

Submission continues to use your configured environment. Updating code is an
explicit action, separate from job submission; coordinate its timing for jobs
sharing the checkout or environment. Compute jobs never run Git or package installation.

The earlier release-copy mechanism and its prepare/release selectors have been
removed. Existing records/directories are retained without automatic cleanup;
`software_runtimes` is no longer used for job runtime selection. The
[agent recipe](../agent/13_software_preparation.md) records the interface boundary.
Development validation uses temporary local repositories and mocked SSH/Slurm;
no live cluster update was performed during this implementation.
