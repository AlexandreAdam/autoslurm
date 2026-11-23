# Campaign records: exact ordinary runs on this controller

Implemented: public create_campaign(name, members, context=''), load_campaign(name),
list_campaigns(); CLI campaign create/list/show; ACP actions with the same names.
Inspection/fetch are implemented through the public operations described below.

**No cross-machine dependencies.** Build an ordinary single-machine bundle for
each member. Job dependencies must stay inside that bundle; never reference a
different member's job or pass its Slurm ID to another machine. Campaigns do not
gate or submit downstream work. The client/operator verifies prerequisite
completion, scientific outputs and data availability before explicitly submitting
any downstream bundle. Scientific splitting and data movement remain client-owned.

Whole-campaign status: `asl campaign inspect NAME`; bounded logs across members:
`asl campaign fetch NAME`. `asl status` / `asl logs` remain individual-run tools.

```python
from autoslurm import create_campaign
campaign = create_campaign('grid-refinement', [
    {'member_id': 'rusty-share', 'machine': 'rusty', 'bundle_path': exact_rusty_bundle},
    {'member_id': 'popeye-share', 'machine': 'popeye', 'bundle_path': exact_popeye_bundle},
], context='Split the selected targets across two clusters.')
```

Use the exact saved or submission tracking bundle paths returned by supported
APIs. Each job records its machine explicitly. No name/date/latest inference.
The returned campaign_path is a controller-local locator, not an application path.

`asl campaign create NAME --member MEMBER MACHINE BUNDLE_PATH` accepts --member
once/twice; add --context TEXT or --json. Bare campaign prints help. list and show
are offline. Creating a group never submits, pulls, installs or copies files.

Immutable format_version=1, revision=1 record: campaign_id (generated UUID hex),
name, created_at (timezone ISO timestamp), context and members. Each member has
member_id, machine, bundle_ref and bundle_sha256. bundle_ref is relative to the
campaign directory, may include .. to an existing definition, and is not a
client results-root path. No machine routing is changed by resolving the record.
One/two members with distinct identities/machines/paths. Read limit 64 KiB per
campaign, 8 MiB per bundle; context 8 KiB. Names are bounded filesystem labels.

Digests use canonical parsed JSON: formatting alone does not change identity.
For receipt-bearing tracking bundles, changing outcome/id/error facts does not
change definition identity, but immutable submission_id/receipt_path links do.
For legacy snapshots without those links, saved IDs remain part of identity.
Job options, graph and recorded execution metadata stay fingerprinted.

Changed definitions require a new campaign name/identity; no edit/overwrite,
automatic import, schema migration, copies or campaign-attempt journal exists.
Unknown versions/keys fail visibly and preserve the source record. Failed list
entries retain diagnostics beside healthy neighbours. Loading the group does
not require that all member files remain readable; inspection diagnoses them.
Removing a bundle with clean does not delete/rebuild its campaign reference.
Records remain on their controller; a gateway login does not transfer them.
Alexandre's `flatiron` gateway is a jump point only, never a controller, helper
or campaign-storage host. Use a verified laptop route or a permitted cluster
login node with explicit record access; do not assume cross-cluster connectivity.

No global scientific task mapping is stored in this first schema: report member/
job/task observations, not a fabricated global science-progress count. Task
partition validation, coordinated submission and retries remain later work.
Use ordinary readable script_args and supported typed CLI validation in members;
campaign context is a rationale, never an opaque replacement for job settings.


## Coherent observation and execution evidence

Public inspect_campaign(name, refresh=True, member=None, job_name=None,
task_index=None, timeout=120) and fetch_campaign with the same selectors plus
tail=40, max_log_bytes=65536, max_logs=20, max_total_log_bytes=262144, stream='both'.
CLI campaign inspect/fetch NAME supports --cached/--json/--member/--job/--task/
--timeout; fetch also --tail/--max-log-bytes/--max-logs/--max-total-log-bytes/--stream.
ACP inspect_campaign/fetch_campaign accepts these public Python parameter names.

Use member_id before selecting job/task; task_index is the member's declared
Slurm index. Validate selectors and bounds before receipt refresh or transport.
Each selected member is isolated: state available/partial/unavailable/not_attempted,
view with original run/receipt/status/log evidence and optional diagnostic.
The campaign state observed/partial describes observation completeness, not compute
or scientific success; ACP success can contain a partial result. CLI exits 1 for
partial evidence while preserving JSON. Bare campaign prints current commands.

Result includes campaign identity/revision/rationale, collected_at, cached flag,
member views, fresh_task_counts and last_known_task_counts. Last-known member
state/counts/time remain separate from current observations and may be stale.
Counts include all member jobs, not unique science tasks. Narrow selectors reduce
detail; do not reinterpret the counts as scientific-output validation.

Fetch refreshes exact receipt links before scheduler/log collection, retaining
known IDs and readable neighbours on failure. No latest selection, results fetch,
software update, retry or alternate profile. Submitted members without producing
metadata remain unavailable rather than falling back to current profiles.

Cached mode does no network, receipt refresh/projection, source-log reads or cache
writes. It reads controller-local definitions, receipts and existing caches. No
aggregate state database/cache is introduced. The optional last_observed.jobs
field in run caches preserves previous task evidence across failed refreshes;
old caches remain readable. Missing cache is never fabricated as empty success.

Limits: at most two members; command deadline up to 120 seconds with fair per-member
allowances; OS filesystem calls are not forcibly interrupted. Whole-campaign
log caps 20 files/262144 returned UTF-8 bytes, each at most 65536. Byte/log quotas
can narrow individual reads. Existing receipt bounds remain 1 MiB/30 seconds.
200 jobs/10000 declared tasks per member, bounded 32-bit indices; response task
details max 250 per member/current or prior view and 2 MiB compact UTF-8 JSON, with omission
markers. IDs/counts survive detail compaction. Narrow selection for fuller evidence.

Changed definitions are not attributed to the campaign. If mutation occurs during
observation, unverified_observation retains minimal IDs separately for diagnosis.
Expected diagnosed member failures preserve neighbours; new coordinator code
propagates unexpected bugs/interrupts. Existing scheduler/log adapter diagnostic
adoption remains scheduled under MVP10; this does not claim universal error parity.


fresh_task_counts includes only fully fresh members; partial-member observations
remain in their views. A zero fresh count is not proof of zero completed work.
last_known_task_counts can include stale observations and is not a new scheduler
snapshot. Inspect per-member times/errors before deciding what to do next.
