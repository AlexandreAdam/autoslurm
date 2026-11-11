# MVP0 Safe development and a small baseline

## Status

**Active**, opened 2026-11-09. The working rules are established in
[WORKFLOW.md](../../WORKFLOW.md); installation/root implementation details below
remain proposed until verified and settled in their task. The rules-only step
MVP0.0a, local baseline MVP0.1 and isolation MVP0.2 are complete; MVP0.3 remains in
[PLAN.md](../../PLAN.md). The preceding M0 design is superseded; its detailed
full-product decisions are not prerequisites for starting an MVP.

## Problems

| ID | Problem | Small response |
|---|---|---|
| P1 | Daily jobs need the current package while development may break APIs/formats | Pin stable code/environments; develop separately and promote tested increments |
| P2 | Storage defaults to the source-style package root; original override was process-local | Add one explicit supported development root selector; preserve the stable default |
| P3 | Workstation and remote helper can discover different storage or versions | Record both lanes' code/helper/root identities and reject ambiguous development configuration |
| P4 | A broad baseline/rewrite could delay the first useful fix | Record fast tests and one small existing workflow; add focused regressions per MVP |
| P5 | Agents need accurate guidance before the full documentation redesign | Ship one short supported integration/operation recipe with exact selection and uncertainty limits |

Actual installation evidence belongs in
[the installation register](../installation-register.md). The local editable
installation and separate local development lane are verified. Initial operating guidance exists in
[agent/00_operating_rules.md](../../agent/00_operating_rules.md); MVP0.3 remains
open until it is grounded in the verified setup and smoke fixtures.

## Decisions

### D0 Local-only execution

**Accepted, explicit user instruction, 2026-11-09.** Develop locally and mock
Slurm and remote transport. No cluster discovery, SSH, live jobs or remote
package changes. References below to real helpers/remote roots describe the
eventual deployment design; current acceptance checks use local fake commands.
Real cluster compatibility remains unverified until a later authorized check.

### D1 Two isolated release lanes

**Implemented locally in MVP0.2.** The original checkout is retained at detached
baseline HEAD, with its existing base Conda environment and tracking root.
Development is a Git worktree on `codex/mvp0-isolation` under `.development/checkout`,
with separate `.development/venv` and `.development/state` locations. Exact paths
and import evidence are in the installation register. No stable package reinstall,
root move or new-run promotion was performed. Remote deployment remains proposed:
a stable pinned checkout/environment continues managing existing
production jobs. A separate development checkout/environment uses distinct local
and remote config/job/script/log roots plus a separate test result namespace.
The application environment referenced by queued jobs is not upgraded in place.

*Check:* record the actual code, helper and state roots before implementation;
an isolation smoke case cannot touch production even if the default configuration
points there. This task does not create a new deployment service.

### D2 One root selector before development writes

**Implemented in development in MVP0.2.** Root discovery has this precedence:

1. Process-local `set_storage_root(path)` override.
2. `AUTOSLURM_STORAGE_ROOT` environment variable.
3. Existing package-root default, unchanged when no selector is supplied.

Explicit roots must be nonempty absolute paths; local `~` expansion and physical
path resolution occur through storage discovery. `set_storage_root(None)`
clears only the process override. An environment-selected root never loads the
old `src/config.json` fallback. Both local wrappers set the same environment
selector; new processes do not need to rediscover it from the current directory.

For remote development, machine `storage_root` selects an absolute POSIX root
and takes precedence over legacy `path`. One shared resolver serves script
preparation, transfer, submission, sync and default results. It probes the
configured environment with the selector, requires helper selector support and
an exact root response, and rejects errors/mismatches before submission. Bulk
execution receives the same selector; both caller and helper reject a payload
script directory outside the selected root. This is a root compatibility check,
not full package/protocol version negotiation. Only mocks were exercised.

With a local environment selector, generated log paths use the selected local
root rather than a legacy machine `path`. Default relative results follow it;
declared path arguments and generated output directives quote roots with spaces.
Explicit application output paths, custom Slurm output directives and configured
`results_root` remain operator-owned destinations, not rewritten or sandboxed.
Keep them separate in development. General application path policy remains MVP1.

*Check:* temporary-root tests cover configuration, bundles, scripts and logs;
the remote probe/submit/transfer paths agree on the selected root. Use a distinct
results subtree for mocked workflow checks. No broad storage migration is included.

### D3 Pin and promote rather than preserve every intermediate interface

**Proposed.** Keep format changes small early. Breaking APIs/formats can ship at
an explicit MVP promotion boundary; old live jobs and their mutable records stay
with the submitting stable installation. Retain it for rollback and inspection.
Use read-only fixture copies for development. Never copy a submission and then
treat it as new work to launch.

*Check:* a promotion checklist identifies old/candidate lanes, new-run routing,
in-flight job ownership and rollback handling of candidate jobs. A general old
data importer and compatibility framework remain later work.

### D4 Minimum evidence for the first release

**Proposed.** Record current fast tests, dependencies and one cheap smoke
scenario. Add targeted tests when changing a shared rule or fixing a confirmed
defect. Retain existing useful tests; do not build a new comprehensive fixture
framework before fixing paths or submission fallback.

*Check:* baseline passes and existing failures are reported separately. Default
tests cannot contact the cluster or write production. A narrow wheel smoke
check is part of promotion; broad release matrices and publication are later.

### D5 Accurate minimal agent guidance now

**Proposed.** One brief recipe identifies the installed lane/version, declared
relative paths, supported public operations, exact bundle selection, and what
to do with partial/uncertain outcomes. Extend it with each supported MVP.

*Check:* a new session can select the smoke run without parsing table positions
or guessing private paths. The recipe does not claim automatic interrupted-
submission recovery, full offline state, or scientific retry support yet.

## Open questions

- Remote inventory, real helper deployment and real cluster validation are
  deferred by local-only scope; no configured remote development lane is implied.
- Which tiny installed application command should become the reference client?
  The existing three-job fixture supplies the first mocked submission baseline;
  no scientific application or live job has been run.

## Local baseline (MVP0.1)

Recorded 2026-11-09 against source revision
`33bcbd34fb167fca67aa64739a013073c64167b1`. No application code, tests,
packaging configuration or current installation was changed. Planning and agent
documentation changes remain uncommitted; this reference identifies the existing
engine, not a committed snapshot of the new documentation. No commit/tag,
deployment, migration or cluster access was performed.

The user-installed base Conda package is editable version 0.1.0, importing this
checkout with Python 3.14.7. Its resolved storage root is the checkout and its
`config.json` is absent. There are no non-dot files in `jobs/`, `slurm/` or `out/`.
These are observations of this installation, not evidence about existing remote
jobs. See the installation register for exact paths.

### Test environment and results

A disposable environment was created at
`/private/tmp/autoslurm-mvp0-baseline-yu9x4_8t/venv`. It reads the current source
without installing or changing the base Conda package. Dependencies came from
existing local wheel cache using `pip --no-index`; no download completed.
Relevant versions: Python 3.14.7, pytest 9.2.0, Typer 0.27.3, Click 8.5.0.
The full optional test extra was not installed; these checks did not need
pytest-mock or coverage.

| Check | Result | Scope |
|---|---|---|
| Existing unit suite, `tests/unit` | 195 passed in 0.99 s | Shared logic, CLI, storage and mocked command behavior |
| `tests/integration/test_job_runner.py::test_integration_schedule_jobs` | Four parametrized cases passed in 0.08 s | Save a three-job dependency bundle, generate scripts, submit through mocks and compare expected script lines |
| Final runtime guard | Zero blocked operations in both runs | Real child processes/network prohibited; file mutations restricted to scratch |
| Source/packaging comparison with HEAD | No diff in `src/`, `tests/`, `pyproject.toml` | Existing engine and test code retained |

The smoke cases cover the existing local/remote-shaped machine dictionaries;
their external commands are mocked and no generated workload is executed.
They establish a small behavior reference, not scheduler or scientific validity.
The full integration suite, wheel installation, other Python versions and real
cluster behavior were not tested.

### Offline test gap and reproduction

The first guarded unit run passed all 195 assertions but attempted one real
`sacct -n -P -j 123 -o JobID,JobIDRaw` probe. The guard blocked it before process
creation. The call came from
`test_latest_log_accepts_array_task_log_for_saved_slurm_id` in
`tests/unit/test_experiment_context.py`; its accounting probe has no explicit mock.
The final run used a wrapper simulating absent `sacct` with `FileNotFoundError`,
and all 195 tests passed with no blocked operations. This is a test-isolation gap,
not a demonstrated product failure. Make it explicit in the default fixtures in
MVP0.2 rather than relying on the host having no Slurm installation.

For reproduction, use an isolated environment with the versions above, expose
`src/` and the repository root on the Python import path, disable bytecode/plugin
autoload/pytest caching, set storage to a temporary directory before collection,
and give pytest a fresh temporary `--basetemp`. Run `pytest -q tests/unit` and
the exact smoke selector above. Retain the `sacct` absence mock and block real
process/network activity until the default fixture gap is fixed. Do not run
an unguarded baseline against a configured installation.

The temporary runner, console reports, JUnit XML and guard reports are under
`/private/tmp/autoslurm-mvp0-baseline-yu9x4_8t/`; they are disposable evidence,
not a persistent development environment or a required repository path. This
section preserves their results when temporary files are cleaned up.

## Local isolation validation (MVP0.2)

Development was installed editable into its own virtual environment entirely
offline, using cached build/test wheels. An invocation outside either checkout
confirmed its interpreter/import/state paths; base Conda independently confirmed
the stable import/root. The original checkout was detached at baseline HEAD
without changing application code, environment, configuration or tracking files.
The `.development/` directory is ignored. Working documentation is mirrored in
the original checkout for discoverability; implementation lives only in development.

The full offline suite passed **238 tests in 1.21 s**. Added cases cover root
precedence/reset and invalid selections, absent selected config, two fresh
processes sharing configuration/bundles/scripts/logs/results from another current
directory, and an executed local fixture preserving a path with spaces. Mocked
remote cases verify common roots across submit/transfers/sync/result lookup,
rejection of unsupported or mismatched helpers before submission, payload-root
validation and preservation of selection through configuration edits.

Default test fixtures now reject unexpected process creation and Python network
access with test failures; a few explicitly marked fixtures may execute reviewed
local Python/Bash programs. Slurm, SSH and transfer commands remain mocked.
Storage overrides/environment are restored per test. The baseline's unmocked
`sacct` probe now has an explicit unavailable-accounting mock.

An actual module-entry-point check exposed an existing defect hidden by direct
function mocks: `python -m autoslurm.apps.bulk_submit_driver` never called `main`.
The module now invokes it. A fresh-process test places a local fake `sbatch`
on PATH, verifies the accepted job ID and exact selected script path, then checks
that a mismatched payload fails without another fake submission. No scheduler
or network service is involved.

Test report: `.development/test-runs/full-3.xml` under the original checkout.
Reproduce with the development Python wrapper and `-m pytest -q tests` from the
development checkout. Neither real cluster compatibility nor scientific validity,
wheel-resource packaging, automatic deployment or uncertain-submission recovery
was established. MVP0.3's reference-client recipe remains open.

## Forward constraints

- **MVP1:** reuse the current bundle shape; centralize existing path/machine/
  selection policies, including a clear working directory and input availability.
- **MVP2:** a small incremental receipt plus explicit uncertainty is enough to
  prevent blind retries. Automatic adoption/resume is not implied.
- **MVP3:** share one resolved task/state/log view and query results; a complete
  new persistent index or status database is not required.
- **Later layers:** publication, complete provenance, broad migration and
  failed-shard/reducer automation must not expand the first MVP acceptance.

## Log

| Date | Event |
|---|---|
| 2026-11-09 | User requested short usable increments, priority on paths/shared core rules/reliability/agents, intentional breaking changes and a way to keep daily use working |
| 2026-11-09 | At the user's request, established working rules before setup: shared procedure, unverified installation register, agent operating entry guide and explicit commit-versus-promotion boundary; no runtime setup performed |
| 2026-11-09 | User required local work with mocked Slurm and installed the editable package in base Conda. Verified the local baseline: 195 unit tests and four mocked dependency-submission cases pass; recorded the accounting-mock gap and retained isolation as the next task |
| 2026-11-10 | MVP0.2 implemented local code/environment/state separation and explicit storage selection with mocked helper checks. Full offline suite: 238 passed, including the real module-entry-point check with fake Slurm. Stable source pinned at detached baseline HEAD; no cluster access or promotion |
