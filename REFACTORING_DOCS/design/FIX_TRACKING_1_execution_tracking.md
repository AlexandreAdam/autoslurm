# FIX.TRACKING.1 execution-side tracking

## Status and problem

Implemented locally on dev in 0.2.0.dev7, 2026-11-16. The user requested that laptop-originated
submissions also appear correctly in cluster-local asl status. Scripts and
incremental execution receipts already reach the cluster, but its jobs directory
has only drafts, and receipts retain workstation-only tracking paths/transport.

## Implementation contract

Send the exact prepared tracking definition with the existing bulk payload.
Validate job/dependency/submission/execution identity before any scheduler call.
The helper exclusively creates a normal timestamped tracking snapshot under its
selected jobs directory, records its exact execution_bundle_path in the receipt,
and writes the receipt before submitting. Timestamp collisions allocate another
free timestamp; an existing draft or attempt is never overwritten.

A small execution_tracking module owns the execution-side view: the same
submission ID, job definitions, producing roots and resolved application paths,
with local transport and the execution receipt reference. The original receipt
keeps origin bundle_path, receipt_path, planned_path, execution and machine.
Each incremental receipt is durable before updating its derived tracking view;
existing projection, inspection and scheduler/log owners remain authoritative.
Projection failures stop further submission, retain known IDs and remain readable
through the receipt overlay. No scheduling retry or receipt search by name.

Receipt inspection selects execution_bundle_path only when the selected receipt
file is its exact execution_receipt_path and differs from the origin receipt.
Cluster fetch/refresh reads local evidence without SSH to itself or rewriting
origin identity. Cached inspection retains its no-source-read/no-write behavior.
Workstation refresh keeps using its recorded transport and origin snapshot.

The optional execution_bundle_path is additive receipt protocol-1 evidence.
New remote execution receipts use `<submission_id>.execution.json`, distinct
from origin `<submission_id>.json`, even when both machines' roots have identical
absolute names. Historical paths are retained and read through their old links.
Validate its root/name and pin it once observed. New submissions require an
execution_tracking capability in addition to submission_protocol; an old helper
stops before staging/dispatch with an update instruction. No installed helper is
updated automatically. Older receipts remain readable; existing remote drafts
are not guessed into attempts or migrated. New behavior applies after both ends
run the matching implementation. Legacy whole-directory sync is unchanged.

## Verification and limits

Use two temporary installation roots and mocked transport/scheduler commands.
Check cluster selection/status/logs/fetch without workstation files or profile,
arrays and dependencies, incremental/partial/uncertain outcomes, collisions and
independent attempts, failures before/after acceptance, replay and old helpers.
Run the full offline suite and no-Git wheel/sdist/installed smoke, then update
human/agent recipes, audit, installation register, version/changelog and plan.
No live cluster commands, package/environment installation in daily use,
scientific data transfer, historical migration or pinned rollback changes.

## Decisions

User requirement: submission must establish cluster-local tracking. Exact
provenance, capability negotiation and additive view metadata are implementation
choices within that request; no broader architecture decision is marked accepted.

## Checks and closure

24 new regressions exercise the real JSON helper through fake SSH/Slurm, two
temporary roots, workstation disappearance, cluster-local status/log/fetch/
inspect and ACP, cached reads, arrays/dependencies, independent attempts with
timestamp collisions, partial/lost responses, failures before/after acceptance,
replay, exact backlink validation, missing acknowledgments and old helpers.
1361 full offline tests passed in 12.21 s, 67 expected collision warnings;
`.development/test-runs/execution-tracking.xml`. Installed-package evidence is
recorded in the installation register. Shared AST coverage: 266 routes/138 owners; one
new reviewed pre-scheduler receipt-protection catch, 21 broad catches total.
Existing incremental persist protection now covers the derived view as well.

No-Git/no-runtime-import metadata, wheel/sdist-to-wheel builds and installed
runtime/distribution/console versions pass. Disposable installed helper creates
the local view, then cluster status/log/fetch/inspect/ACP work with the origin
directory unavailable. Cached reads and local receipt refresh make no SSH calls;
the helper-owned receipt stays unchanged. Packaged section18 describes the
interface and helper capability boundary. Direct and rebuilt wheels match.

No actual cluster was contacted or updated. Main/base imports the dev7 source;
editable metadata remains 0.1.0 without reinstall. No daily config/state,
dependency/environment install, scientific data, external client, historical
record migration or pinned rollback edit. New remote submissions require an
operator update of the cluster helper; old cluster drafts are not adopted.
Legacy sync and historical receipt discovery remain separate.

2026-11-16: FIX.TRACKING.1 complete locally; v0.2.0.dev7 checkpoint. Resume
MVP10.4b SSH/session/helper diagnostics; no general submission-error overhaul.
