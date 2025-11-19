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

Before scheduling, activate the environment specified in `autoslurm-configuration` and run:

```bash
pip install -e .
```

Every machine AutoSlurm talks to must have the package installed in the environment whose activation command lives in the configuration. 
Without this, the entry point does not exist and submissions will fail.

## Why registration removes path headaches

When you register a script, AutoSlurm runs it via the entry point in [project.scripts] instead of a hardcoded filesystem location. 
That avoids differences between local/remote paths and makes it safe to rename files or reorganize the source tree.
Just keep the pyproject file up-to-date.
