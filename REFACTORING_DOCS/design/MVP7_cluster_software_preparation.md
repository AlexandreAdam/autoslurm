# MVP7 Software status and single-checkout Git updates

## Status

FIX.CONFIG.2 (2026-11-13) exposes env_command in interactive creation/editing;
Enter keeps the value and `-` removes it. The existing shared activation and
post-save validation are reused. See the interactive setup amendment below.

FIX.CONFIG.1 (2026-11-13) amends machine configuration: the user requires an
optional Slurm account and a way to clear it. See the account amendment below;
this is separate from the proposed command/job interface investigation.

FIX.SOFTWARE.1 (2026-11-13) restores normal pip build isolation and composes
env_command setup before venv activation; it supersedes the MVP7.2f no-index/
no-build-isolation requirements below. Temporary build environments are permitted;
no additional persistent project/runtime environment is created.

The user's 2026-11-12 clarification supersedes the earlier source/release
preparation design: cluster file limits require **one existing checkout per
project**, updated in place. MVP7.2f amends the original pull-only behavior with
an editable installation in the configured existing environment after each pull.
MVP7.2e removes the source/cache/wheel/release engines and their job selectors.
The prior implementation and design remain in Git history and the PLAN Done log;
they are not supported executable alternatives.

Development remains local only. Test remote behavior through mocks and temporary
local repositories. The earlier read-only rusty status exception does not
authorize live pulls, installations or cleanup. Existing historical evidence,
local rollback source and remote files must remain untouched by this task.

## User-confirmed decisions

- **Single copy — accepted, 2026-11-12.** Never create project clones, bare Git
  caches, detached source sets, worktrees, releases, additional persistent environments or
  preparation/release records. MVP7.2f refreshes an existing editable install.
- **Existing branch, latest upstream.** Pull the existing checkout's configured
  tracking branch with `--ff-only`. Do not guess/switch the branch, pin an older
  commit, stash changes, reset history or merge divergence. Earlier fresh-default-
  branch/source-pin proposals are superseded for this update-only layer.
- **Two scientific roots remain.** `software_root` locates existing checkouts;
  `results_root` owns relative inputs/cwd/results. Application path resolution
  and historical producing paths stay unchanged.
- **SSH config ownership remains.** Use only `ssh_alias`, through the shared
  adapter. Operator Git/SSH configuration owns repository authentication.
- **Dependencies remain machine-owned.** Existing read-only dependency/application
  metadata checks remain useful. Updates reinstall the project editable with
  --no-deps with normal build isolation. Build requirements may be downloaded
  temporarily; scientific runtime dependencies remain operator-managed. Jobs use their configured environment; environment
  construction and revision-managed execution remain outside this layer.
- **Explicit update.** Submission/preview/compute scripts never pull code.
  The operator coordinates update timing for jobs sharing mutable source.

## Public interface

```sh
asl software update --machine cluster --project gaia-asteroseismology
asl software update --machine cluster --project gaia-asteroseismology --json
asl software status --machine cluster --project gaia-asteroseismology
```

`--project` is relative to software_root and selects the repository's actual
checkout root. A missing project is an error, not an instruction to clone.
Empty software/update/status commands show help without machine discovery.

```python
from autoslurm import update_software, SoftwareUpdateError
result = update_software(machine="cluster", project="gaia-asteroseismology")
```

Failures raise `SoftwareUpdateError` carrying `.evidence`. The result reports
version 1, machine/root/project/path, current branch/upstream, before/after
commits, stage, state, timestamp, installation outcome and any bounded error. States `updated` and
`up_to_date` mean a successful pull with readable commits and completed editable installation. `failed` describes a
known rejection/failure; `unknown` means effects may have occurred without a
complete observation. No new persistent record format or migration is needed.

## Responsibilities

| Owner | Responsibility |
|---|---|
| `software_update` | Select one machine/profile, send the stdin probe through shared SSH, validate its response and expose available evidence |
| `software_update_probe` | Pure relative-project selector plus checkout/environment preflight, one Git pull, editable refresh and stage evidence; standard library only |
| `apps/software` | Help, text/JSON output and exit status |
| `software_status` / `software_probe` | Existing read-only Git inspection; status never pulls |
| `software_requirements` / `environment_probe` | Existing focused metadata/dependency/source comparisons without scientific imports |
| `transport`, `config`, `machine_paths` | Existing shared SSH/profile/root normalization |

The same updater executes locally or travels over SSH through stdin. The probe is not
copied/installed on the target and never imports installed remote AutoSlurm; it
refreshes the application editable through the selected environment's pip.
Git working-tree/metadata and the project's editable install metadata/entry points
are the writes requested by the updater; there is no additional state engine. Git's own index/ref locks handle
competing operations; no AutoSlurm lock/record file is introduced.

Preflight checks a real existing repository root inside software_root, a readable
HEAD, attached branch/upstream and a clean tracked/untracked tree. Pull disables
recursive submodule updates, rebase and automatic stashing. It uses no reset or
force option. Raw Git diagnostics are not returned because they may contain
credentials; recognized authentication/divergence failures have bounded messages.

A lost connection, Git/install timeout or unreadable post-pull HEAD produces unknown
rather than invented success or an automatic retry. Inspect current Git status
through the existing public status operation. There is no release identity to
recover or background retry/resume service. A reported failed pull may still have
updated Git metadata; retain any observed commit evidence.

## Removed interfaces and retained data

Remove source/release preparation modules and their copy-producing tests;
replace them with focused single-checkout safety tests. Remove public
`prepare_software_sources`, `SoftwarePreparationError`, `prepare_software`,
`inspect_software_release`, software prepare/release CLI flags, and
`software_release` selection in preview/submission/execution context.

Historical pure manifest normalization remains for reading/validation. Managed
bundle runtime requests are rejected explicitly; new bundles use configured
operator-prepared environments. Existing snapshot/receipt inspection remains
readable without migrating or rewriting stored metadata. Old release paths
inside already-created scripts remain literal historical evidence.

Do not delete existing local or remote operation evidence/copies automatically.
Any actual cluster cleanup is a separate operator operation, outside this task's
local-only scope. Base Conda continues importing main dev; the pinned rollback
checkout remains unchanged. Old `software_runtimes` config fields are retained
as data but no longer interpreted.

## Verification

Task MVP7.2e in [PLAN.md](../../PLAN.md) owns completion. Required cases include
one checkout through repeated updates, no duplicate/install/record operations,
changed/up-to-date commits, clean/dirty/untracked/diverged/detached/missing branches,
missing/unsafe paths, exact SSH stdin execution, malformed/lost responses with
no retry/fallback, and existing scientific/submission/status behavior.
**Final:** 525 offline tests passed in 5.53 s, 39 expected collision warnings;
report `.development/test-runs/software-update-final.xml`. Thirty-two new cases
replace the retired copy-engine tests. The Git fixture proves repeated updates
use the same working copy, then executes the exact SSH payload through fake
transport and rejects divergence without resetting local work. Mocked tests
cover missing/unsafe paths, dirty/untracked/detached/unconfigured branches,
commit reporting, authentication/fast-forward failures, timeouts/malformed/lost
responses without retry, unchanged storage files and useful CLI help/output.
Existing science, submission, inspection and metadata comparisons still pass.

The wheel was built from clean temporary sources to exclude stale build-cache
copies of removed modules. An isolated target installation passed public API,
absence-of-old-API and update-help smoke checks. Artifact:
`.development/artifacts/mvp7.2e/autoslurm-0.1.0-py3-none-any.whl`, SHA256
`e43ec1dcaa52adabe467f4f8c65a385f75250cfecdb3051bedfdd306114377b0`.
Base Conda still imports main dev; clean pinned rollback source/import was
verified at `33bcbd3`. Existing local operation evidence and user edits were
preserved. No cluster contact/update/install/cleanup or daily config mutation
was performed. Task prefix `MVP7.2e:`, local milestone tag `mvp7`; no deployment.

## Submission SSH ownership fix (FIX.SSH.1)

The user requested this narrow fix before MVP8: submission must honor configured
connection sharing and avoid macOS's long TMPDIR socket paths. The shared
transport builds a non-connecting `ssh -G` observation. A non-none ControlPath
with automatic ControlMaster or enabled ControlPersist yields an empty options
list: both sbatch and the bulk driver inherit SSH configuration, and AutoSlurm
never explicitly opens/closes the user's master. Local sessions still yield None.

Otherwise the existing owned-master lifecycle remains, using
`/tmp/asl-ssh-*/cm-%C` on POSIX; the default temp directory is used if `/tmp` is
absent. Failed/malformed configuration inspection falls back once. No settings,
credentials or config writes are added. Cleanup cannot erase an observed receipt
or a body exception. Verification is offline with fake subprocess commands;
actual submission remains the user's check.

Final verification: 542 offline tests passed in 5.64 s, 39 expected warnings;
report `.development/test-runs/ssh-session-final.xml`. Seventeen new cases cover
both submit adapters, auto/autoask/persistence, malformed/failed observations,
short sockets under long TMPDIR, cleanup failure and local no-ops. The existing
submission/job-runner/alias/persistence suites passed. No real SSH was invoked.

## Editable-install amendment (MVP7.2f, complete locally)

**User accepted, 2026-11-12:** software updates must run an editable install by
default to refresh new command-line entry points. This amends the earlier
pull-only policy, while retaining one checkout and one existing environment.
Use configured venv_path/bin/python; verify its prefix before pulling, never
substitute system Python or create an environment. After every successful pull,
including unchanged HEAD, run pip install --editable against that checkout.
Keep machine-owned dependencies/backend in place with --no-deps and
--no-build-isolation; disable cache/index access for this local project operation.
Missing build requirements are an installation failure, not permission to rebuild
the machine's scientific environment. No installs inside compute jobs/submission.

Installation evidence is additive in the existing returned object, not a saved
record: selected interpreter, editable source path, state and exit code. Overall
success requires installation success. Retain before/after Git commits if pip
fails; installed environment may be partially changed. Installation timeout or
lost SSH response is unknown and must not trigger a retry/reset. Never roll Git
back implicitly after a pip failure. Test with temporary local environments and
fake SSH only; no actual cluster installation is authorized by implementation.

Final verification: 576 full offline tests passed in 9.61 s, 39 expected collision
warnings; `.development/test-runs/software-editable-final.xml`. Fourteen net new
cases plus the expanded temporary Git/venv fixture verify interpreter mismatch,
missing/invalid configuration and unavailable interpreter before pull; install
failure/timeout with retained Git evidence; untrusted/malformed remote success;
no retry/fallback; unchanged-commit entry-point repair and a new CLI at unchanged
package version. The exact stdin SSH payload installs editable into that temporary
environment and imports source from the single existing checkout. Pip environment
redirection is disabled; no scientific dependencies are installed or changed.

Clean temporary-source wheel build and isolated target/API/evidence/help smoke
passed. Artifact `.development/artifacts/mvp7.2f/autoslurm-0.1.0-py3-none-any.whl`,
SHA256 `4994986c18e649411b7fc27e2f1d45c73942a1f8b957e7df7622a5f5ecedc782`.
Base editable source import/help and clean rollback source 33bcbd3 reverified.
No base install, actual cluster contact, cluster package/Git update, daily config
or tracking mutation. Push the completed task commit to origin/dev; existing
milestone tags and rollback source are not advanced by this amendment.

## Optional account amendment (FIX.CONFIG.1, 2026-11-13)

The user requires clusters to work without an explicit account directive. Profile
selection no longer requires `slurm_account`. Shared profile normalization treats
missing/null/empty/whitespace-only accounts as absent and removes the key on save;
nonempty string accounts remain supported. The existing renderer already emits a
profile account directive conditionally, so no parallel rendering policy is added.
Explicit job `slurm.account` options still render and must also be omitted if the
operator wants no account directive. Historical scripts/receipts are not rewritten.

`asl config --machine NAME --clear-slurm-account` removes the account;
`--slurm-account ACCOUNT` sets it. The flags are mutually exclusive, use the shared
settings writer, preserve other settings and never probe a machine. Omitting
`--machine` selects the default profile. Summary uses `-` for no account. The
interactive editor accepts `-` to clear optional account/software/results fields;
Enter keeps existing values. Required fields cannot be cleared. Existing
interactive post-save validation remains; it is mocked in tests. Clearing a
root restores its ordinary default for future execution, not a move of old data.

Verification: 593 full offline tests passed in 10.57 s, 41 expected bundle-name
collision warnings; `.development/test-runs/optional-account.xml`. Seventeen new
cases plus the replaced mandatory-account expectation cover normalization,
set/clear persistence, default/explicit selection, invalid edits without writes,
interactive creation/editing, config aliases, in-memory overrides, remote-context
rendering and preview/mock submission agreement, including retained explicit
accounts/partitions. No SSH or scheduler was contacted.

Clean temporary-source wheel install/config/render smoke passed; artifact
`.development/artifacts/optional-account/autoslurm-0.1.0-py3-none-any.whl`, SHA256
`491f184730042a666b49b448edb66be6a691296821a74de557da8a18ad7d3046`.
Base Conda's editable source was verified and its config handler cleared the local
rusty account; every other configuration setting was compared and preserved.
Backup: `.development/backups/optional-account-iym80kt7/config.json`.
No base package installation, cluster change, historical record change or pinned
rollback source change. The DOCS.3 command/argument proposals remain unimplemented.

## Plain editable build and activation amendment (FIX.SOFTWARE.1, 2026-11-13)

The user requires editable reinstalls to behave like `pip install --no-deps -e .`.
Removed --no-build-isolation and --no-index from the selected interpreter's pip
command. Default build isolation may download requirements declared by the
project into disposable build environments on the login host. The selected venv
needs pip, not a preinstalled setuptools/backend. Keep --no-deps, cache/version/
prompt controls and existing installer redirection guards. Only the project's
editable install changes in that persistent environment; scientific dependencies
are operator-managed. This explicitly supersedes MVP7.2f's offline/backend policy;
development tests still perform no downloads or cluster commands.

On nonzero pip exit, retain the pulled commit, failed installation state and exit
code. Add installation.output_tail: last 20 stdout/stderr lines, bounded to about
4 KiB, with credential-bearing URL lines omitted. Include the same tail in the
existing error message so Python, human CLI and JSON consumers can diagnose the
build. No retry, rollback or new saved record. Timeout/lost-response uncertainty
is unchanged. This tactical diagnosis is not completion of the broader MVP10.

Shared activation now composes env_command followed by the quoted venv activation
with `&&`; either setting alone keeps its behavior. Module loads can precede
activation without modifying the venv's bin/activate. Jobs and config validation
use that same function; the editor retains an existing env_command when editing
other profile fields. CLI help now describes the setup role. Software updates
continue to use venv_path/bin/python directly, without running the job preamble.
Existing profiles with both settings now intentionally execute both, including
redundant legacy activation commands. No daily profile was edited by this task.

Verification: 634 full offline tests passed in 9.16 s, 41 expected collision
warnings; `.development/test-runs/plain-editable.xml`. Eleven new cases cover
bounded/redacted pip tails and human/JSON visibility, composed/single activation,
editor retention and successful/failing local shell execution. The real Git/venv
fixture uses an in-project standard-library editable backend with no downloaded
requirements, confirms a conflicting runtime package is hidden during the build,
and verifies only the project is added to installed distributions. Actual local
and exact fake-SSH payload updates still refresh old/new CLI entry points at the
same version and preserve one source checkout. Three old integration script
expectations were updated for the deliberate both-settings activation behavior.

Clean temporary-source wheel install/flags/output-tail/activation smoke passed.
Artifact `.development/artifacts/plain-editable/autoslurm-0.1.0-py3-none-any.whl`,
SHA256 `afb047beeba30dc7ba3c512bb5cfc8c7420d5abda2f5dfd21870d479aea071b3`.
No network dependency download in tests, base Conda install, cluster contact,
daily configuration/tracking mutation or pinned rollback source change.

## Interactive environment setup amendment (FIX.CONFIG.2, 2026-11-13)

The user reported that the package supports env_command but the editor only
preserves an existing value silently. _prompt_machine_details now asks for an
optional **Environment setup command** immediately after the required venv path,
for both new profiles and edits. Existing prompt semantics apply: Enter retains
the current command; a new nonempty value replaces it; `-` removes the key.
Clearing setup keeps venv activation. Existing root/alias/account settings and
the shared writer remain in use; no extra environment or alternate config owner.

Validation and job rendering already compose env_command then venv activation
with `&&`. The editor continues to validate after saving an edit, including the
selected SSH/helper-root checks for a remote profile; tests mock all commands.
Software updates still invoke the configured venv Python directly. This fix
adds no direct env-command CLI flag and never edits a venv's bin/activate.

Six regressions cover add/replace/keep/clear/unset through the public interactive
CLI, exact saved profiles, quoted venv paths, actual validation command construction,
rendered preambles and creation through the configuration alias. Existing prompt
fixtures are updated for the additional field. Full-suite/package results are
recorded in PLAN.md; no actual SSH, daily config, environment or rollback edit.

Verification: 84 focused tests passed; full offline suite 803 passed in 10.98 s,
43 expected collision warnings; `.development/test-runs/config-env-command.xml`.
Clean-source wheel interactive/alias/save/clear/validation/render smoke passed;
SHA256 `61c2233cdd76b0107bc148111060e6349a7f3adaf7d64493b8e8206509d58a24`.
MVP10.3 remains unstarted; this requested editor fix is separate.
