# Config

Use `asl config` to manage machine profiles. Each machine has two scientific
locations: `software_root` for existing project checkouts and
`results_root` for inputs, working directories and outputs. They can live on
different cluster filesystems. Application definitions keep relative paths.

```sh
asl config --interactive
asl config --summary
asl config --view
```

The interactive editor creates profiles and supports editing, adding, renaming,
choosing the default and explicit validation. Adding/editing a machine retains
its environment/connectivity validation behavior, including remote SSH checks.
The default machine is used when an operation omits its machine selection.
`venv_path` selects the environment. An optional `env_command` in that profile
provides shell setup before activation, such as `module load jax/0.11.0`.
When both are present, jobs and config validation run the setup followed by
`source <venv_path>/bin/activate`, joined by `&&`; either setting alone keeps
its existing behavior. Software updates use the venv's Python directly.
In text prompts, Enter keeps the current value and `-` clears an optional field
(account or either root). Required fields such as the environment and SSH alias
cannot be cleared. Clearing a root restores its default location for future runs.
To update the roots or alias of an existing profile without remote commands:

```sh
asl config --machine cluster --ssh-alias research-cluster --software-root /home/user/software --results-root /scratch/user/studies
asl config --set-default cluster
```

The Slurm account is **optional**. Remove it for a cluster that should receive no
account directive, or set it explicitly where required:

```sh
asl config --machine rusty --clear-slurm-account
asl config --machine cluster --slurm-account research-account
```

These flags only edit local configuration and do not run SSH or environment
checks. Omit `--machine` to edit the default profile. Clearing removes
`slurm_account` from the JSON; missing, `null`, empty and whitespace-only values
also mean unset. `--summary` shows `-` for an unset account. AutoSlurm then emits
no profile `#SBATCH --account` directive and leaves account selection to Slurm/site
policy. A job's explicit `slurm.account` remains a Slurm directive: remove that
too if no account should be sent. Existing scripts and submission records are
unchanged; the setting applies to newly rendered scripts.

Remote profiles select one `ssh_alias`, matching a `Host` entry in SSH config.
AutoSlurm does not configure hostname, username or keys. To change only the alias:

```sh
asl config --machine cluster --ssh-alias research-cluster
```

The same `--ssh-alias` override is available to submit/schedule. Old hostname-based
aliases normalize to this field; old explicit host/user profiles require selecting
an alias. New run records retain the alias; older recorded transports are still
readable. Actual connection details stay in SSH config.

For example, `input_args = ["input_file"]` with `input_file = "inputs/data.json"`
and `output_dir = "study-42/summary"` both resolve under `results_root`.
A relative `working_directory` uses that same base; it does not change how
declared arguments resolve. Required inputs/data working directories must exist
before preview/submission; future output subdirectories need not exist yet.
The software location does not become the job's working directory.

Root settings are absolute infrastructure paths. Defaults are
`<storage_root>/software` and `<storage_root>/results`; summaries show symbolic
defaults without probing a remote host, and execution records save resolved paths.
Legacy unrooted jobs with no input/cwd declarations retain their old behavior.
`storage_root` separately holds AutoSlurm's internal definitions, scripts, receipts
and caches. Local configuration is `<storage_root>/config.json`, selected through
`AUTOSLURM_STORAGE_ROOT` or the process root selector. Configuration writes are
atomic; saving roots does not move files, clone repositories or install software.
`asl software update` explicitly pulls an existing checkout under `software_root`;
saving configuration never pulls code. See [software updates](software.md).
Environment/package installation remains operator-managed.

An old `project_root` alone becomes `results_root`; equal old roots are coalesced.
Different old project/result roots need an explicit choice with `--results-root`.
This removes the old profile setting without moving data. Existing saved runs
retain their recorded input/output paths and are not redirected by this edit.
New profiles with configured roots require relative application paths; absolute
output overrides previously allowed by results-only profiles are rejected.

`configuration` and the existing `autoslurm-configuration` command remain aliases.
The alias/root/account flags only save settings; they do not validate a live connection.
The interactive editor retains connection/environment validation.
New installations also expose `autoslurm-config`; the existing editable installation
can use `asl config` immediately without reinstalling console scripts.
See [the client workflow](../agent/01_client_workflow.md) and
[SSH configuration](ssh_configuration.md) for integration and connection details.
