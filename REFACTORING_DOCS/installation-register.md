# AutoSlurm installation register

## Status

**Local `dev` activation verified, 2026-11-12.** The user explicitly selected the
main repository and base Conda commands for daily use of the refactor. The main
checkout is now branch `dev`, starting from tested MVP4 commit `89e2781`; activation
records are located with `git log --grep '^MVP4.4:'`. Earlier layouts below are
historical. Current tested code includes MVP7.0d: locate it with
`git log --grep '^MVP7.0d:'`; the last completed full milestone tag is `mvp6`.
No cluster installation or live
job was changed.

## Current local inventory

| Field | Active daily use | Test execution | Rollback baseline |
|---|---|---|---|
| Source | `/Users/aadam/Projects/autoslurm`, branch `dev` | Same active main source | `/Users/aadam/Projects/autoslurm/.development/stable`, detached `33bcbd34fb167fca67aa64739a013073c64167b1` |
| Python | `/opt/homebrew/Caskroom/miniforge/base/bin/python`, unchanged base Conda environment | `.development/venv/bin/python`, separate test dependencies; editable source repointed to main offline | `.development/stable-python` selects baseline source through PYTHONPATH with base Python |
| Commands | Existing base `asl` / `autoslurm` import main through the original editable install; no base reinstall needed | `.development/python` / `.development/asl` wrappers | `.development/stable-python` / `.development/stable-asl` |
| Default state | `/Users/aadam/Projects/autoslurm`, unless explicitly selected with `AUTOSLURM_STORAGE_ROOT` | `/Users/aadam/Projects/autoslurm/.development/state`; fixtures use temporary roots | `/Users/aadam/Projects/autoslurm/.development/stable`; old baseline does not support the environment root selector |
| Persistent config / jobs at activation | Config absent; zero non-dot jobs/scripts/logs/receipts/observations; no records migrated | Config absent and zero persistent runtime records | Empty fresh baseline runtime; never adopts active dev records implicitly |
| Package version | `0.1.0`, unreleased; identify code by branch/commit/import path | Same code/version | `0.1.0`; identify by pinned SHA/import path |
| Remote installation | Uninspected and unchanged; no cluster commands | All Slurm/SSH/transfer effects mocked | Remote installations retain their existing code and job ownership |

The initial development worktree `.development/checkout` remains at MVP4 on
`codex/mvp0-isolation`, with its pre-existing user edits. It is retained as a
snapshot, not the active editing/test import source. The baseline rollback wrapper
changes source selection only; it is not a separately cloned Conda environment.
No dependencies in base Conda were changed during activation.

## Activation evidence and retained work

- Candidate: `89e27817a620e48553638b9a09eb633b1590acbc`, tag `mvp4`;
  **333 offline tests** passed before activation. The full suite passed again
  from the active main source: **333 passed in 3.55 s**, 39 expected timestamp
  collision warnings; report `.development/test-runs/dev-main-activation.xml`.
- Narrow artifact check: built `.development/artifacts/mvp4/autoslurm-0.1.0-py3-none-any.whl`
  offline, SHA-256 `f93d1eb1927c22a832e65e556c4a8a20c459b76efa552be23d31c0a9aaf25f8a`.
  Isolated target installation under `/private/tmp/autoslurm-mvp4-wheel-smoke`
  imported independently, previewed a tiny job and performed cached inspection
  without scheduler calls. This is not a full distribution/resource audit.
- Original main working files: 38 files copied with verified SHA-256 hashes to
  `.development/backups/pre-dev-main-20261112-000207/files`; manifest, tracked
  patch, status, revisions and activation evidence are retained alongside them.
  Additional Git stash: `7016e9b87bdc682e5cf13640a6c12987d3b0ee1d`.
- Existing user changes in `REFACTORING_DOCS/README.md` and
  `REFACTORING_DOCS/requirements-gaia-asteroseismology.md` were restored byte-for-byte
  and remain excluded from implementation commits. Older mirrored docs were
  archived rather than reapplied over the current implementation guidance.
- Base daily commands and the test interpreter both import main source; test
  state stays separate. The test-only scientific example install also points
  to the main `examples/reference_client` source. Rollback wrappers import the pinned baseline and use its
  own root. Do not copy new dev tracking data into that older implementation.

## Rollback use

For read-only baseline help/import checks, use `.development/stable-asl --help`
and `.development/stable-python`. Its own state is separate and empty at
activation. The main `dev` branch and current records remain available for runs
created with the refactor. Switching new work back to baseline would be an
explicit routing decision; it does not undo submissions or migrate new records.

## Historical verification and release record

The following entries document earlier stages before local `dev` activation.
Their original pinned-main/separate-development layout is superseded above.

- **Baseline tests:** 195 unit tests and four mocked three-job submission cases
  passed. See [the baseline record](design/MVP0_safe_development.md#local-baseline-mvp01)
  for dependencies, guards, the missing accounting mock and limits.
- **Stable revision pin:** original checkout detached at the full baseline SHA.
  Base Conda is unchanged; development has its own environment. Do not edit
  stable source, advance its checkout, or upgrade its environment as part of
  ordinary development. This is operational separation, not a filesystem lock.
- **Local development isolation:** verified. Source, environment and state have
  distinct locations; the stable default root and empty runtime directories are
  unchanged. The nested `.development/` directory is ignored by the stable tree.
- **Development validation:** 238 tests passed in 1.21 s, including fresh-process
  storage/config discovery, generated paths with spaces, mocked submission/
  transfers/sync/results, mismatched/old helper failures, helper payload-root
  rejection, configuration-editor retention, and the actual helper module entry point with a local fake Slurm executable. The missing `sacct` mock is fixed;
  default test fixtures reject unmocked process/network access.
- **Remote development isolation:** deferred; all current tests are local mocks.
- **Promotions or migrations during this refactor:** none performed.
- **MVP0.3 validation:** 245 full offline tests passed; 13 focused client/context
  tests passed after final updates. Exact selected definitions survive competing
  drafts; client validation covers missing input, incomplete and incompatible
  shards. The installed standalone client produces matching single and reduced
  summaries. See [the client recipe](../agent/01_client_workflow.md) and
  [reference application](../examples/reference_client/README.md).
- **MVP1 validation:** 270 full offline tests passed in 2.27 s, with five expected
  timestamp-collision warnings; report `.development/test-runs/mvp1-final.xml`.
  Shared project/results/working-directory mapping, preview, invalid inputs before
  scheduler effects, activation failure, one remote root probe and batched
  preflight, and saved local/remote artifact lookup verified. Stable baseline
  HEAD/import/source and zero non-dot runtime files reverified; persistent stable
  and development config files remain absent. See
  [the MVP1 design](design/MVP1_paths_and_selection.md).
- **MVP2 validation:** 295 offline tests passed in 2.62 s; 28 expected timestamp
  collision warnings. Report `.development/test-runs/mvp2-final.xml` covers
  incremental execution receipts, partial/uncertain outcomes, exact read-only
  refresh, capability/replay guards, known-ID preservation, cleanup protection,
  shell syntax and environment exports. CLI receipt help and agent context
  verified. Stable baseline source/import/runtime remain unchanged; both
  persistent configuration files remain absent. See
  [the MVP2 design](design/MVP2_submission_safety.md).

- **MVP3 validation:** 313 offline tests passed in 3.87 s; 29 expected timestamp
  collision warnings. Report `.development/test-runs/mvp3-final.xml` covers
  shared terminal/Python/ACP task evidence, canonical IDs/reasons/exit codes,
  exact local receipt overlays, missing/failed/stale observations, saved
  producing-path bounded remote log tails, growing/replaced/truncated logs,
  query batching and cached no-network reads. CLI help/agent task-context and
  documentation links verified. Base Conda still imports the baseline source;
  stable code/tests/runtime and both absent persistent configs are unchanged.
  See [the MVP3 design](design/MVP3_shared_inspection.md).

- **MVP4 validation:** 333 offline tests passed in 3.22 s; 39 expected timestamp
  collision warnings. Report `.development/test-runs/mvp4-review.xml` covers
  shared preparation, preview parity, copied definitions/resolved paths,
  unchanged scripts and scheduler dependency arguments in both lanes; explicit
  operation stages and dispatch phase errors; initial and final storage failures
  and interrupted persistence after known acceptance. All prior scientific and
  inspection cases remain passing. Stable source/import/runtime and both absent
  persistent configs are unchanged. Documentation updates stay in development.
  See [the MVP4 design](design/MVP4_submission_boundaries.md).

## Current implementation verification

- **MVP5, 2026-11-12:** 366 offline tests passed in 3.15 s; 39 expected snapshot
  collision warnings. Report `.development/test-runs/mvp5-final.xml` covers
  collection/projection/cache/artifact boundaries, invalid records and producing
  metadata, malformed cache structures, cache-write evidence retention, bounded
  remote decoding, cached no-network/task identity and all previous scientific,
  submission, terminal and agent workflows. Daily/base and isolated test imports
  remain the main dev source. Baseline source and both persistent runtime roots
  remain unchanged. No dependency installs, cluster access, migration or push.

- **MVP6, 2026-11-12:** 392 offline tests passed in 3.27 s; 39 expected snapshot
  collision warnings. Report `.development/test-runs/mvp6-final-reviewed.xml` covers shared
  atomic writes, serialization/interruption/publication failures, exclusive snapshot
  collision races, batch append, configuration/file-transfer ownership, saved
  profiles/key paths, staging/copy failures, no-process local operations, explicit
  exports and all prior science/CLI/ACP/submission/inspection workflows. Seven
  bugs were reproduced before fixes; 26 cases added. Base import/help still uses
  main dev source. Clean rollback HEAD and absent configs/empty runtime directories
  verified in main/test/rollback roots. No dependency, remote, migration or push work.

- **MVP7.0c, 2026-11-12:** 405 offline tests passed in 3.22 s, 39 expected
  warnings. Report `.development/test-runs/config-reviewed.xml` covers canonical
  config modules/command, two scientific roots, merged input/cwd/output mapping,
  recorded software/data locations, explicit/no-network legacy profile edits and
  saved historical paths. No base reinstall: `asl config` and the older installed
  command work immediately; `autoslurm-config` is declared for future installs.
  Git/software preparation remains unimplemented. No config or user data migrated;
  baseline source and persistent runtime roots remain unchanged. Main config was
  already present before this task (mtime 2026-11-12 11:17:16 local; baseline tests
  began 11:43:57); it was preserved, not migrated. Test/rollback configs remain
  absent, and jobs/scripts/logs/receipts/observations are empty in all three roots.

- **MVP7.0d, 2026-11-12:** 427 offline tests passed in 3.23 s, 39 expected
  warnings, report `.development/test-runs/ssh-alias-final.xml`. Current profiles,
  overrides and new run transports use ssh_alias only. SSH config owns host/user/
  identity options; historical explicit transports remain readable. Main profile
  rusty now selects alias rusty, matching its existing local SSH Host entry. User
  requested this local config edit; all non-connection fields verified unchanged.
  Original config SHA `3b9c7feed9c8508d61265f339e634812219cefef519042424ff2900f893a369a`;
  backup `.development/backups/pre-ssh-alias-20261112-121325/config.json` (mode 0600).
  Updated config SHA `b07fe4e437dac32607fb95b4e303d5e7d76dea07234e3705cf9b05e7acd39914`.
  SSH config and baseline source/state unchanged. No cluster access or installs.

## Current local commands

```sh
# Daily use: base Conda's installed commands now import the main dev checkout.
asl --help
autoslurm --help

# Development tests: same source, isolated dependencies and state.
/Users/aadam/Projects/autoslurm/.development/python -m pytest -q /Users/aadam/Projects/autoslurm/tests

# Retained baseline source and its own default root.
/Users/aadam/Projects/autoslurm/.development/stable-asl --help
```

Edit the main checkout on `dev`. Do not continue implementation in the retained
`.development/checkout` snapshot or modify the baseline rollback worktree.
Prepared remote helpers/application environments must still be identified before
any separately authorized cluster operation. One bundle targets one selected
machine. Store nonsecret paths/identities, never credential contents.
