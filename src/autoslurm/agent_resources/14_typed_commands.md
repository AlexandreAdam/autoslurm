# Typed command authoring and saved-job validation

Use this recipe when building a client application or revalidating its saved
jobs. This recipe ships with the package. Retrieve it with
`asl agent --sections 14_typed_commands` or ACP
`{"action":"gather_context","task":"integrate"}`.

## Supported public interface

```python
from autoslurm import CommandContract, CommandOption, from_typer
```

`CommandContract` is framework-free. `from_typer` derives one from a trusted,
already-imported lightweight Typer app. Install `autoslurm[commands]` on the
authoring machine for the supported Typer 0.27 adapter. No Typer import occurs
merely by importing AutoSlurm. Ordinary scientific commands need their own CLI
dependencies, not AutoSlurm, to execute.

Declare one typed command per job kind, with scalar named settings: native int,
finite float, nonempty str, or default-off bool. Prefer Typer, explicit required
options and static defaults. Keep imports free of scientific execution/submission.
The narrow adapter requires one plain leaf app with `add_completion=False`;
it rejects groups/app callbacks, custom flags/classes/contexts, option callbacks,
prompts/env/default factories, custom parsers, forward annotations, optional/list/
tuple values and default-on booleans. It does not parse help or execute callbacks.
Unsupported/version-mismatched declarations fail explicitly; no guessing/fallback.

For an unsupported CLI framework, declare a CommandContract with CommandOption
values explicitly and check that contract against the real parser in client tests.
Ordinary raw `script`/`script_args` authoring remains supported; it does not gain
automatic signature validation.

```python
command = CommandContract("science-fit", (
    CommandOption("seed", "int", required=False, default=17, minimum=0),
    CommandOption("verbose", "bool", required=False, default=False),
))
```

## Build and save readable jobs

```python
import typer
from typing import Annotated
from autoslurm import from_typer, save_bundle

app = typer.Typer(add_completion=False)

@app.command()
def fit(input_file: Annotated[str, typer.Option()],
        output_dir: Annotated[str, typer.Option()],
        seed: int = 17, label: str = "trial", verbose: bool = False):
    pass  # Call the client's scientific function here.

command = from_typer(app, script="science-fit", input_args=("input_file",))
job = command.job(name="fit", script_args={
    "input_file": "data/measurements.json", "output_dir": "study/fit",
    "label": "pilot's first run",
}, slurm={"time": "00:05:00"})
planned_path = save_bundle({"fit": job}, "study")
```

`describe()` returns plain option/default/range/path metadata. `validate(values)`
fills current defaults for a new job; `job(...)` does the same and accepts explicit
`dependencies=("parent",)` plus Slurm settings such as `array: "0-3%2"`. Graph,
resource and path/readiness checks remain with the normal bundle engine. Futures
such as a reducer's parts directory use `path_args`; files that must already
exist use `input_args`. `output_dir` is automatically a result path.

Every setting stays individually named in `script_args`, including defaults and
False. Use a CSV scalar for lists; never hide settings in JSON/base64/config-file
payloads. Strings are literal: spaces/quotes/metacharacters are quoted after path
resolution; do not pre-escape. Control characters fail locally. True emits a flag,
False is omitted; default-on booleans are unsupported. Runtime expressions inside
values do not expand: use a CLI environment default or `runtime_environment`.
Declare relative application paths; AutoSlurm owns selected-machine root discovery.
The fixed `script` prefix contains no job-specific shell expressions.

## Revalidate exact saved settings

```python
from autoslurm import load_bundle_from_path

jobs, _, _ = load_bundle_from_path(planned_path)
checked_job = command.validate_job(jobs[0])
```

Supply the current trusted declaration explicitly. `validate_job` checks command
text, declared input/result roles, required/unknown/type/range rules and the full
saved option set, returning a detached copy. Missing options are errors, even if
the new command provides defaults: rebuild a new definition explicitly after
review. Changed defaults do not replace explicitly saved values. A changed command
or path role is a mismatch. Missing/unsupported declarations require client action;
AutoSlurm never imports an arbitrary module or guesses a replacement contract.

No schema, callback or declaration identity is added to saved JSON. Revalidation
proves compatibility with the supplied current contract, not identity with the
historical command or installed cluster software. It cannot detect science changes
behind unchanged options. It neither writes the bundle nor selects a new machine,
checks remote files, updates software, or authorizes retry. Submission snapshots
remain protected by the normal engine; validating their settings does not make
them new submission definitions.

## Preview, submit and inspect

After client revalidation, use the existing public operations:

```python
from autoslurm import preview_bundle, submit_jobs, SubmissionError, inspect_bundle

preview = preview_bundle(planned_path, machine="selected-profile")
# Operator reviews preview before the explicit submission action.
try:
    receipt = submit_jobs("study", bundle_path=planned_path, machine="selected-profile")
except SubmissionError as error:
    receipt = error.receipt  # Preserve accepted IDs/partial or uncertain evidence.
    raise
view = inspect_bundle(receipt_path=receipt["receipt_path"], refresh=False)
```

Preview/readiness may contact a remote profile; builder and revalidation are pure.
No new scheduler or automatic submit action is hidden in the builder. Preview and
submission use the same literal compiler. Record exact paths/receipt IDs and use
bounded `inspect_logs` or `asl logs` for producing task evidence. An accepted
receipt is not scientific success. Never blindly retry an unknown acceptance;
arrays retain original task indices and reducers validate their outputs. Dependent
jobs default to kill-on-invalid-dep=yes, with explicit per-job overrides retained.

Expected authoring mismatches raise ValueError with the option/field; correct the
declaration/settings and rebuild deliberately. No bundle write, scheduler call,
application callback or preparation occurs during these checks. Scientific CLI
validation and output validity remain client responsibilities. ACP `schedule`
only saves a supplied raw dictionary: build/revalidate through these Python APIs
first. No Python object is serialized into an ACP request.
