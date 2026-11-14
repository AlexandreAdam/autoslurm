# One command declaration, readable jobs

A scientific command should be useful directly in a terminal and easy for a
client or agent to put into a bundle. AutoSlurm's command contracts connect those
uses: validate named settings once, save the effective values visibly, then use
the ordinary path, preview and submission engine.

The scientific command remains responsible for computation and output validity.
The builder runs on the workstation or login host. Compute jobs execute the
installed command in an already prepared environment; they do not read bundles,
discover contracts or install packages.

## Build a job from your CLI

With AutoSlurm installed, its `commands` extra supplies the supported Typer 0.27
adapter. Keep each job kind as one lightweight leaf app with static scalar
options and `add_completion=False`. A client can then use:

```python
from autoslurm import from_typer, save_bundle
from my_science.cli import fit_app

command = from_typer(fit_app, script="science-fit", input_args=("input_file",))
job = command.job(name="fit", script_args={
    "input_file": "data/measurements.json",
    "output_dir": "study/fit",
    "label": "pilot's first run",
}, slurm={"time": "00:05:00"})
path = save_bundle({"fit": job}, "study")
```

The saved `script_args` includes supported defaults as well as the supplied
values, including false booleans. `describe()` exposes plain option metadata.
Unknown names, wrong types, missing requirements or unsupported parser features
fail locally before the client saves the job. Spaces and quotes remain literal
values; the shared compiler handles shell quoting after machine-path resolution.
Use CSV strings for lists and default-off boolean flags.

`CommandContract` and `CommandOption` also support explicit metadata for another
CLI framework. The client must keep it aligned with the actual parser. Existing
raw script/dictionary authoring stays available; AutoSlurm does not infer a
complete arbitrary CLI signature from its help text.

## Return to a saved plan

```python
from autoslurm import load_bundle_from_path, preview_bundle

jobs, _, _ = load_bundle_from_path(path)
checked_job = command.validate_job(jobs[0])
preview = preview_bundle(path, machine="selected-profile")
```

Supply the current trusted command explicitly. Revalidation returns a copy and
checks command text, path roles and every saved setting. If the command adds an
option, a missing saved value is an error even when a default exists; review and
build a new definition deliberately. Existing explicit values are preserved when
defaults change. No old file is modified, and no application module is imported
automatically from saved data.

This check establishes compatibility with the contract supplied now. It cannot
certify the historical command, scientific semantics or the installed cluster
version. There is no new persisted contract schema or automatic declaration
lookup. Preview still checks selected-machine paths/readiness and may use SSH;
contract construction and saved-job validation do not contact the cluster.

## Arrays, dependencies and operator review

`command.job(..., slurm={"array": "0-3%2"})` creates an ordinary array job.
Use `dependencies=("shards",)` for a reducer. Required inputs must exist before
submission; future upstream outputs use declared `path_args` instead. Original
task indices, dependency IDs, kill-on-invalid-dep defaults and receipts are
handled by the existing engine.

The [reference client](../examples/reference_client/README.md#typed-command-authoring)
demonstrates public Python and `science-jobs plan/validate/preview` routes through
four shards and a reducer. The CLI never submits automatically. An operator
reviews the preview and explicitly submits; retain the exact receipt, distinguish
acceptance from scientific success, and inspect bounded producing logs. An
uncertain submission must be investigated before any retry.

Agents can retrieve the self-contained installed recipe with
`asl agent --sections 14_typed_commands` or ACP `gather_context` with task
`integrate`. The [full recipe](../src/autoslurm/agent_resources/14_typed_commands.md)
lists supported and rejected declarations and gives the outcome/failure contract.
Typer is optional; the core package and explicit contracts work without it.
