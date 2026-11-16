# FETCH.1 selected-run execution evidence

## Status and scope

Complete locally in 0.2.0.dev6, 2026-11-16, after the user requested fetching. Existing explicit
logs/execution-records-only scope applies; scientific results remain application
owned. Work locally on dev, mocked cluster commands and temporary state only.

## Implementation contract

Expose asl fetch using the same selectors/presentation as asl logs and a public
fetch_run entry point returning the inspection object. Refresh only receipts
already linked and validated against the exact selected tracking snapshots,
then collect scheduler observations and bounded producing-path log excerpts.
Reuse existing refresh_submission, inspection/cache and selection owners; do not
implement another transfer or status engine. Cached fetch performs no remote
receipt, scheduler or source-log reads and no projection writes.

An explicit fetch may update the exact local receipt/tracking projection and
observation/excerpt caches. Receipt refresh failures must retain existing IDs
and allow status/log reads to continue; errors and partial freshness remain
visible. Failure in one selected run cannot discard another run's evidence.
Validate bounds/selectors and linked identity before effects. Never submit,
retry jobs, guess a receipt by bundle name, change producing roots/aliases or
merge another installation's definitions.

Replace unbounded remote receipt cat with the existing standalone regular-file
reader: one exact recorded path, max 1 MiB, 30-second timeout, strict response/
size/encoding/receipt identity checks. Missing, unreadable, transport, malformed,
oversized and changing records are distinct failed observations. No remote
AutoSlurm install is needed; python3 is required as for logs. Keep old valid
receipt/known IDs if fetching fails and never infer scheduler failure from it.

Logs retain existing 40-line/64-KiB/20-file defaults, 1-MiB/100-file upper bounds,
filter-before-bound semantics and explicit omissions/truncation. Fetch saves
excerpts into existing caches, not complete log files or a new export directory.
Legacy sync remains an explicit whole-directory mirror; describe that distinction
and do not recommend it as bounded retrieval. Changing sync policy, discovering
cluster-only receipts and scientific-result fetching are separate work.

## Checks and closure

49 new cases verify API/CLI/ACP selectors, receipt recovery before status/logs,
partial receipt/transport/cache/persistence failures, retained IDs even without
saved local evidence, exact shipped reader execution, a 1-GiB sparse receipt,
special files, identity/encoding/size guards, sparse and historically observed
arrays, no host fallback/name guessing and cached no-contact/no-write behavior.
1337 full offline tests passed in 10.37 s, 47 expected collision warnings;
`.development/test-runs/fetch-evidence.xml`. Existing submission-loss/replay
regressions now execute the exact bounded worker against temporary receipts.

No-Git/no-runtime-import metadata, wheel and sdist-to-wheel builds pass. A
disposable installed package verifies runtime/CLI/distribution identity, recovery,
exact workers, partial failures, cached reads, CLI/ACP and packaged section18.
Direct/rebuilt wheel contents match. Artifact hashes are in the
[installation register](../installation-register.md). Inventory additions were
reviewed individually: four routes/two owners, total 266/138, with the existing
20 broad catches unchanged. Runtime errors use errors.py; receipt orchestration
and bounded transport have separate owners and share the existing projection.

## Forward constraints and log

Legacy sync is unchanged and explicitly documented as a whole-directory mirror;
it is not this bounded workflow. New fetch follows exact existing links only;
remote-only receipt discovery and scientific results remain separate decisions.
No actual cluster contact, daily config/state edits, base/test dependency install,
external-client change, record schema/history migration or rollback edit occurred.
Source follows dev6 through the existing editable install; installed metadata is
still 0.1.0 without reinstall. Actual cluster checks remain operator-owned.

2026-11-16: FETCH.1 complete locally, annotated v0.2.0.dev6; MVP10.4b remains next.
