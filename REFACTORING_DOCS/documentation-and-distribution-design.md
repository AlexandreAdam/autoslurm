# AutoSlurm documentation and distribution design

## Purpose and status

**Draft for review, 2026-11-09.** Make AutoSlurm installable as a released Python
package and give people a clear explanation of its purpose, concepts, and
scientific workflows. Human documentation and
[agent documentation](agent-documentation-design.md) serve complementary roles
and share the same public behavior contracts.

This is the full-product target. Under the [MVP plan](../PLAN.md), early releases
need working development installs, a narrow wheel smoke check before promotion,
one accurate agent recipe and a short human overview. Public package release,
complete resource delivery, a polished site and broad release matrices are L3
work and do not gate daily-use improvements.

The existing project has Python packaging metadata and user documentation. The
refactor must verify a usable distribution and redesign the human experience;
neither is established merely by an editable install or an API listing.

## Audience and interface boundaries

| Audience | Main questions | Documentation emphasis |
|---|---|---|
| Scientist or operator | Why use AutoSlurm? What will run? What happened? What should I do now? | Conceptual map, representative examples, interpreting outcomes, choosing and supervising work |
| Agent developing client software | How should I structure my package so runs are portable and recoverable? | Explicit integration practices, supported schemas, reference client, local validation |
| Agent operating jobs | Which exact run/task is this? What is known? What action is safe next? | Structured operations, durable identities, evidence, failure and recovery contracts |
| AutoSlurm contributor | How do the services, adapters, persistence and compatibility boundaries work? | Separate implementation architecture, design decisions and development workflow |

The execution engine is designed for programmatic use by agents, with the
terminal as another interface to the same operations. Human readers should see
this principle early, understand what they can delegate, and know how to inspect
the result. An agent is a consumer of supported interfaces, not a justification
for treating every private Python module or storage file as a public API.

Human documentation remains sufficient for a person to install, configure,
submit, monitor, diagnose, and retrieve a small workload without an agent.
The shorter treatment of internals must not obscure operational effects or
make an agent mandatory for routine use.

## Proposed human guide

The first reading path should build understanding before presenting reference
detail. Reuse the existing documentation tooling if it can support the agreed
structure; a site-generator migration is not an initial requirement.

| Page or section | Reader outcome | Worked material |
|---|---|---|
| What AutoSlurm does and why | Understand saved work, remote execution, durable tracking, agent collaboration and the limits of the package | One annotated journey from a scientific question to a collected result |
| The system at a glance | Understand workstation, login node, compute node, prepared software, Slurm, local observations and result storage | One architecture diagram and a small glossary of definition, run, attempt, job and array task |
| First successful run | Install a supported release, configure a machine, validate a cheap example, submit, refresh and retrieve | Complete small command sequence with actual supported output and prerequisites |
| Working with an agent | Know what integration context to provide, what the agent should produce, what can be inspected, and how to resume another session | A client integration brief and a saved-run handoff; link to detailed agent recipes |
| Common scientific workflows | Recognize single jobs, parameter sweeps, arrays, dependency graphs, map/reduce and results selection | A few end-to-end examples with explicit inputs, expected outputs and resource rationale |
| Understanding a run | Read summaries, identify exact code/attempt/task, understand state age and find evidence | Annotated mixed-success array, unknown status and missing-result examples |
| When something goes wrong | Distinguish connection, submission, scheduling, application and retrieval problems | Partial submission, transport loss, failed shard and cancellation race; explain recovery preconditions |
| Installation and cluster preparation | Understand local versus remote prerequisites, supported versions, storage/config locations, offline compute and manual package updates | Workstation and login-node setup; existing environment and optional preparation tools |
| Portable application paths | Understand why applications use relative paths and AutoSlurm resolves the selected machine's roots | One relative input/output example, its working directory and resolved preview; two separate machine selections, never one distributed run |
| Reference | Look up supported commands, configuration fields, compatibility and public interfaces | Concise generated or checked references with links from examples |

Explain enough of the mechanism to support decisions: what is copied, what is
cached, when the cluster is contacted, how dependencies are satisfied, and what
a retry changes. Detailed class hierarchies and private helper inventories
belong in contributor documentation rather than the main reading path.

Explain the [relative path contract](target-architecture.md#application-path-contract)
as a central portability principle. Application configuration stays independent
of absolute workstation or cluster paths; machine profiles/discovery own those
locations. Define the base of a relative path clearly, without implying it is
always the shell's current directory. Each application run targets one machine.

## Examples as product checks

Use a small generic reference application with an installed entry point and
deterministic, cheap work. The human tutorial shows the scientific workflow;
the agent recipe shows the exact integration and response contract. Both use
the same underlying example and supported operations.

Validate examples against fake adapters first and exercise a representative
subset on the cluster separately. Keep live cluster steps labelled so a docs
build never submits jobs. Identify the software version for each example;
clearly separate supported behavior from planned features. Navigation and the
overview diagram must match the actual interactions and command semantics.

## Installable distribution requirements

The target release supports `pip install autoslurm` from an agreed package index.
Check availability/ownership of the distribution name and index credentials
during release preparation; do not assume a version is published. Publication
is a distinct release action, outside this planning task.

Build and test both a wheel and source distribution. A fresh environment must
be able to install the wheel, and build/install the source archive, then run
outside the repository with only declared dependencies. Test supported Python
versions and operating systems consistent with cluster/workstation support.
Separate required runtime dependencies, optional integrations, test dependencies,
and documentation build dependencies.

Release acceptance includes:

- Console entry points import and show help outside a source checkout, with
  clear explanations when SSH, Slurm or transfer tools are unavailable.
- Version-matched agent recipes, schemas and small reference assets are included
  in the distribution and discoverable without internet or a repository clone.
- Configuration, run records and caches use explicit writable runtime locations,
  independent of the installation directory. No writes to `site-packages` or
  reliance on the source tree for normal operation.
- A small local/fake-adapter workflow exercises scheduling, identity lookup and
  documentation retrieval from the installed artifact. Import/help do not
  require cluster credentials or invoke remote commands.
- Wheel/source contents include necessary package data and exclude credentials,
  local runtime records, large logs, and generated documentation build trees.
- README and package metadata give a concise purpose, install instructions,
  supported versions, human guide link, and agent integration entry point.
- Release checks cover client/helper compatibility and the upgrade/migration
  behavior of existing configuration and saved runs. Upgrading the package
  must not silently discard tracking history.
- Published documentation is versioned with the package, built from a documented
  dependency set, and checked for broken internal links and stale examples.

PyPI distribution installs AutoSlurm; it does not provision the scientific
application, cluster system tools, data, accounts or environments automatically.
Compute nodes execute prepared software without an installation step in each job.

## Implementation sequence

| Milestone | Deliverable |
|---|---|
| MVP0 | Separate stable/development installs and roots; record baseline and the short safe-operation recipe |
| MVP1 | Reference client with relative paths and a basic install smoke check; no source-tree state assumptions |
| MVP2 | Correct submission/environment instructions covering partial and uncertain outcomes |
| MVP3 | One-page human system map and working example; agent inspection/diagnosis recipes using shared evidence |
| MVP4 optional | Small result retrieval example |
| L1-L2 later | Richer history, provenance and automated scientific recovery examples |
| L3 later | Complete wheel/source-install CI, packaged agent resources, versioned human site, migration notes and release/publication workflow |

Keep the simple installation path and relevant recipes working throughout.
Avoid source-layout/state assumptions that would make later packaging expensive,
but do not require full distribution or site completion before shipping an MVP.
