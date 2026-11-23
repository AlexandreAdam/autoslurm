# Campaigns across machines

A campaign groups exact ordinary runs while each run still belongs to one machine.
Your application decides how to split the science; no scientific script changes
are required just to group runs.

```sh
asl campaign create grid-refinement \
  --member rusty-share rusty /path/to/exact-rusty-bundle.json \
  --member popeye-share popeye /path/to/exact-popeye-bundle.json \
  --context "Split the selected targets between the clusters."
asl campaign list
asl campaign show grid-refinement --json
```

These commands are offline and do not submit or update software. Use paths returned
by existing bundle/submission operations; subsequent operations select the saved
campaign name. Public create_campaign/load_campaign/list_campaigns and ACP actions
provide the same data. The installed 20_campaigns agent recipe documents the
contract. Inspection and fetching use the same public member evidence, as described below.

The first schema groups one/two members with distinct machine names and exact
bundle definitions, preserving recorded transport and relative application paths.
An immutable campaign holds readable context and fingerprints, not copies of code,
logs or datasets. Receipt-bearing mutable outcomes may evolve; receipt identity
and job settings remain pinned. Changed definitions need a new campaign name.
Unknown/broken records are retained and visible; no automatic history migration.
There is no global scientific task mapping, submission or retry engine in v1.

Campaign records belong to the controller that created them. At home, Alexandre's
current route is ssh flatiron, then ssh rusty/popeye from there. An interactive
gateway shell does not give laptop commands this route or move their records.
See [connection checks](ssh_configuration.md#check-access-without-an-interactive-prompt).
No gateway configuration or authentication is automated.

Cleaning a member bundle removes its usual navigation; its campaign reference
remains. Campaigns never reconstruct deleted definitions from a receipt or silently
substitute a newer bundle. Scientific files remain application-owned.


## Inspect and fetch across machines

```sh
asl campaign inspect grid-refinement
asl campaign inspect grid-refinement --cached
asl campaign inspect grid-refinement --json
asl campaign fetch grid-refinement --member rusty-share --job shards --task 17
```

Use inspect_campaign/fetch_campaign in Python or ACP actions with the same names.
Select a member before narrowing to a job/task. Task is the member's declared
Slurm array index; there is no global scientific index translation in this version.

Fresh inspection queries each selected member's recorded producing machine.
Fetching first refreshes its exact linked receipts, then uses the existing status
and bounded log pipeline. One unavailable member leaves the other visible. Current
and last-known task counts, state, timestamps and errors stay separate; known old
progress is never presented as freshly verified. Counts include supporting jobs
and are scheduler observations, not validated scientific results.

`--cached` performs no network, receipt refresh/projection, source-log reads or
cache writes. Missing/stale/failed cached evidence is explicit. A partial view is
still returned as structured data; the CLI exits 1. Unknown/bad selectors fail
before connecting. Grouping a legacy submitted bundle without producing metadata
is allowed, but observation reports it unavailable rather than guess its route
from a profile that may have changed.

The campaign deadline defaults to 120 seconds, with fair time allowances per
member and remaining time passed to existing command adapters. It bounds command
admission/processes; it cannot interrupt a blocked operating-system filesystem
call. Fetch defaults cap the whole campaign at 20 log excerpts and 256 KiB of
returned excerpt content. --max-logs, --max-log-bytes, --max-total-log-bytes,
--tail, --stream and --timeout can narrow these limits. Quotas may reduce the bytes
available per excerpt; no dataset or whole-directory transfer is added.

A member currently supports up to 200 jobs and 10000 declared tasks, with bounded
32-bit nonnegative array indices. Responses include at most 250 task details per
member/current or prior view, with omitted counts and a details_truncated marker;
aggregate counts remain. Select one task to inspect it directly. Compact UTF-8 context JSON is
bounded at 2 MiB; unusually large detail is compacted while IDs/states/counts remain.

A changed definition or receipt link is not silently followed. Source changes
during observation are reported with unverified minimal ID evidence, which is
not attributed to the campaign's totals. Removing a member bundle leaves an
unavailable reference. No automatic repair, resubmission or results retrieval.
