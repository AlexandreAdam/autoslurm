# MVP7 Software status and single-checkout Git updates

## Status

The user's 2026-11-12 clarification supersedes the earlier source/release
preparation design: cluster file limits require **one existing checkout per
project**, updated in place. This layer's sole mutation is `git pull --ff-only`.
MVP7.2e removes the source/cache/wheel/release engines and their job selectors.
The prior implementation and design remain in Git history and the PLAN Done log;
they are not supported executable alternatives.

Development remains local only. Test remote behavior through mocks and temporary
local repositories. The earlier read-only rusty status exception does not
authorize live pulls, installations or cleanup. Existing historical evidence,
local rollback source and remote files must remain untouched by this task.

## User-confirmed decisions

- **Single copy — accepted, 2026-11-12.** Never create project clones, bare Git
  caches, detached source sets, worktrees, releases, application installations,
  environments, or preparation/release records in this layer.
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
  metadata checks remain useful. Updates run no installer, and jobs use their
  configured environment. Environment construction and revision-managed execution
  are outside this layer.
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
commits, stage, state, timestamp and any bounded error. States `updated` and
`up_to_date` mean a successful pull with readable commits. `failed` describes a
known rejection/failure; `unknown` means effects may have occurred without a
complete observation. No new persistent record format or migration is needed.

## Responsibilities

| Owner | Responsibility |
|---|---|
| `software_update` | Select one machine/profile, send the stdin probe through shared SSH, validate its response and expose available evidence |
| `software_update_probe` | Pure relative-project selector plus existing-checkout preflight, one Git pull and before/after observation; standard library only |
| `apps/software` | Help, text/JSON output and exit status |
| `software_status` / `software_probe` | Existing read-only Git inspection; status never pulls |
| `software_requirements` / `environment_probe` | Existing focused metadata/dependency/source comparisons without scientific imports |
| `transport`, `config`, `machine_paths` | Existing shared SSH/profile/root normalization |

The same updater executes locally or travels over SSH through stdin. Nothing is
copied/installed on the target, and installed remote AutoSlurm is not imported.
Git's own working tree and normal metadata are the only writes requested by the
updater; there is no additional state engine. Git's own index/ref locks handle
competing operations; no AutoSlurm lock/record file is introduced.

Preflight checks a real existing repository root inside software_root, a readable
HEAD, attached branch/upstream and a clean tracked/untracked tree. Pull disables
recursive submodule updates, rebase and automatic stashing. It uses no reset or
force option. Raw Git diagnostics are not returned because they may contain
credentials; recognized authentication/divergence failures have bounded messages.

A lost connection, Git timeout or unreadable post-pull HEAD produces unknown
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
