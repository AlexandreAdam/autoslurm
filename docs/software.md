# Prepare application code for scientific jobs

AutoSlurm can prepare a fresh application installation on a cluster's login
host before you submit jobs. Each release records the source commits and its
own installed application files. Updating creates another release, so an older
job script continues to use its selected application code.

The machine supplies an existing scientific Python environment. AutoSlurm keeps
its NumPy/JAX/PyTorch stack unchanged and installs the requested applications in
a separate location under `software_root`. Inputs, working directories and outputs
continue to use `results_root`. Compute nodes need no internet access.

## Prepare and use an update

Start with a configured SSH alias, `software_root`, `results_root` and `venv_path`.
The login host needs Git, system python3, and a selected application Python 3.11+
with pip and the project's build tools already installed. Git authentication
belongs to your existing SSH/Git configuration.

```sh
asl software prepare --machine cluster --local-project /path/to/science
```

This reads the local project's name and Git origin, then prepares the latest
upstream default-branch commit on the selected machine. Local edits are not sent.
Use `--revision FULL_COMMIT`, a branch or a tag to choose another revision.
For a bundle declaring several software projects, use this instead:

```sh
asl software prepare --machine cluster --bundle-file /path/to/study.json
```

The command prints a release ID before connecting and reports ready or the
failed stage when it finishes. Keep that ID:

```sh
asl software status --release RELEASE_ID --verify
asl submit --bundle-file /path/to/study.json --software-release RELEASE_ID
```

Your application should expose an installed command, or use
`python -m application.module`. Paths to source scripts are rejected for managed
releases. Python callers pass `software_release=ID` to `preview_bundle` and
`submit_jobs`; the [agent recipe](../agent/13_software_preparation.md) gives a
complete example and evidence contract.

Release status inspects that installation. Ordinary
`asl software status --machine cluster --project science --local-project PATH`
continues to describe the existing checkout/base environment, which preparation
does not update. Empty software commands show help.

## Dependencies and machine policy

Preparation builds non-editable application wheels without downloading dependencies
or changing the scientific environment. It checks all declared dependency
requirements against packages actually visible to the selected interpreter.
If a requirement conflicts, preparation fails; arrange a compatible scientific
base separately, then prepare another release. The lighter project-status report
focuses on major dependencies and is not a readiness certificate.

By default the application uses `venv_path/bin/python`. If its interpreter needs
to differ from the AutoSlurm helper, edit machine policy through the public API:

```python
from autoslurm import load_config, save_config

config = load_config()
config["machines"]["cluster"]["software_runtimes"] = {
    "default": {"python": "/cluster/scientific-env/bin/python",
                "constraints": "/cluster/policy/scientific-constraints.txt"}
}
save_config(config)
```

The optional constraints file lives on the target machine and contains plain
package requirements, without include files or installer options. Bundles select
only a logical runtime name. They do not carry laptop environment freezes.

## Interpret failures and recover

A failed source fetch/build/install/dependency check retains the release ID,
failed stage and partial evidence. A lost connection is **unknown**, because the
remote operation may continue. Inspect the same ID; do not automatically prepare
again. An unavailable observation reports saved state as potentially stale.
A missing remote record does not rule out a request still arriving.

Ready releases are checked again before new submission. Changed installation
files, base package inventory or constraints block dispatch. Existing jobs keep
their selected application installation; keep the underlying scientific base
stable for their lifetime. AutoSlurm does not clone that base or make drivers,
external data and library contents immutable.

Checks use metadata and import origins without loading scientific packages.
They do not establish GPU availability or scientific correctness. Retain an
application smoke command and validate outputs. Builds currently require existing
build tools; relocated wheel data/scripts, Git submodules and LFS are unsupported.
There is no automatic cleanup, interrupted-operation resume, dependency upgrade
or cluster helper deployment. Live cluster preparation has not been exercised;
tests use temporary local repositories/package builds and mocked SSH/Slurm.
