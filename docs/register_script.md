# Registering a script (optional)

AutoSlurm can run any Python file by specifying a path, but registering the CLI in your python environment makes it so you no longer need to worry about hardcoded paths.

## How AutoSlurm submits jobs

When you run `autoslurm-schedule`, AutoSlurm saves the job metadata in `$AUTOSLURM/jobs/...` and generates a SLURM script under `$AUTOSLURM/slurm/...`. Before the job is submitted, AutoSlurm sources the `env_command` you configured (see [Configuration](configuration.md)), so the virtual environment already contains your package. The generated SLURM script then executes the registered entry point, e.g. `train-model --epochs 10`.

## Declare entry points

Add your CLI to `pyproject.toml` or `setup.cfg` so it can be referenced by name:

```toml
[project.scripts]
train-model = "my_package.train:main"
```

This entry creates an application called `train-model` which can be used in the terminal from anywhere to execute the main function inside `PATH/my_package.train.py`, 

## Install the package inside the configured environment

Before scheduling, activate the environment specified in `asl config` and run:

```bash
pip install -e .
```

Every machine AutoSlurm talks to must have the package installed in the environment whose activation command lives in the configuration. 
Without this, the entry point does not exist and submissions will fail.

## Why registration removes path headaches

When you register a script, AutoSlurm runs it via the entry point in [project.scripts] instead of a hardcoded filesystem location. 
That avoids differences between local/remote paths and makes it safe to rename files or reorganize the source tree.
Just keep the pyproject file up-to-date.

## Path argument standard (portable bundles)

For machine-portable reruns, prefer **relative** paths in job `script_args`.
AutoSlurm rewrites relative paths to machine-specific absolute paths at SLURM script generation time.

Standard fields:
- `output_dir` is always treated as a path argument and normalized automatically.
- Additional path-like arguments should be declared explicitly via `path_args` in the job payload.

Example:

```json
{
  "script": "substructure-lens-transfer-function",
  "path_args": ["output_dir", "jacobian_h5"],
  "script_args": {
    "output_dir": "substructure_lens/results/transfer_production/...",
    "jacobian_h5": "substructure_lens/results/build_jacobian/.../jacobian_block.h5"
  }
}
```

Rules:
- relative path values in declared `path_args` are resolved against the machine `results_root` (or `<storage>/results` fallback),
- rooted profiles and explicit path contracts require relative paths without
  `..` traversal; historical unrooted profiles retain their absolute-path behavior.
- required input files use `input_args`; preview/submission checks their availability.

## Readable named arguments

Prefer one typed CLI command per job kind, with individual scalar settings in
`script_args`. A fixed command such as `train-model fit` belongs in `script`;
the job's settings remain visible in the saved bundle:

```json
{
  "name": "fit",
  "script": "train-model fit",
  "script_args": {"label": "pilot's first run", "seed": 17, "bands": "g,r", "verbose": false},
  "slurm": {"time": "00:05:00"}
}
```

AutoSlurm compiles literal arguments after resolving paths, then shell-quotes
each value. Plain words remain unquoted; spaces, quotes and metacharacters stay
within one value. Supply ordinary strings without manual escaping. Control
characters, nested values and malformed option names fail locally. `True` emits
`--flag`; `False` is omitted, so boolean CLI defaults must be off. Keep effective
defaults visible in JSON. Use CSV strings for lists in Typer clients; existing
raw bundles retain `--flag a b` lists and trailing positionals, now quoted too.

Shell expressions in values are literal: `$HOME`, `$(command)` and `*.fits` are
not expanded. For runtime values, let the command read its environment or use
the job's explicit `runtime_environment` mapping. The `script` prefix itself
retains shell-command semantics; keep job settings in named arguments.

Validate against the actual CLI signature before saving; literal/shell checks
cannot detect an unknown application option or wrong scientific setting. The
same compiler is used by `preview_bundle` and submitted scripts. This changes
new script rendering without rewriting saved bundles or historical receipts.
