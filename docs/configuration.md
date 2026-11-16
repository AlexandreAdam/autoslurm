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
To set it, run `asl config --interactive`, choose **1) Edit machine fields** and
select the machine. The **Environment setup command** prompt follows the venv
path: type the command to add/replace it, press Enter to keep it, or enter `-`
to remove it. The same prompt appears when creating a profile. Clearing it
removes `env_command` from the saved profile and keeps `venv_path` unchanged.
Jobs and config validation run setup before `source <venv_path>/bin/activate`.
Jobs check each step and stop before the application if it fails, even without
a working directory. Software updates use the venv's Python directly.
In text prompts, Enter keeps the current value and `-` clears an optional field
(environment setup command, account or either root). Required fields such as the environment and SSH alias
cannot be cleared. Clearing a root restores its default location for future runs.

## Module initialization for cluster jobs

Some clusters define `module` only in initialized shells. A job submitted from a
laptop can otherwise fail with `module: command not found`, even though the same
job works when submitted from a cluster terminal. Configure initialization once
per machine; bundles and scientific applications need no special handling.

```sh
asl config --machine rusty --detect-module-init
```

This explicit action contacts the selected machine through its SSH alias (or
checks locally for a local profile). It saves the first readable regular file
among `/etc/profile.d/z00_lmod.sh`, `/etc/profile.d/lmod.sh`,
`/etc/profile.d/modules.sh`, `/usr/share/lmod/lmod/init/bash` and
`/usr/share/Modules/init/bash`, in that order. It never sources candidates or
executes `env_command`. A failed detection preserves configuration and reports
the failure; it never falls back to another machine. A detected readable file
is a candidate, not proof that modules or CUDA work on compute nodes.

For another site layout, set the trusted machine-owned initialization file:

```sh
asl config --machine rusty --module-init /site/modules/init/bash
asl config --machine rusty --clear-module-init
```

Setting/clearing is local configuration editing without SSH or file checks.
`--summary` includes `module_init`. In the interactive editor, the optional
**Module initialization file** prompt follows `env_command`; Enter keeps it and
`-` clears it. Menu action **7) Detect module initialization file** performs the
same explicit detection as the flag. Ordinary edits do not automatically detect.

With `module_init` configured, every newly generated job:

1. Checks whether `module` is already available; otherwise sources that exact
   file and checks that `module` became available.
2. Runs `env_command` to load your chosen modules and set variables.
3. Activates `venv_path`, then runs the application.

For example, the profile can contain:

```json
{
  "module_init": "/site/modules/init/bash",
  "env_command": "module load python/3.13 cuda/13 && export XLA_FLAGS=--xla_gpu_cuda_data_dir=$CUDA_HOME",
  "venv_path": "/home/user/envs/science"
}
```

Replace these example paths/module versions with your site's values. Paths are
literal absolute machine paths, including spaces; no `~` or variable expansion.
Only configure trusted initialization scripts. `env_command` remains trusted
shell code: use `&&` between operations whose failures must stop setup. The
generator checks its resulting exit status; it cannot infer failures hidden by
later successful shell commands. Never put a submit/update command there.

The same ordered setup underlies config validation and helper-root discovery.
Preview checks shell syntax without executing setup; submission does not run an
activation preflight. Remote submission-helper launch policy is unchanged.
No global `/etc/profile` sourcing or login-shell switch is introduced. Jobs
without `module_init` require no module system. Existing saved scripts and
receipts are unchanged; no packages, modules or environments are installed.

## Other machine settings

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

Known local configuration errors now show the failed path/field/profile, original
cause and corrective action, then exit 1. Use `asl config --summary --debug` (or
add `--debug` to another config action) to retain the original exception/cause
traceback. Parser misuse remains exit 2. Unexpected code errors are not turned
into ordinary configuration failures. `--view` still prints the raw JSON shape
for inspection; malformed JSON or unreadable files fail clearly.

An existing corrupt, unreadable or dangling-symlink configuration is preserved:
the interactive editor does not offer to replace it with a fresh default. Correct
the reported file/access problem explicitly. Only observed absence permits first-
use profile creation. An explicit `AUTOSLURM_STORAGE_ROOT` disables the historical
`src/config.json` lookup; without that selector, lookup is allowed only when the
primary file is actually absent, never after corruption or denied access.
Python callers catch `ConfigurationError` and read `.diagnostic.to_dict()`;
validation remains ValueError-compatible. Missing/unreadable reads and missing
activation now use that class instead of the previous OSError/AttributeError mix.
Filesystem publication errors remain a later diagnostic-adoption slice.

The visibility filter accepts only `active` or `all` (`asl filter active`,
`asl filter all`). A missing configuration defaults reads to active; malformed,
inaccessible or invalid configuration no longer silently resets the filter.
An invalid stored `bundle_filter_mode` identifies that exact field/file. Correct
the file first; filter reads and failed updates preserve its contents. This keeps
status and index selection from silently changing after a configuration failure.

New installations also expose `autoslurm-config`; the existing editable installation
can use `asl config` immediately without reinstalling console scripts.
See [the client workflow](../agent/01_client_workflow.md) and
[SSH configuration](ssh_configuration.md) for integration and connection details.
