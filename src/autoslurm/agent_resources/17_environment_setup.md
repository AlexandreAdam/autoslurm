# Machine modules and environment setup

Interaction: configure a machine once, then preview/submit the same readable
application bundles from a workstation or cluster terminal. Module initialization
is AutoSlurm/operator infrastructure; scientific clients keep their commands,
named arguments and relative paths independent of site startup files.

Use `asl config --machine NAME --detect-module-init` to explicitly check common
readable regular initialization files on that machine. Remote profiles use their
SSH alias. It saves the first match in profile.module_init; it never sources files,
runs env_command or activates a venv. Missing candidates, launch/SSH/timeout or
unexpected responses preserve the configuration and report a ConfigurationError
diagnostic (CLI stderr/exit 1, --debug retains native causes where available).
Do not silently replace an existing path after failed detection. A readable
candidate is not proof of runtime/module/CUDA readiness on compute nodes.

Common paths, in order: /etc/profile.d/z00_lmod.sh, /etc/profile.d/lmod.sh,
/etc/profile.d/modules.sh, /usr/share/lmod/lmod/init/bash,
/usr/share/Modules/init/bash. Other sites can use
`asl config --machine NAME --module-init /absolute/site/init.sh`.
`--clear-module-init` removes it. Set/clear and ordinary reads do not contact the
machine. The interactive field follows env_command; Enter keeps, '-' clears.
Interactive action 7 explicitly detects. Summary includes the configured path.

Profile example (replace paths/module versions for the selected machine):

```json
{
  "module_init": "/site/modules/init/bash",
  "env_command": "module load python/3.13 cuda/13 && export XLA_FLAGS=--xla_gpu_cuda_data_dir=$CUDA_HOME",
  "venv_path": "/home/user/envs/science"
}
```

New scripts check module availability, source only the recorded initializer if
needed, verify module is then available, run env_command, and activate venv_path.
They preserve functions/exports in the job shell. Each failed step stops before
application execution with module_init, env_command or venv_path in stderr,
including profiles without working_directory. Inspect the exact attempt's bounded
Slurm logs; scheduler acceptance does not mean successful setup or computation.
An inherited module skips initialization; a venv-only profile needs no module.

Only trusted site scripts belong in module_init. Paths are literal absolute
machine paths, not '~' or variable expressions. env_command is trusted shell:
use && to propagate intermediate failures; its final status is what is checked.
Never put submission, software update or scientific computation in setup.
No global /etc/profile sourcing, login-shell switch, runtime path guessing,
installation or automatic submission retry occurs. Existing scripts/history
remain unchanged. Preview performs syntax/path checks, not activation; submission
has no activation preflight. Config validation and root discovery reuse ordered
setup, but the remote submission-helper launch policy is unchanged.

Public Python profiles through save_config/load_config, machine_config overrides
and activation_command_from_config accept module_init; invalid paths use the
shared ConfigurationError contract. Detection is exposed through the config CLI.
Offline checks cover clean/inherited module shells, failed/no-op/missing
initializers, setup/activation failures, quoting, local/mocked remote identical
preview/dispatch scripts and detection preserving state without executing setup.
