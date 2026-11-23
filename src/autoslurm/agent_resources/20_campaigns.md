# Campaign records: exact ordinary runs on this controller

Implemented: public create_campaign(name, members, context=''), load_campaign(name),
list_campaigns(); CLI campaign create/list/show; ACP actions with the same names.
Inspection/fetch are added separately; do not infer availability from the design.

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

No global scientific task mapping is stored in this first schema: report member/
job/task observations, not a fabricated global science-progress count. Task
partition validation, coordinated submission and retries remain later work.
Use ordinary readable script_args and supported typed CLI validation in members;
campaign context is a rationale, never an opaque replacement for job settings.
