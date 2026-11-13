# AutoSlurm agent documentation design

## Purpose and status

**Draft for review, 2026-11-09.** Redesign `agent/` around
[the interaction map](interaction-map.md). The documentation serves an agent
building a client application as well as an agent operating existing jobs.
It is part of the interface contract and evolves with each implemented slice.

This is the full-product design. The [MVP plan](../PLAN.md) now ships a short
accurate integration/operation recipe first, adds structured inspection in
MVP3, and defers complete documentation packaging and reference coverage to L3.
An early release does not have to implement every layer or recipe below.

The repository's AGENTS.md/CLAUDE.md govern development of AutoSlurm itself.
They are distinct from the installed guidance that client agents obtain through
AutoSlurm's context tools. Neither should require knowledge of private backend
modules to use the package correctly.

## Documentation entry and retrieval

### Accepted client argument preference (2026-11-13)

Alexandre explicitly requires readable, individual named job arguments, typed CLI
commands per job kind (Typer preferred), and a flat scalar `script_args` mapping.
Opaque base64/JSON/config-file configuration payloads are to be replaced. Lists
use one comma-separated scalar, booleans default to off, and strings stay single
shell-safe words under the current renderer. Client builders validate actual CLI
signatures, required/unknown options, types and unsafe values before saving or
submitting. This is a lasting preference for integration, bundle generation and
client reviews. The [current client recipe](../agent/01_client_workflow.md#explicit-named-job-arguments)
and [bundle recipe](../agent/10_task_schedule.md) carry the operational contract;
AGENTS.md carries the contributor reminder. Recording this policy changes no
renderer/validator or saved data. Other proposed designs below remain proposals.

### Context discovery

An agent starts with a short orientation: what AutoSlurm owns, capability and
version discovery, the choice between integrating an application and operating
a run, and how to request the next recipe. Do not make a full source-code map
or all historical examples the default context payload.

Use stable recipe identities for context selection. Define how the installed
package includes its own version-matched docs, examples, and schema; retrieval
must not depend on a source checkout beside the installation. Specify missing
recipe and incompatible-version behavior. Adapt existing context/ACP selectors
at a documented boundary instead of silently changing their meaning.

## Proposed documentation layers

Names below identify topics, not final filenames or new CLI commands.

| Layer | Content | Main interactions |
|---|---|---|
| Start | Ownership, capabilities, exact run selection, cached versus refreshed state, how to load a recipe | I01, I08, I16 |
| Integrate an application | Entry point, config/arguments, local smoke check, paths, environment, resources, task partitioning, result/error contract | I02-I05 |
| Build a workload | Single job, sweep, array, map/reduce, output ownership, scientific metadata | I04-I05 |
| Prepare and submit | Machine readiness, code checks, execution preview, acceptance receipts, partial outcomes | I03, I05-I06 |
| Resume and monitor | Rediscovery, refresh scope, array/task identity, status age, logs and artifact references | I07-I10, I16 |
| Diagnose and recover | Evidence-based failure explanations, cancellation, retry preconditions, checkpoint semantics, reduce dependencies | I11, I13-I14 |
| Retrieve and retain | Result filters, completion markers, validation ownership, history retention and cleanup | I12, I15 |
| Reference | Supported public schemas, errors, version compatibility, capability matrix and migration notes | All |

Resource guidance teaches allocation/thread coordination and measurement; it
does not prescribe fixed CPU/GPU ratios or small array limits for every study.

## Required recipe structure

Every operational recipe must answer:

1. **When to use it:** intent, scope, and required installed capability.
2. **What to supply:** exact selectors, required context, and preconditions.
3. **What happens:** local reads, remote checks, file writes, and scheduler effects.
4. **What comes back:** stable references, outcomes, observation times, warnings,
   and bounded evidence. Explain which fields may be unknown.
5. **How to interpret failure:** rejected, partial, uncertain, stale, and failed
   computation have distinct meanings.
6. **What to do next:** supported follow-up operations with their preconditions;
   repeatability, reconciliation, cancellation, or retry implications.
7. **Minimal worked case:** supported request, expected response shape, and at
   least one relevant failure/recovery path.

Examples use current public operations. Proposed fields and behavior stay in
design documents until implemented. Public machine-readable contracts, CLI
help, recipes, and capability discovery must agree; no hand-maintained parallel
schema that drifts from validation.

## Client integration recipe requirements

Provide a minimal reference client with an installed command and a local smoke
case. It must illustrate the practices in the interaction map: reproducible
partitioning, explicit resources and thread limits, portable paths, unique
outputs, nonzero failures, result completeness, scientific metadata, and saving
returned run identities. Add array/reduce and failed-task recovery cases as the
corresponding features land.

The guide should make responsibility boundaries clear: application checkpointing
and scientific validation stay in the client; AutoSlurm tracks execution and
retrieval. Show how a client can integrate with little glue, without importing
submission internals, rewriting Slurm scripts, parsing presentation tables, or
reading private index files.

The client agent should leave its project a small integration note containing
the entry point, supported workload forms, input/output and environment contract,
local smoke command, scientific success checks, and links to saved AutoSlurm run
references. It must not copy the whole AutoSlurm manual into that project.

Teach the [relative path contract](target-architecture.md#application-path-contract)
explicitly: the application supplies relative paths and declares their bases;
AutoSlurm discovers machine roots. No application hostname branches or hard-coded
absolute mount prefixes. The guide must explain working directory, declared path
arguments, previewed resolved locations, and why old attempts retain their actual
locations after configuration changes. Examples use one machine per run; showing
the same definition under another profile does not imply multi-machine routing.

## Agent response and handoff requirements

Design structured operation outcomes around the information needed to continue:
selected definition/run/attempt/task references; per-item outcomes; scheduler
identity when known; observation time/source; errors with evidence; artifact
references; and supported next actions. Exact fields are settled with their
service contracts, including compatibility/versioning.

Distinguish authoritative reasons from inferred explanations. Keep log output
bounded with a retrieval reference/continuation. An agent must be able to find
the record after a context reset and identify which observation is stale. Do
not return success for a request merely because one of several jobs succeeded.

## Rollout and acceptance

| Work | Completion evidence |
|---|---|
| MVP0 | Small accurate recipe identifies the stable/development lane, supported operations and exact selection; review only blocking interactions |
| MVP1 | Relative paths/bases, machine discovery and the shared selection rule have one checked client example |
| MVP2 | Submission and per-job environment recipe shows known, partial and uncertain outcomes; uncertainty stops rather than automatically recovers |
| MVP3 | Fresh-session rediscovery, array/log evidence, observation age and bounded structured inspection agree with terminal output |
| MVP4 optional | Filtered retrieval recipe uses the recorded producer paths and does not resubmit compute |
| L1-L2 later | Richer state, automatic reconciliation and failed-task/reduce examples are documented when implemented |
| L3 later | Complete installed recipe/schema delivery, capability coverage, generated references and versioned packaging |

Small public recipes land alongside their operations. Use the human
guide and distribution requirements in
[the documentation and distribution design](documentation-and-distribution-design.md)
for audience boundaries, installed resources, and release checks.

Use contract tests and a deterministic reference-client walkthrough to validate
the guide. Useful evaluation questions are: can a new agent find the right recipe,
prepare a client without private APIs, identify every accepted/uncertain task,
explain a failure from evidence, and resume after losing chat context? Optional
model-based trials can reveal missing guidance, but they do not replace tests.

## Initial audit of current material

This is a code-reading audit, not a claim that examples have been executed.
Audit decisions become concrete edits as the corresponding public operations
are implemented; correct misleading current claims before reusing the material.

| Current material | Treatment | Reason and destination |
|---|---|---|
| `agent/01_context_overview.md` | Replace | Start with tasks, ownership and capabilities instead of a source-file reading list; I01 |
| `agent/02_llm_interface.md` | Replace | Separate implemented ACP actions from future tools; define installed-version context and public response contracts |
| `agent/03_experiment_context.md` | Correct and split | Distinguish bounded inspection, refresh side effects, and context handoff; I09-I11/I16 |
| `agent/04_project_map.md` | Replace as default context | It mixes public operations with private helpers and stale config/storage assumptions; keep a contributor map separately |
| `agent/05_cli_reference.md` | Correct from parser/help | It advertises pre-command and job-name flags that differ from the current schedule parser; do not duplicate help manually |
| `agent/06_resource_rules.md` | Replace prescriptions with principles | Fixed CPU/GPU ratios, time limits and array sizes are examples rather than universal workload policy |
| `agent/07_acp_actions.md` | Retain verified action concepts | Derive supported payload and response references from the actual dispatch/schema |
| `agent/08_examples.md` | Replace with checked recipes | A scheduling example claims scripts are rendered immediately; a training loop omits required time; remote paths/config claims need correction |
| `agent/09_task_inspect.md` | Replace | Refresh and repeated inspection claims need explicit cached/live semantics and stable task identity |
| `agent/10_task_schedule.md` | Expand into client integration and workload recipes | Relative paths need explicit bases and shared machine resolution; the current project-prefix convention must not become an implicit requirement; add installed commands, partitioning, errors, outputs and provenance |
| `agent/11_task_submit_monitor.md` | Replace | Clients should declare dependencies through the public contract rather than edit generated scripts with internal helpers |
| `agent/12_task_acp_reference.md` | Retain concise reference role | Keep it aligned with implemented actions; separate protocol versioning and task context |
| `agent/schema.json` | Reconcile with validation | It is a reference schema without an established versioned validation boundary; fields such as pre-commands must match actual supported behavior |
| `agent/examples/` | Audit and retain useful scenarios | Execute minimal single-job, dependency and array examples against fake adapters and the reference client |
| `src/autoslurm/acp_action.json` | Reconcile with dispatch | The four documented actions do not cover every operational interaction; expose supported capability coverage explicitly |
| Context packaging and selectors | Redesign | `context.py` finds `agent/` relative to a source-style root; installed wheels need version-matched resources; selector behavior must be explicit |

Specific current evidence: `storage.py` resolves `config.json` under its storage
root, rather than the `~/.autoslurmconfig` path described in several pages;
`apps/schedule.py` renders no scripts until submission and requires `--time`;
`apps/agent_context.py` prints help with no arguments, although several pages
describe a no-argument documentation dump. These discrepancies belong in the
baseline and documentation corrections, not in the new behavior contract.

## Open design choices

- Public request/response versioning and the relationship between CLI JSON,
  Python API, and existing ACP actions.
- Stable recipe selectors and explicit task-context selector changes at
  promotion boundaries; no blanket compatibility promise during development.
- Required versus optional application metadata and result manifests.
- The first reference-client workload and how to keep it small and generic.
- Which current documentation assumptions need immediate corrections before
  any new backend behavior is available.

Use the audit to correct the pages needed by the active MVP. Full recipe
coverage, new commands and all later schema decisions are not prerequisites for
the first fixes. Keep future capabilities clearly identified as unavailable.
