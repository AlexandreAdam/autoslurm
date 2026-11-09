# M0 Interaction mapping and regression coverage

## Status

**Superseded**, 2026-11-09, by [MVP0](MVP0_safe_development.md). This historical
proposal is retained with its original task/decision IDs; it is not an active
implementation gate. Tasks M0.0-M0.4 are in the
[archived roadmap](../archive/PLAN_before_mvps.md), with M0.0a-M0.0b added before M0.1. M0.0a drafts the
interaction and documentation requirements; M0.0b reviews them before backend
design. M0.1 reviews the baseline decisions below. Application code has not
changed as part of this proposal.

## Problems

| ID | Problem | Evidence or investigation | Destination |
|---|---|---|---|
| P1 | Existing tests often patch particular helpers, making it hard to distinguish a refactor from a behavior regression | Inspect fixtures and patch sites in `tests/unit` and `tests/integration` | M0, M1 |
| P2 | A bulk submission error triggers a blanket legacy retry, including errors after scheduler acceptance | `src/autoslurm/job_runner.py`, remote bulk exception handler | M2 |
| P3 | Existing local logs are excluded from subsequent transfer, even when remote logs grow | `src/autoslurm/sync.py`, `--ignore-existing` | M3 |
| P4 | Status and logs query and interpret array identity separately | `status.py`, `array_status.py`, `experiment_context.py` | M3 |
| P5 | The supported development environment and actual test baseline have not been established for this refactor | Packaging declares Python >=3.8, uses newer standard-library/type features, and CI covers 3.9-3.11; test dependency installation differs between packaging and CI | M0.2 |
| P6 | Existing refactor docs have broad phases but no sequential task record or acceptance trail | Previous roadmap and strategy | M0.0 |
| P7 | Agent docs focus on commands/internals without a complete client integration or recovery journey | Initial audit in the agent documentation design | M0.0a-M0.0b and each implementation slice |
| P8 | Editable installation and the current user guide do not establish a usable pip distribution or the human reading path | Source-relative agent resources/storage; packaging metadata and existing docs need artifact/build checks | M0.2, M1, M4, M6 |
| P9 | Application path bases and machine resolution are implicit and duplicated | `job_to_slurm.py` normalizes output/declared paths under a results base; `remote_fs.py` resolves results separately; both pass absolute values through | M1 path contract, M2 execution, M3 retrieval |

P2 and P3 are code-reading findings; regression tests must establish their
observable effects. A reported failure is not automatically a confirmed defect.

## Decisions

### D1 Baseline before structural changes

**Proposed.** Record the current unit and integration results, dependency
versions, Python version, and failures before moving application code. Check
test isolation before running the full suite. Repair a broken test harness in
an identified task, separately from functional changes.

*Check:* another session can reproduce the recorded baseline with documented
commands and no production files or cluster access.

### D2 Preserve useful behavior and specify corrections

**Proposed.** Characterize bundle creation/selection, dependency order,
submission metadata, array progress, log identity, and CLI selection. Normalize
incidental timestamps, temporary paths, and color when needed. Do not freeze
every printed byte or turn an existing defect into a compatibility promise.

*Check:* each fixture has a stated expected result; behavior corrections have
their own regression case and destination milestone.

### D3 Plain fixtures and replaceable external commands

**Proposed.** Use small JSON bundles, scheduler command outputs, and log files
that remain understandable without importing legacy classes. Cover single
jobs, dependency graphs, mixed array outcomes, and repeated bundle snapshots.
Use the existing test suite where useful; add a fake-command boundary where
necessary rather than creating a second general execution framework.

*Check:* workflow tests verify public outcomes and detect wrong dependencies or
log mappings even if internal function names change.

### D4 Track failures honestly

**Proposed.** For a confirmed current bug, use a strict expected failure linked
to the problem and future task. A fix removes the expected-failure marker and
must make that case pass. Keep ordinary passes and known exceptions distinct.

Failure cases include acceptance followed by transport loss, partial DAG
submission, malformed remote responses, growing logs, absent accounting, and
logical/raw array IDs. Fixtures alone cannot prove real Slurm behavior.

*Check:* the baseline lists exact failures and expected failures; an unexpected
pass fails the test run so a resolved bug cannot remain hidden.

### D5 Keep initial scope small

**Proposed.** M0 establishes evidence and contracts without moving production
modules, selecting a new workflow backend, introducing a database, or preparing
cluster packages. Keep the existing AutoSlurm legacy policy: preserve replaced
implementations at explicit boundaries. Gaia's workflow does not imply adopting
its policy of deleting old names immediately.

*Check:* M0's code changes are limited to the harness and tests, apart from
separately identified fixes needed to make baseline collection possible.

### D6 Derive contracts from interactions

**Proposed implementation of the agreed interaction-first approach.** Review
[I00-I16](../interaction-map.md) before choosing types, modules or persistence.
For each interaction, settle outcomes, durable evidence, failure semantics and
the next action; map it to a milestone, a recipe and a validation trace. Use the
dependencies between interactions to revise the implementation order.

*Check:* M0.0b records the user's review and any amendments; M1 designs explain
which interactions their contracts serve. A new agent can rediscover work
without relying on a previous chat, display index or private storage path.

### D7 Design documentation and distribution with the interface

**Proposed.** Follow the [agent documentation design](../agent-documentation-design.md)
and [human documentation and distribution design](../documentation-and-distribution-design.md).
Teach client software practices as well as operations. Build a small reference
client and keep examples aligned with supported contracts in each slice.
Human docs explain purpose, concepts, workflows and failure interpretation;
the detailed agent interface is supported and versioned rather than an invitation
to depend on private internals.

*Check:* recipe and example checks cover new-session tracking, uncertain
submission, failed-task diagnosis and recovery. Artifact installation outside
the source tree and versioned documentation become release requirements. No
future operation is advertised as an implemented feature in installed docs.

## Open questions

- **Q1 Minimum Python version:** what should the new supported range be?
  M0.2 gathers the actual constraints; settle the packaging/CI policy before
  implementing new contracts in M1. No requirement to retain a broken promise.
- **Q2 Regression contract:** which current command outputs do existing scripts
  parse? During M0.1, identify any known consumers; preserve documented selectors
  and semantic fields while leaving table spacing outside the compatibility
  contract unless evidence requires it.
- **Q3 Real cluster validation:** which configured cluster and small workload
  should exercise M5? This does not block offline M0 work. Live execution and
  package changes are outside the planning task.

## Forward constraints

- **M1:** tests must exercise draft/run identity and legacy bundle loading
  without selecting a storage implementation in advance. Reviewed interactions
  and client practices constrain those contracts; runtime/resources must work
  outside an editable source checkout.
  Include T13: relative definitions, explicit bases, selected-machine roots,
  execution working directory, and historical resolved locations. Do not depend
  on a submitting agent's current directory or split one run across machines.
- **M2:** record partial success before testing retries. Treat a missing receipt
  as uncertainty, not proof that Slurm rejected a job.
- **M3:** fixtures need observation timestamps, raw/logical array identity,
  changing logs, and incomplete query results.
- **M4:** both presentation interfaces need the same semantic reference cases;
  human and installed agent guides share the same checked examples/contracts.
- **M5:** retain a compact array-and-reduce scenario suitable for real cluster
  validation, including failed tasks and selected result retrieval.
- **M6:** wheel/source installation and documentation publication checks must
  validate the built artifacts, with no source-tree imports/resources or writes
  inside the package installation.

## Log

| Date | Event |
|---|---|
| 2026-11-09 | M0 proposal opened; Gaia planning workflow adapted while preserving AutoSlurm's legacy policy and offline compute constraints |
| 2026-11-09 | Interaction-first planning added at the user's request; drafted I00-I16, client integration practices, documentation audit, human reading path and pip release criteria; review is M0.0b |
| 2026-11-09 | User clarified relative application paths and AutoSlurm-owned machine discovery; added the path contract and T13 while keeping one selected machine per run |
