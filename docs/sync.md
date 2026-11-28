# Sync tracking between cluster and laptop

A job submitted on the laptop gets a cluster-local tracking view at submission.
`asl sync` brings native cluster submissions and their latest receipts back into
the laptop's view:

```console
asl sync rusty
asl status --head
```

Here `rusty` is the **laptop's profile**. It selects the SSH alias and remote
AutoSlurm storage root. The cluster can call its local profile `rusty-local`;
the names are expected to differ. Do not rename profiles to make them match.
Sync does not change either configuration or the cluster's records.

Tracking is matched by submission ID. A laptop-originated submission keeps its
existing tracking path, including campaign references. A native cluster run gets
a laptop view that queries Slurm and reads logs through the selected SSH alias,
using the original cluster paths and scheduler IDs. `asl status`, `asl logs` and
`asl fetch` then use their ordinary selectors; display indices are local and need
not match the cluster. Observations collected at different times may still differ.
Use exact bundle/receipt references for durable handoffs.

## Repairing copies made by older sync versions

Update the laptop installation to 0.2.0.dev18 or later, then run the explicit sync
above. The cluster needs no new helper for this fix, but its records must already
have submission receipts and execution metadata. Sync stages snapshots first,
validates their exact linked receipts (at most 1 MiB, 30 seconds per receipt),
and publishes a controller view only when the source identity, job definitions,
producing paths and known IDs agree. Unsubmitted drafts and untracked legacy
files are skipped. A filename collision is reported rather than overwritten.

Verified raw cluster copies are repaired automatically during that explicit sync.
Changed local records are backed up under `sync_backups/<submission-id>/` in the
local AutoSlurm storage root. Verified redundant views of the same submission
leave normal discovery after the canonical view is saved; their backups remain.
Unchanged repeat syncs create no new runs or backups. Source provenance stays
in the local receipt for later refresh; no scheduler jobs are submitted or retried.

Missing, corrupt, conflicting or changed records are retained and reported.
A raw local copy without a verified source is retained without guessing a repair.
Healthy neighbours can still import when another record fails; the command reports
incomplete tracking and exits unsuccessfully. A transport failure stops further
receipt reads for that machine. Receipt and snapshot publication is recoverable,
not a multi-file transaction: after correcting the problem, repeat the explicit
sync to reconcile an interrupted pair. Never resubmit jobs to fix a sync error.

## Transfer scope

Sync also retains the existing bulk transfer of `slurm/` scripts and `out/` logs:
existing scripts are kept and logs refresh using checksum comparison, including
replacement and truncation. **This can transfer complete, large logs.** Use
[`asl fetch`](logs.md) for selected, bounded execution evidence instead. Neither
operation transfers application-owned scientific datasets/results. Sync does not
upgrade software, alter SSH configuration or run on a jump-only gateway.

Python clients can import the supported `sync_machine` from `autoslurm.sync`
and call `sync_machine(machine_name="rusty")`.
It returns `None` with progress text on success, and raises on failed import or
transfer with diagnostics and any completed effects retained. `--debug` on the
CLI includes the chained cause. A successful sync is a tracking reconciliation,
not scientific validation or proof that every scheduler row is available.
