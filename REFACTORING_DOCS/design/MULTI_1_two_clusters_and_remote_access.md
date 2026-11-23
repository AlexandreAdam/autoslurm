# MULTI.1 Campaigns and access from home

## Status

Design revised on 2026-11-23 from Alexandre's proposal and clarification.
**Requested:** coherent context for work spread over rusty and popeye, and support
for the extra gateway step when working from home. **Proposed:** the contracts,
record layout, command names and delivery slices below. MULTI.1a–c connection checks, campaign grouping and observation are implemented
in 0.2.0.dev13–15. Coordinated submission/retry and scientific task mappings remain
proposed; the implementation log below narrows the original larger schema. [PLAN.md](../../PLAN.md) owns progress.

A campaign groups ordinary runs. Each run still selects one execution machine;
this does not introduce jobs whose execution moves between machines.

## Actual access workflow

At work, the laptop can use the cluster aliases directly. At home, Alexandre
currently opens two successive interactive SSH sessions:

```text
laptop:  ssh flatiron
         authenticate to the gateway (password/code as required)
gateway: ssh rusty       OR       ssh popeye
```

`ssh rusty` from the home laptop does **not** currently work. A shell on flatiron
does not by itself make later laptop SSH/SCP/rsync commands use that shell. Do not
present a transparent same-alias setup or one-login-per-day routine as existing
behavior. flatiron is an access host, not a third Slurm execution machine.

### Controller location and the access boundary

The controller is the host running AutoSlurm and holding its selected local
tracking store. Execution machines run Slurm jobs. There are two candidate modes:

| Mode | Requirements and consequences |
|---|---|
| Laptop controller through the gateway | Operator/site must confirm that an SSH jump connection is permitted and supports this authentication. Operator supplies working SSH aliases on the laptop. AutoSlurm then uses those aliases through its ordinary adapters. This is unverified. |
| Controller inside the accessible network | Gateway or login host must permit the required software, outbound cluster commands and durable storage. Authentication into that host stays interactive. This does not automatically carry laptop tracking records or discover campaigns on other clusters. |

Prefer one controller and its authoritative campaign store for the first release.
Changing controller hosts is explicit: a campaign file alone is insufficient if
its linked bundle definitions and receipts exist only on the laptop. Execution-side
tracking already helps inspect an individual submitted run on its own cluster;
it does not automatically publish an entire multi-machine campaign there.

Host-to-host campaign export/import is deferred. An alternative controller can be
used with records created there; moving an existing campaign requires an agreed
transfer/import design first. No silent profile fallback, hostname rewriting,
assumption of shared home directories or automatic state synchronization.

Operator-owned SSH config continues to own HostName/User/keys/routing. AutoSlurm
never enters a password/code, drives an interactive nested shell, edits SSH config,
creates forwarding services or bypasses the gateway. Jump support, connection
sharing and allowed lifetime must be verified with the site. No promise that a
previous terminal login establishes a reusable connection for AutoSlurm.

### Proposed noninteractive transport policy

One shared SSH option policy should cover SSH, SCP and rsync's SSH invocation,
including root/helper probes, scheduler/log/receipt reads, staging, submission,
software operations and owned submission sessions. Some routes already supply
BatchMode and timeouts; audit and compose them rather than adding a parallel
transport. Preserve recorded destinations and caller options.

Use noninteractive authentication and bounded commands. Borrow operator-owned
shared connections when available; never close them. Retain existing ownership
and cleanup rules for AutoSlurm's own sessions. Do not add blind retries.
Operator-supplied jump configuration needs separate verification that both hops
remain noninteractive; an outer SSH flag alone is not proof of that.

A failed connection is not proof of an expired login: SSH launch failure,
configuration, DNS/routing, gateway/authentication and remote-command failure
need distinct evidence where observable. Otherwise report transport unavailable
with the stage/alias/timeout and uncertainty. Never infer authentication failure
from exit 255 alone. Suggested action at home should mention `ssh flatiron`, then
`ssh rusty`/`ssh popeye` from there, and the controller location; do not prescribe
`ssh rusty` on the home laptop as a sufficient repair.

Proposed `asl connection check --machine rusty` / `--all`, plus equivalent Python
and structured output, tests only explicitly configured profiles with bounds:

- Optional configured-master check is evidence of a connection, not proof of
  remote command readiness. Absence of a master is not failure: key authentication
  may work without one.
- A bounded noninteractive no-op probe can establish command reachability from
  **this controller** at the observation time. It does not establish Slurm,
  environment, filesystem, CUDA or scientific readiness.
- Report ready, unavailable or unknown, timestamp, attempted alias/stage, shared
  connection observation and supported cause facts. Login-required is a diagnosis
  only when evidence supports it; otherwise show it as a possible operator action.
- It never prompts, executes env_command, installs software or deliberately creates
  an AutoSlurm master. Ordinary operator SSH settings may create connection/cache
  state during a probe; do not claim zero local side effects.

No concrete home SSH configuration is recommended until the site constraints are
known. An inaccessible laptop route can remain unavailable while campaign record
and cached-context work is developed and tested offline.

## Campaign ownership and record proposal

A campaign is an AutoSlurm grouping over exact ordinary runs. The client owns
scientific task generation, split/cost model, output validation and data movement.
AutoSlurm owns references, validation, observation provenance and bounded context.

Confirmed user boundary (2026-11-23, MULTI.1c.docs): no cross-machine
dependencies. Dependencies stay inside ordinary single-machine member bundles.
Campaign submission coordination must not introduce cross-member prerequisite
gating. Clients/operators own prerequisite/output/data checks before explicitly
submitting downstream work; cross-machine orchestration is outside MULTI.1.
Campaign status/log entry points are campaign inspect/fetch; individual-run
status/log interfaces do not select campaigns. No operator SSH route was changed.

First useful slice: group already saved runs on two machines, without requiring
new planning/submission orchestration. One initial member per machine. Later
attempts remain under that member; no rebalancing in the initial release.

Proposed plain JSON definition, illustrating the contract rather than a frozen
schema (task mappings use half-open ranges):

```json
{
  "format_version": 1,
  "campaign_id": "<stable unique id>",
  "name": "grid-refinement-v1",
  "revision": 1,
  "context": "Refine the selected stellar grid; the client chose a 3:1 split.",
  "task_count": 2000,
  "members": [
    {
      "member_id": "rusty-share",
      "machine": "rusty",
      "bundle_ref": "plans/rusty_20261123120000.json",
      "bundle_sha256": "<digest of exact saved definition>",
      "workload_job": "shards",
      "task_mapping": [{"campaign_start": 0, "array_start": 0, "count": 1500}]
    },
    {
      "member_id": "popeye-share",
      "machine": "popeye",
      "bundle_ref": "plans/popeye_20261123120000.json",
      "bundle_sha256": "<digest of exact saved definition>",
      "workload_job": "shards",
      "task_mapping": [{"campaign_start": 1500, "array_start": 0, "count": 500}]
    }
  ]
}
```

Reference-file paths are relative to the campaign directory on its controller;
they are not application input/output paths or remote paths. Existing run evidence
owns resolved roots/transports. Runtime metadata added to a submitted tracking
snapshot does not redefine the fingerprinted planned bundle. Attempts link the
exact derived tracking snapshot and receipt separately.

Required validation before publication:

- Unique stable campaign/member identities, supported version and named machine;
  every job in a member belongs to that member's machine. Names are labels,
  not substitutes for identity; numeric Slurm IDs are scoped to their machine.
- Readable exact bundle definitions and matching fingerprints. No latest-bundle,
  nearest-date, directory-name, host-name or job-name guessing.
- Plain grouping supports existing ordinary runs without requiring an array or
  scientific task mapping. Report member/job counts; do not invent global task
  progress when no task domain was declared.
- When a client declares a logical task domain, its named workload job must exist
  and declared array indices must match each explicit mapping. Mappings are
  nonempty, in-range, disjoint and covering; local array index 0 can refer to a
  different global task on each machine. Validate ranges without expanding huge
  lists. Setup/merge/summary jobs are not extra scientific work units. Generic
  task-mapping support can be split out before submission coordination if it
  would delay the minimal existing-run grouping slice.
- Client job arguments remain explicit script_args, with typed CLI validation.
  Campaign context never replaces job settings with an opaque config argument.

Keep the definition immutable after creation. Changed options/split produce a new
revision linked to the previous definition; old definitions and attempts remain.
A small separately published association record links member attempts/receipts;
receipts alone own accepted IDs/submission outcomes. Reuse atomic JSON publication
and existing receipt persistence, not a second submission engine/database.

Before MULTI.1b writes a new record, review/freeze the minimal v1 schema,
publication/collision/size bounds and retention rules. This is a new opt-in record
at an explicit package checkpoint. Existing bundles/receipts are unchanged; no
automatic historical import/migration. Unknown versions are retained and rejected
with an actionable diagnosis. Do not silently convert records in place.

## Coherent context and everyday interfaces

Proposed discovery and observation routes (not currently available):

```text
asl campaign list
asl campaign inspect NAME --cached
asl campaign inspect NAME --json
asl campaign fetch NAME --member rusty-share --job shards --task 17
```

Python create/load/list/inspect/fetch campaign operations and agent/ACP routes
must share the same service and evidence. Use a distinct campaign namespace to
avoid a campaign name silently shadowing a bundle name. Member and task selectors
must be exact; details always carry campaign/member/attempt/machine identity.

Reuse inspect_bundles, exact receipt refresh, scheduler grouping, caches and
bounded log reading. These are existing implementation owners, not instructions
for client agents to import private modules. Harden per-member failure isolation
where required; a sequential exception must not prevent observing other members.
No second scheduler query/parser, log downloader or mutable status database.

The returned context separates:

1. Declared intent: revision, human rationale, planned tasks, machine allocation
   and exact definitions/attempts/software expectations.
2. Submission facts: not submitted, accepted, rejected, partial or uncertain, with
   original receipts/accepted IDs. One member cannot overwrite another's outcome.
3. Observations: member/job/task scheduler state, counts, reason/exit details,
   current/last successful observation times, source, errors and freshness.

The campaign collection time is not a simultaneous snapshot of two clusters.
Example of a compact human view (illustrative values):

```text
campaign grid-refinement-v1   revision 1   observation: partial
member        machine  last observed state  completed  observation
rusty-share   rusty    RUNNING               800/1500  fresh, 14:20 UTC
popeye-share  popeye   RUNNING               120/500   stale, 13:10 UTC; connection unavailable
known completed: 920/2000 (includes 120 last observed on popeye)
```

Never call this 920 freshly verified completions. Report scheduler completion
separately from client-validated scientific success. Keep counts of logical work
and supporting jobs separate. Do not double-count old attempts or sum CPU/GPU
capacity into a misleading cross-cluster availability total. Missing definitions,
receipts or task mappings are unavailable evidence, not zero work or completion.

A gateway outage, one unreachable cluster, a damaged member reference or a log
error leaves good member evidence accessible. Structured output carries partial
outcome/errors; a failed refresh is visible even when cached data can be shown.
Unexpected bugs remain debuggable instead of being mislabeled as connection loss.

### Fetching, caching and bounds

Campaign fetch retrieves AutoSlurm execution evidence only. It refreshes exact
linked receipts, then status and bounded log excerpts. No scientific outputs,
datasets, entire-directory sync or guessed remote campaign discovery.

A cached campaign inspection/fetch does no network, scheduler/source-log access,
receipt refresh/projection or cache writes. Missing cache is explicit. Initially
compose member caches; avoid persisting a competing aggregate status cache.

Set request-wide as well as per-member bounds. Proposed first defaults: two
members, 120-second overall observation deadline, at most 20 log excerpts and
256 KiB of excerpt content across the campaign; retain the existing per-log and
1 MiB/30-second receipt bounds. Thread remaining deadlines through existing
adapters rather than allow each operation to restart the full budget. Validate
selectors before effects, preserve collected evidence at the deadline and label
unvisited members/items as not attempted. Specify a serialized response bound
and clipping markers before implementation; counts alone do not bound task JSON.
Round-robin excerpt selection avoids the first member consuming all capacity;
explicit member/job/task selection narrows the same pipeline.

## Submission, identity and retry (later slices)

Clients split scientific work and produce ordinary member bundles. A future
campaign review shows each member's options/resources/software evidence and the
combined planned demand before any mutation. Existing per-machine scheduler
policies remain separate; verify actual limits rather than hard-code the draft's
unverified 50-job assumption. Planning should be usable offline.

Software identity is compared to a declared expected commit per relevant project
on each machine. No unspecified "latest" choice may silently mix revisions in one
campaign: an unpinned request needs one explicitly resolved/recorded target before
coordinated submission. Equal package versions alone do not establish equal code;
unknown/dirty/incompatible evidence blocks or requires an explicitly reviewed
policy. Machine-specific dependencies may differ and satisfy their own declared
requirements; environments need not be identical. Status never installs or pulls.
Updates stay explicit single-checkout operations on login hosts and are coordinated
by the operator with existing queued/running work.

Submission proceeds in a documented order, persisting each member's receipt link
before another member is dispatched. A failure stops new member dispatch by
default and leaves earlier accepted jobs alone. No cross-cluster transaction,
automatic cancellation, rollback, retry or fall-through to another profile.
Before implementing orchestration, prove durable member-to-receipt association
**before its own dispatch**, including a controller crash immediately after
acceptance. Extend the existing receipt lifecycle narrowly if necessary; if
association persistence is uncertain, stop and expose recovery evidence rather
than assume no submission happened. An outcome already uncertain is inspected,
never replayed as a convenient way to fill a missing association.

Resubmission is a new reviewed attempt derived from an exact immutable campaign
revision, selected member and declared retry tasks. It is not regeneration from
whatever mutable client run file happens to exist. Store the derived readable
options and link original/new attempts; ambiguous/unobserved tasks are excluded
until inspected. Preparation runs on the controller, not inside compute jobs.
A builder needing cluster-local facilities is a separately justified extension;
rebuilding on the cluster is not the cure for stale options. Reuse MVP12.6 retry
planning; do not implement a competing retry engine here.

No rebalancing, automatic failover, cross-cluster Slurm dependencies or result
staging/merging in this release. A client may later plan a separate summary run
once its required scientific inputs have been collected and validated by the client.
Shared filesystems are unverified and never inferred from matching path strings.

## Responsibility map and integration with existing work

| Concern | Existing owner / planned extension |
|---|---|
| SSH addressing and command options | transport, transfer adapters and session ownership; shared noninteractive policy |
| Expected diagnostics | errors module and existing operation adapters; MVP10 adoption continues |
| One-machine planning/submission | bundle preparation, job runner, submission operation/receipts |
| Observation and artifacts | inspection collection/projection/cache/receipt refresh and scheduler |
| Campaign definition/association validation | One small new campaign owner, names/contracts settled in MULTI.1b |
| Campaign context | Composition over member views, separate pure aggregate projection and presentation |
| Readable status interpretation | Shared with MVP11; no duplicated reason classifier |
| Named run grouping | MULTI.1b/c satisfy MVP12.4's common grouping layer; no second run registry |
| Resource review, offline planning, retry | Reuse MVP12.1–3/6; split only prerequisites actually needed |
| Scientific split/cost model/data | Client application; no Gaia edits in this repository task |

## Delivery slices and acceptance gates

Each slice is independently usable, versioned and documented through supported
Python/CLI/agent interfaces. Do not require finishing MVP10–12 wholesale first.
All development checks use temporary records and mocked SSH/Slurm, with no live
cluster/operator configuration changes.

| Slice | Small delivery | Required proof |
|---|---|---|
| MULTI.1.0 | This design, real access topology, ownership and staged plan | Source trace, documentation/link review; no runtime changes |
| MULTI.1a | Shared bounded noninteractive transport policy and connection check | SSH/SCP/rsync/session/probe callers covered; gateway failures, unsupported auth, key-only access, missing master and unknown causes; no prompts, retry or altered destinations |
| MULTI.1b | Opt-in campaign record and public create/load/list for existing runs | Frozen v1/release boundary, exact refs/hashes, machine-scoped IDs, overlap/gap/mapping/version/collision/corruption cases; offline publication only |
| MULTI.1c | Inspection, cached context and bounded fetch across members | One failed machine preserves the other; per-member freshness, identical job IDs on different clusters, independent attempts, global limits/deadline; Python/CLI/ACP and installed agent recipe |
| MULTI.1d | Reviewed ordinary member submission from a client-supplied split | Pre-dispatch durable association, crashes/partial/uncertain acceptance, machine-specific checks and software targets; no replay or silent update; reference client proof |
| MULTI.1e | Revision-based explicit retry planning and handoff | New attempt/definition links, original options retained, no duplicate logical work/unknown-outcome retries; share MVP12.6 |

Split a slice before implementation if its audited surface is too large; do not
turn each proposed interface into a mandatory redesign. The first campaign MVP is
**MULTI.1b + MULTI.1c over existing runs**. MULTI.1a improves home failure handling
but cannot by itself establish a permitted laptop-to-cluster route. Its operator
access check is not a prerequisite for offline campaign development.

Each implemented slice ships a human example, installed agent discovery/recipe,
plain outcome/evidence contract and fake two-machine fixture. Human docs explain
controller vs execution hosts, gateway login, partial evidence and drill-down;
agent docs specify identities, bounds, freshness and safe follow-up. Proposed
commands stay out of current capability/help claims until implemented.

## Open decisions and operator facts

- Whether Flatiron permits/supports the relevant jump/authentication/sharing
  setup; no access attempts or SSH config edits are authorized by this design.
- Which controller Alexandre wants for daily campaigns. Laptop-first depends on
  an approved working route; gateway/login-host operation depends on site software,
  storage and access policies. No automatic campaign portability is promised.
- Popeye's actual partitions/accounts/limits/modules and environment; paths and
  shared filesystem assumptions must be independently verified by the operator.
- Final minimal v1 schema, reference retention and bounded task mappings/output;
  missing members after manual/ordinary cleanup must remain visible as unavailable.
  Campaigns do not automatically recreate or silently delete those records.
- Strict expected-commit and explicit override policy, allowed retry-task states
  and scientific completion signals: settle before their dependent slices.

## Design log

2026-11-23, MULTI.1.0: revised the original draft against the actual two-step
home workflow and existing transport/inspection/receipt/cache owners. Removed
unverified SSH configuration, automatic reachability switching, guaranteed daily
sharing and cluster-local resubmit assumptions. Defined exact grouping, partial
context, global bounds, controller-store limitation and five implementation
slices. Consolidated overlap with MVP11 and MVP12.4/6. Documentation only;
implementation contracts remain proposed, no cluster access, tests or deployment.


2026-11-23, MULTI.1a implemented: shared SSH/SCP/rsync BatchMode=yes and
ConnectTimeout=10, direct remote sbatch/bulk-driver 60/300-second bounds, public
check_connections / connection check / ACP with per-machine no-op observations.
The first implementation deliberately omits the optional master-status probe:
ready does not require sharing, and no master does not prove authentication need.
No env setup or scientific imports. 12-second probe, up to 32 configured profiles;
expected failures retain cause/time and neighbours. 15 new regressions plus
updated exact transport expectations; full offline and package evidence recorded
in the installation register. No cluster access or site-route verification.


### MULTI.1b implemented v1 boundary (2026-11-23)

The implementation request authorizes the minimal existing-run grouping slice.
The frozen v1 fields are format_version=1, campaign_id (32 hex UUID), name,
revision=1, created_at, context, members; each member has member_id, machine,
bundle_ref, bundle_sha256. Public load adds campaign_path as a locator. Relative
references resolve against that campaign's controller directory and may refer
outside it to existing bundles. One/two distinct machine/member/path entries;
64 KiB record, 8 MiB bundle and 8 KiB context limits. JSON duplicate keys fail.

Canonical parsed-definition digests ignore whitespace. Only receipt-bearing jobs
with exact immutable submission_id/receipt_path links exclude mutable id and
submission state/id/error from hashing; legacy saved IDs remain fingerprinted.
All options, graph and recorded execution metadata remain fingerprinted. Record
publication is exclusive/atomic. No edits/migrations/overwrites: changed plans get
a new name/identity. Unsupported versions/fields remain intact and fail visibly.
No historical records are imported. Task mappings and attempt journals from the
larger example above are deliberately not v1 fields; settle their opt-in record
boundary in MULTI.1d rather than quietly accepting unused metadata now. This
satisfies the minimal grouping/discovery portion of MVP12.4, not its later review
and retry requirements. CLI create/list/show, Python and ACP use one record owner.
Member absence after cleanup is retained as a reference for later inspection.


### MULTI.1c implemented observation boundary (2026-11-23)

Public inspect_campaign/fetch_campaign, campaign inspect/fetch and ACP share one
coordinator over exact member validation and ordinary inspection/fetch services.
Separate campaign_projection owns pure counts/clipping; CLI owns presentation.
No new scheduler parser/downloader/aggregate cache. Missing/changed members and
receipt failures do not discard neighbours. Source mutation during observation
retains minimal unverified IDs separately, without attributing them to this campaign.
Submitted members lacking producing metadata do not infer current-profile routing.

Selectors are member ID plus exact job name/declared task index; validate before
effects. Optional cached reads never refresh receipts, query Slurm/source logs or
write caches. Run-cache last_observed optionally retains prior jobs; old records
remain readable. Cached count validation rejects impossible/negative counts.
Collection time, per-member observation time and last-known time remain distinct.
Fresh-count totals include only fully fresh members; partial-member evidence stays
in the individual views, never silently counted as fresh or scientific success.

The command-admission deadline is at most 120 seconds with per-member allowances;
remaining time flows through existing scheduler/receipt/log subprocess adapters via
a context-local deadline scope that is reset even on interruption. Local OS file
calls cannot be forcibly interrupted. Global fetch limits 20 excerpts/256 KiB of
returned UTF-8 content, per-excerpt at most 64 KiB; existing receipt caps retained.
Initial context limits 200 jobs/10000 declared tasks per member, bounded 32-bit
indices, max 250 task details per member/current or prior view and compact UTF-8
JSON at most 2 MiB. Explicit omission markers and narrowing selectors preserve
access to detail. No application results/datasets or whole-directory mirroring.

v1 still has no scientific task mappings or campaign-attempt journal; these are
future opt-in contracts rather than silently accepted metadata. Grouping/inspection
implements the requested first campaign MVP, not MULTI.1d/e or all of MVP12.4.
Full fake-cluster regression and installed-package evidence is in the installation
register. No actual SSH/Slurm, configuration edits or remote installation performed.
