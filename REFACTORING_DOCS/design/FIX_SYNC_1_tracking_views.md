# FIX.SYNC.1 controller views for synchronized submissions

Authorized 2026-11-27 after the user confirmed that laptop and cluster profile
names intentionally differ. Local/mock implementation only; no repair of daily
records or live cluster commands during development.

`asl sync MACHINE` explicitly chooses the source transport/root. Stage jobs in a
temporary directory, validate a tracked submission and fetch its exact receipt
through the existing 1 MiB/30 second reader. Import only native execution views
under that root, not records targeting another machine or unsubmitted drafts.
Untracked legacy submissions are reported as unsupported rather than guessed.
Keep the existing bulk Slurm-script/out mirroring; bounded evidence fetching
remains fetch_run/asl fetch and does not change.

Publish a controller view through the selected profile with original scientific
definitions, producing roots and Slurm IDs. Remote profile names never need to
match. Reuse an existing controller snapshot by submission identity, validate
definitions/known IDs and preserve its path, including campaign references.
Otherwise create an ordinary versioned snapshot without clobbering a collision.
Reuse exact receipt projection/observation validation, with no submission/retry.

Protocol 1 remains unchanged. Imported receipts add `sync_origin`, retaining the
original immutable receipt identity/paths/execution (including any execution
tracking path). The local view keeps usable local bundle/receipt paths and a
remote execution transport. Future receipt refresh validates the original
identity first, then translates it to this same pinned controller view. Old
readers retain readable records but need this release to refresh imports.

Repair previously raw-copied files only when submission identity, definitions,
producing root and known IDs agree with the selected source. Back up changed
local snapshots/receipts under sync_backups before publication. Verified redundant
views of that exact submission can leave normal discovery only after the
canonical view is published; preserve them in backups. Never merge by name/date
alone. Same-ID/different-definition, transport or scheduler-ID conflicts retain
all evidence and report failure. Missing/unreadable/corrupt source receipts leave
local records untouched. A failed item must not prevent healthy neighbours.

Writes use the existing atomic JSON owner. A receipt/snapshot pair is not a
multi-file transaction: interruption can leave one published first, but known
IDs/original evidence remain and another explicit sync reconciles the pair.
No automatic retries, remote writes, deletion of scheduler jobs, source code
copies, scientific result transfer or new status database. Record changes made
concurrently are rejected when observed; this is not a global locking service.
Repeated unchanged syncs do not create new snapshots or backup copies.

Gates: offline two-installation tests with different names; cluster-origin and
laptop-origin jobs, partial/uncertain receipts, refreshed IDs, repeated sync,
raw-copy repair, missing/corrupt/conflicting/changed records, local publication
failures and status/log/cancel/fetch context. Full suite, installed package smoke,
documentation, task log, version checkpoint and dev push.

## Implementation and verification (2026-11-27)

Completed FIX.SYNC.1, checkpoint 0.2.0.dev18. `tracking_sync` owns staged import,
source/controller validation and backed-up publication. Existing `submission`
now owns one in-memory receipt projection and one source-observation merge, shared
by sync and refresh. Filesystem/SSH/receipt/log/status adapters are reused; no new
public route or broad catch was introduced (inventory 292 routes/146 owners/21).

Twenty-one regression cases exercise differing profile names, native and original
laptop submissions, exact status/log/cancel/fetch context, partial receipts and
monotonic IDs, stable repeat sync, raw snapshot/receipt repair, duplicate
retirement, conflicts, healthy neighbours, orphaned copies, concurrent changes
and interrupted publication/recovery. Full offline suite: 1869 passed in 21.51 s, 105 expected
collision warnings, report `.development/test-runs/tracking-sync.xml`. Installed
wheel smoke outside the checkout passes native sync/raw repair/backup/status/log/
fetch/refresh/repeat/recipe discovery and prior campaign/cancellation/status checks.
No-Git static metadata, wheel, sdist and wheel-from-sdist builds passed with matching
installed runtime/distribution/CLI identity and direct/rebuilt member contents.
Artifact hashes are in the installation register. No base/test dependency install,
live cluster operation, daily record repair, SSH-config change or rollback edit.

Public human guidance is docs/sync.md; packaged agent recipe is 22_sync. Update
only the controller for this fix; existing execution helpers need no new protocol.
Older clients can read compatible records but must upgrade to refresh imported
sync_origin views. Untracked legacy jobs remain unsupported and are skipped;
source filename collisions and orphan raw copies retain evidence and report errors.
Broader MVP10 observation diagnostics/MVP11 consolidation are not closed here.
