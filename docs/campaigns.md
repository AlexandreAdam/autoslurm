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
contract. Inspection and fetching follow in a separate slice.

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
