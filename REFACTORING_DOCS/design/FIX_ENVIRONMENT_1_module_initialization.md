# FIX.ENVIRONMENT.1 explicit machine module initialization

## Status and agreed scope

Authorized by Alexandre on 2026-11-16 after reviewing the remote-submission
report. Complete locally in 0.2.0.dev5; actual cluster discovery/deployment remains
outside this session. Existing user report is preserved separately.

The machine profile may record module_init, an absolute path to a trusted,
machine-owned Bash initialization file. New jobs initialize modules only if
module is unavailable, run env_command, then activate venv_path. Profiles without
module_init retain their existing setup without requiring a module system.
Initialization, setup and activation share one generator; failures stop before
the application, including jobs without a working_directory.

Explicit config detection checks a bounded list of common readable files on the
selected machine, saves the first match and reports its identity. It never
sources candidate files, invokes env_command or reads login profiles. A readable
candidate is not proof of compute-node readiness: config validation and runtime
checks remain distinct. Explicit paths support other sites. Ordinary config
reads/edits never discover machines; detection is an explicit contact operation.

One config field, no global login-shell change, no runtime filename guessing,
module/package installation, submission retries or activation preflight. Existing
scripts/receipts are retained unchanged. Module initialization for jobs/root
discovery/config validation shares generation; helper launch policy remains
MVP10.4b. Receipt discovery, job naming and log relocation are separate tasks.

## Verification

Use .development/python, temporary state, fake module initialization/venv files,
and mocked SSH/Slurm only. Check configured initialization, inherited module,
missing/failing/non-defining initializer, setup and activation failures, quoting,
no-module profiles, config keep/set/clear/detect and failed detection preserving
configuration. Check rendered local/remote scripts and installed wheel/sdist
behavior before the version checkpoint.

49 new tests cover those boundaries plus real Bash execution under a clean
non-login shell, inherited exported module, paths containing spaces/quotes,
interactive detection and programmatic conflicts. 1288 full offline tests passed
in 10.75 s, 46 expected collision warnings; `.development/test-runs/module-initialization.xml`.
The AST inventory remains 262 routes/136 owners/20 broad catches. Build metadata
works without Git/importing runtime. Wheel and sdist rebuild match exactly;
disposable installed checks verify CLI/runtime/distribution identity, clean job
setup/failure, identical preview/dispatch text, mocked remote detection, preserved
config on error and packaged section17 guidance. Artifact hashes are recorded in
[the installation register](../installation-register.md).

## Forward constraints and log

No daily configuration was changed and no cluster was contacted. Configure once
explicitly to enable initialization; the existing editable source follows dev5
while installed metadata stays 0.1.0 without reinstall. Existing scripts and
receipts remain intact, and the pinned rollback source is unchanged. Discovery
by bundle receipt, run naming/log placement and helper setup remain separate.

2026-11-16: FIX.ENVIRONMENT.1 complete locally; annotated v0.2.0.dev5 checkpoint.
[PLAN.md](../../PLAN.md) retains MVP10.4b as the next task.
