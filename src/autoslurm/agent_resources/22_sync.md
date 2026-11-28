# Sync: native tracking into a controller view

Interaction: reconcile native cluster runs into the workstation's tracking view.
Use `from autoslurm.sync import sync_machine`, then
`sync_machine(machine_name="rusty")`, or `asl sync rusty`. This explicit
operation selects the workstation profile, SSH alias and remote AutoSlurm root.
The cluster's native profile name can differ (for example rusty-local). Never
rename profiles, edit SSH configuration or silently fall back to local execution.
A jump-only gateway cannot host AutoSlurm, helpers or state.

Outcomes: return None/progress on success; raise DiagnosticError on adopted
failures, with completed/partial directory and tracking effects. The CLI renders
once and exits 1; --debug retains causes. Healthy records may have imported even
when another fails. Read diagnostics before proceeding; failed sync never
justifies submission or retry. Scientific completion is application-owned.

Import contract:
- Stage remote job snapshots; import only submitted native execution views under
  the selected root. Skip drafts, untracked legacy files and other-machine views.
- Read the exact linked receipt through the existing 1 MiB/30-second adapter.
  Validate submission identity, definitions, producing paths, dependencies and
  known IDs. Never infer identity or a receipt from a bundle name/latest/index.
- Match existing controller views by submission ID, retaining their paths and
  campaign references. Otherwise publish a normal snapshot with the selected
  remote transport. Preserve producing paths and scheduler IDs. The saved receipt
  retains source identity in additive sync_origin metadata (protocol 1 unchanged),
  so later refresh validates source identity before projecting the local view.
- Verified old raw copies are repaired with original records retained under the
  local storage root's sync_backups/<submission-id>/. Verified duplicates leave
  normal discovery only after canonical publication, retaining backups. Repeat
  unchanged syncs create no new attempts/backups. These are package-owned records;
  clients must use public inspection rather than parse or rewrite them.
- Missing/corrupt/conflicting evidence, filename collisions, changed transport or
  known IDs stop that import and preserve local evidence. Orphan raw copies are
  reported and retained. Transport failures stop remaining receipt reads for that
  machine. Publication is not a global transaction; explicit sync after diagnosis
  can reconcile an interrupted receipt/snapshot pair. No automatic retry/recovery.

After import, use inspect_bundle, inspect_logs/fetch_run or ordinary status/logs/
fetch CLI selectors. Collection uses the recorded producing paths via the selected
SSH alias, never local Slurm merely because the cluster profile was local. Keep
exact references: row indices differ between installations, and collection times
can differ. Existing controller receipt refresh uses the same projection owner.
The workstation needs 0.2.0.dev18+ to refresh these imports; no new cluster helper
is needed, but native records must already contain receipts/execution metadata.

Scope: scripts still mirror with ignore-existing and out logs with checksums,
including complete log files. Sync is not bounded retrieval; prefer fetch_run for
selected bounded evidence (18_fetching). It does not transfer application results,
change source records/config, install software or submit/cancel jobs. No extra ACP
sync action is added. Offline regressions cover differing names, native/controller
runs, status/log/cancel/fetch routing, partial IDs, repeat sync, raw repair,
duplicates, conflicts and interrupted publication.
