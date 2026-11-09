# Target Architecture

This document describes the intended internal model for the refactored
AutoSlurm stack.

This is architectural direction for review. [PLAN.md](../PLAN.md) owns the
MVP releases; [milestone designs](design/README.md) settle exact contracts and
implementation choices. This describes the fuller product, not a mandatory
first-release decomposition. Terminal and agent interfaces use shared operations.

Early MVPs keep existing bundle shapes, centralize rules in the working code,
add only needed metadata/receipts, and share one task/state view. A new database,
complete record hierarchy, full persistent index, automatic recovery and general
migration are later layers. Stable and development installations have separate
environments and mutable state; see PLAN.md for promotion/rollback.

The responsibilities below are provisional. Use
[the interaction map](interaction-map.md) and the
[agent documentation design](agent-documentation-design.md). Derive the backend
contracts and their implementation order from the interactions needed by each
MVP. Full-product review is not a gate on a targeted fix or shared extraction.

## Design Intent

The refactored system should be local-first. After a sync, the local AutoSlurm
storage should contain enough information to inspect bundles, report status, and
find logs without requiring live Slurm accounting as the default path.

## Core Internal Model

Separate a bundle definition (requested computation) from its runs and submission
attempts. Scheduler observations and output artifacts refer to those identities;
they do not rewrite the original request. Stable identities include machine
context and do not depend on a display index or a timestamp alone.

The canonical records collectively include:

- bundle snapshot identity
- job name and submission metadata
- logical Slurm job id
- raw Slurm job id
- array parent id and array task index
- job state
- log path or log-path candidates
- source/provenance of each resolved field
- requested and observed application revision, environment identity, and an
  explicit dirty or unknown status
- submission attempt outcome, accepted job IDs, and uncertainty when a response
  is lost
- observation and refresh timestamps, including failures
- declared scientific result locations and retrieval state

Store plain data and retain the current representation where useful. Introduce
new versions/migration only when required by a promoted change; a database is
not a prerequisite. Runtime storage must be independent
of package installation paths, with an explicit migration from the old layout.

## Application path contract

**Agreed direction:** client application configuration and workload definitions
always declare relative filesystem paths. AutoSlurm discovers the appropriate
roots for the selected machine and provides the execution context. Applications
do not need hostname checks, cluster mount prefixes or workstation home paths.
The narrow first resolver/working-directory contract is settled in MVP1.

Each application run/bundle executes on one selected machine. Selecting a
different configured machine for a separate run remains possible. Multi-machine
routing, cross-machine dependencies and automatic placement are outside scope.

### Path ownership

| Location | Representation and owner |
|---|---|
| Client configuration and saved workload definition | Relative paths with declared meaning/base; owned by the application |
| Machine configuration and discovery | Machine-specific absolute roots, prepared environment locations and root validation; owned by AutoSlurm/operator |
| Execution plan and attempt record | Original relative paths plus resolved machine locations and working directory; owned by AutoSlurm |
| Artifact retrieval | Producer attempt's recorded path mapping plus a selected local destination; owned by AutoSlurm |

For example, a client can declare `results/study_01/run_03`. A local profile may
resolve it under `/work/research_project`, while a cluster profile resolves it
under `/project/research_project`. The saved relative value stays the same; these
are two independent single-machine runs. Exact root names and whether different
path roles need different bases remain MVP1 decisions.

### Resolution requirements

- Declare which arguments/configuration fields are filesystem paths and what
  they are relative to. Do not rewrite arbitrary string arguments, or assume
  every path belongs under a results directory.
- Resolve from the selected machine's explicit configuration or documented
  discovery mechanism. A missing or ambiguous root is an actionable error,
  not a fallback to the agent's current directory or a guessed home directory.
- Use one policy for validation, preview, script execution, status/log lookup
  and result retrieval. Define the working directory, path normalization and
  handling of parent traversal centrally.
- Keep application-facing definitions relative. MVP1 settles whether the runtime
  contract preserves relative arguments with a selected working directory or
  materializes absolute arguments at launch. Either approach must work without
  client code discovering machine roots itself.
- Record both logical paths and actual execution locations. Inspecting an old
  attempt must not reinterpret its files using a changed default machine/root.
- Absolute machine configuration and resolved runtime evidence are valid;
  absolute paths embedded in new client definitions violate this contract.
  Preserve historical records containing absolute paths and define an explicit
  compatibility/migration path, without silently guessing their original base.

Validate this with the same relative workload under two machine profiles in
separate runs, including input/output paths, a changed current directory,
missing roots, and retrieval of an older attempt after profile changes. No test
needs to distribute one run across machines.

## Local Memory Layer

The local memory layer should be built from synced artifacts and persisted in a
machine-readable local index.

It should allow:

- status lookup without immediate cluster access
- array-task lookup from local metadata
- log lookup from local `.out` files and local mapping records
- provenance-aware fallbacks when data is incomplete

The index stores last-known observations. Slurm remains authoritative about
scheduler state. A cached running state is reported with its age; a failed query
does not erase an earlier observation or establish successful completion.

## Sync-Driven Refresh

`sync` should become the boundary between remote state and local state.

It should:

- mirror remote bundle snapshots
- mirror remote output logs
- update or rebuild the local status/log index
- record what data was refreshed and when

## Reader Behavior

Read-side commands should follow this order:

1. consult the local index
2. use local files and cached mappings
3. surface stale or incomplete state explicitly
4. use the shared refresh service when the user requests fresh data or an
   explicit live repair

Cached inspection does not initiate network access implicitly. Commands may
offer refresh or live options, with the same semantics for humans and agents.

This applies to:

- `status`
- `logs`
- `inspect`
- `clean`

## Module Direction

- One module should own bundle snapshot selection and visibility policy.
- One module should own status resolution.
- One module should own log resolution and array-task mapping.
- One module should own sync/index refresh behavior.
- CLI entrypoints should mostly parse arguments and render output.

Every service must serve an identified interaction and expose enough stable
evidence for an agent to continue after losing session context. Agent recipes
teach client integration practices as well as operation contracts; they are
part of each slice's completion criteria, not a later interface-only milestone.

## Distribution and Human Documentation

The engine is designed for agent-facing programmatic use through supported
contracts; the terminal presents the same operations for people. Human docs
explain purpose, concepts, a system map, complete examples, and how to interpret
and supervise outcomes. Private implementation detail stays in contributor docs.

Wheel and source installations must work outside the repository. Bundle
version-matched agent guidance/schema resources and keep runtime state outside
the installation. See [the documentation and distribution design](documentation-and-distribution-design.md)
for the human reading path and release checks. Storage and resource contracts
must allow this during the MVPs. Initially use a narrow artifact smoke check and
minimal accurate guides; full resource delivery, documentation publication and
release matrices belong to later layer L3.

## Submission and Environment Boundaries

Submission records partial outcomes durably. An uncertain scheduler acceptance
requires reconciliation before a retry; it must not trigger a blanket fallback
that could duplicate work. Define helper protocol compatibility and recovery
alongside the submission service.

Jobs use environments prepared before submission and do not perform package
updates or Git operations. Capture requested and observed code provenance;
verification alone does not freeze a mutable installation. Package preparation
stays manual initially. Optional environment tools can be considered later.

## Legacy Boundary

Keep the pinned stable installation and Git history as the default reference.
Retain a legacy module only for a concrete comparison/import need, and avoid
two active implementations of a shared rule. Old live jobs remain managed by
their submitting installation; incompatible development uses isolated state.
See [the legacy policy](legacy-policy.md).
