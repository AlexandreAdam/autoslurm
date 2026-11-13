# MVP7 Software status and single-checkout Git updates

## Status

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
  caches, detached source sets, worktrees, releases, additional environments or
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
  --no-deps/--no-build-isolation/--no-index, keeping scientific dependencies and
  build tools operator-managed. Jobs use their configured environment; environment
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
