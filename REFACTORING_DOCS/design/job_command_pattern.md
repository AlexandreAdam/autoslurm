# Readable command and job authoring pattern

## Status and purpose

**Investigation and proposal for review, 2026-11-13 (DOCS.3).** Alexandre wants
less integration work for agents while preserving readable settings, commands
and Slurm scripts for human cluster operation. The accepted requirement is this
readability/friction goal. The API sketches and architecture choices below are
proposals, not implemented or accepted interfaces. DOCS.1's scalar/CSV/default-off/
safe-word preference remains in force. No renderer or execution behavior changes.

**Planning update (PLAN.1):** the user requested this work as MVP9, followed by
MVP10 error handling. Delivery scope is below; implementation has not started.
The earlier investigation's hypothetical APIs are still not supported interfaces.

This follows the [current interaction map](../interaction-map.md#job-script-interactions-current-code-and-design-review).
It compares AutoSlurm's current parser/renderer, its argparse reference client,
and Gaia's existing typed task registry/CLI/bundle builder. Gaia is reference
evidence only; this task changes no client application or cluster installation.

## Recommended pattern

**Declare a task's command interface once. Build ordinary readable jobs from it.
Save the named settings. Preview the exact resolved invocation. Submit explicitly.**

| Layer | Owns | Human/agent result |
|---|---|---|
| Scientific application | Computation, scientific validity, input data interpretation and domain checks | Independently callable scientific code |
| Lightweight typed command | Named options, types, defaults, constraints and the ordinary CLI entry point | A command that works manually and under Slurm |
| Client's workload builder | Parameter choices, studies/sweeps, resources, dependencies and output ownership | Flat readable job definitions |
| AutoSlurm command adapter/compiler | Shared command metadata, supported option validation, literal argument encoding and shell rendering | Consistent JSON, preview and executable invocation |
| Existing AutoSlurm engine | Machine/path binding, staging, dispatch, durable receipts and bounded inspection | One execution/observation path for terminal, Python and agents |

The client keeps its science and workload policy. AutoSlurm supplies the reusable
argument/bundle plumbing rather than requiring each agent to write its own
registry, type checker, flag mapper and shell formatter. A planning-time Python
reference can identify a command definition; it must never become a serialized
callback or a new compute-node execution mode. Compute nodes still run normal
installed commands/scripts in prepared environments without an agent process.

## Walkthrough of the proposed experience

### 1. The application has an ordinary typed command

For example, an existing Typer application can expose `science-tool fit` through
a lightweight wrapper with a signature like:

```python
def fit(
    input_file: str,
    output_dir: str,
    seed: int = 17,
    batch: int = 4,
    require_gpu: bool = False,
):
    # Import heavy scientific dependencies only when this command runs.
    from .science import run_fit
    return run_fit(input_file, output_dir, seed, batch, require_gpu)
```

This is a signature sketch, not a complete Typer registration example. The
actual CLI explicitly declares all parameters as named options (including
required ones), registers `fit` as a subcommand and can declare `batch >= 1`.
Typer remains preferred for Alexandre's clients, but the core contract is plain
data. Scientific code and CLI execution do not require AutoSlurm imports.

Declare options/defaults once in the command interface and derive scheduling
metadata from that interface. Avoid a hand-maintained second schema listing the
same names/types/defaults. Domain checks can be shared pure application validators;
parsing types alone does not validate scientific input contents or computation.

### 2. The workload builder names values and resources

The following is **hypothetical API notation**, not a current importable helper:

```python
# fit_command is obtained once from the client's lightweight typed command.
# It knows the target command, options/defaults and declared path roles.
job = fit_command.job(
    name="fit",
    script_args={
        "input_file": "data/measurements.json",
        "output_dir": "study/fit",
        "seed": 17,
        "batch": 4,
        "require_gpu": False,
    },
    slurm={"cpus_per_task": 4, "mem": "8G", "time": "00:30:00"},
)
```

The helper would validate before any bundle write, fill supported static defaults
and produce a normal job mapping for existing `save_bundle`. The application
still chooses resources, graph edges and unique outputs. Machine paths, SSH,
Slurm dispatch and receipts are not client-side reimplementations. The adapter
is created once per command and reused for every job in a sweep.

Its result remains readable using existing field names:

```json
{
  "fit": {
    "name": "fit",
    "script": "science-tool fit",
    "input_args": ["input_file"],
    "script_args": {
      "input_file": "data/measurements.json",
      "output_dir": "study/fit",
      "seed": 17,
      "batch": 4,
      "require_gpu": false
    },
    "slurm": {"cpus_per_task": 4, "mem": "8G", "time": "00:30:00"}
  }
}
```

Keep the named mapping authoritative. Any generated argument tokens/script are
derived execution evidence; callers do not independently edit both versions.
False stays visible in JSON, with omission justified by the validated default-off
CLI. Data-file paths are explicit inputs, never a hidden whole-job config payload.

### 3. All authoring routes use the same contract

| Caller | Proposed route |
|---|---|
| Human terminal user | Type application options through an AutoSlurm authoring adapter; parse them with known command metadata and retain typed settings |
| Python workload builder | Supply native values; shared validation rejects wrong types/names instead of silently stringifying/coercing them |
| Client-owned plan/submit CLI | Call the same builder and save/preview/submit operations |
| Agent | Discover the command contract/recipe, fill named values, read field-specific validation errors and retain exact bundle/receipt references |
| Existing saved definition | Load plain data, check its available command contract and use the same compiler; never need to execute a saved Python object |

The contract needs command tokens, names/flag spelling, supported scalar types,
defaults/requiredness and path roles. It must be available when a saved definition
is loaded, not only as a transient Python object in the process that created it.
How its plain metadata/identity is retained is an open format decision; no new
job fields, record versions or format migration are introduced by this study.
An initial builder slice can preserve today's job JSON and accepted argument
profile; complete saved-definition validation remains explicitly incomplete until
the contract's durable lookup/recording boundary is agreed.

Raw external commands without a known contract remain a deliberate compatibility
case: structural/shell/path checks cannot certify their option signatures. An
agent must see that semantic validation is unavailable, not invented success.
Source files (`python script.py`), modules and installed entry points can share
this command interface; their code must already be available on the target.

### 4. Human review shows the effective execution

The proposed preview should show the exact selected bundle, target machine/SSH
alias, environment, account/partition, CPU/GPU/memory/time, cwd, requested and
resolved paths, relevant code observations and every effective setting. It then
shows a directly readable application command, for example:

```sh
science-tool fit \
  --input-file=/cluster/data/data/measurements.json \
  --output-dir=/cluster/data/study/fit \
  --seed=17 \
  --batch=4
```

Explain that `require_gpu=false` uses the command's known default rather than
silently hiding it. This illustrative path uses the configured results root;
applications continue supplying relative paths. Normal command execution need
not load a whole AutoSlurm JSON document or bootstrap through an opaque runner.
The generated script additionally shows environment/cwd and SBATCH directives.

The readable summary and script must be projections of the same prepared job.
Distinguish locally validated fields, target observations and unknown checks;
displaying account/partition does not establish scheduler permission. Preview is
not submission and existing target path checks may require SSH. Explicit submit
uses an exact saved reference and returns the existing receipt/failure contract.
No preview can guarantee mutable code/environment remains unchanged in the queue.

## Validation and ownership boundaries

1. **Before save:** validate supported command names/options, required values,
   strict native Python/JSON types, defaults, constraints and literal encoding.
   Terminal input starts as text and needs declared conversion; Python input is
   already typed and must not turn True into integer 1 or silently truncate a
   float. Reject unsupported parameter forms explicitly.
2. **During target preparation:** resolve declared paths/cwd and environment for
   one machine, validate target availability and build the command/script through
   one compiler. Local CLI filesystem validators must not reject a remote path
   merely because it does not exist on the laptop.
3. **At application execution:** retain normal CLI and scientific/data validation.
   Availability and code can change after preview. Optional pure cross-field
   validators can be shared; arbitrary callbacks must not run implicitly while
   an agent merely inspects or validates a job.
4. **After submission:** preserve receipt uncertainty/accepted IDs and status/log
   freshness. A compiler, metadata or observation failure never triggers another
   host, automatic submission retry or opaque fallback execution mode.

A useful error names the exact location and repair, for example
`jobs.fit.script_args.batch: expected integer >= 1; received "four"`.
An agent should fix that value without reverse engineering shell output or
editing generated scripts. Scientific result validation remains client-owned.

## Findings from a local design experiment

The disposable probe `.development/test-runs/job-interface-investigation.py`
ran against the existing isolated test environment (Typer 0.27.3). Its JSON report
is `.development/test-runs/job-interface-investigation.json`. This is an
investigation, not a new supported adapter or a production test-suite change.

- Command metadata exposed names, positive/negative flags, defaults and the
  integer range constraint without invoking scientific code. Parsing rejected
  unknown names, a wrong integer type and an invalid range; it filled defaults.
- Today's scalar/default-off/safe-word values round-tripped through the actual
  renderer and CLI parser to the requested values. A literal token containing a
  space parsed successfully, while today's unquoted rendering split it.
- A repeated option parsed successfully; today's space-list output failed.
  The parser's intermediate repeated value was a tuple, showing that normalized
  plain-data types need an explicit boundary rather than leaking parser objects.
- Omitting False for a default-on option produced True. This confirms why current
  default-off guidance is necessary until a broader boolean contract is approved.
- Parsing without invoking the command body still executed a parameter callback.
  It is not automatically pure validation. Contract inspection must not run
  arbitrary client callbacks, eager options, prompts or dynamic default code.
- Python signature binding accepted a wrong annotated value type, and parser
  integer conversion accepted True as 1. Binding and conversion therefore do not
  replace strict native-value validation in a Python/JSON builder.
- The first Click-export assumption failed: this Typer had no separate Click
  distribution metadata and its command had no to_info_dict method. Names/types
  were inspectable, but this does not prove a stable general metadata adapter.

Typer's [official vendored-Click guidance](https://typer.tiangolo.com/tutorial/click/)
explains why treating every Typer command as an external Click command is not a
supported generic strategy. A narrow optional adapter needs explicit version/
capability checks and behavioral fixtures. Core jobs and saved data should not
contain framework objects. Python [signature binding](https://docs.python.org/3/library/inspect.html#inspect.Signature.bind)
can check name/argument binding; it does not itself enforce annotated value types.

Gaia independently demonstrates typed signatures feeding task metadata, a CLI
and pre-save validation. The reusable concept is that common declaration; its
TaskContext, run/stage names, scientific provenance and output layout remain
Gaia's policy, not new mandatory AutoSlurm abstractions.

## Proposed small refactor sequence

| Slice | Concrete outcome | Boundary |
|---|---|---|
| A. One-command builder proof | Declare one lightweight typed command once, derive supported metadata, validate native named values before save, emit today's job dictionary and show the equivalent CLI | Reference client and accepted scalar profile only; no public API claim or new runtime |
| B. One argument compiler | Reuse shared preparation to build literal argument tokens and shell-render them; preview, submission and local smoke agree on invocation | Keep existing machine/receipt engine; agree any persisted evidence/format change first |
| C. Shared authoring adapters | Make Python, terminal and agent authoring use the same supported metadata/validator; stop relying on help-text guessing for those commands | Optional Typer adapter plus explicit compatibility boundary, no universal parser framework |
| D. Broader values, if approved | Add per-option repeated/tuple/boolean semantics and safe strings with spaces, with true round-trip tests | Amend DOCS.1 deliberately; do not introduce blanket job-wide styles or unsupported CLI guesses |

The DOCS.3 investigation alone did not authorize these production changes. The
subsequent user request schedules the narrow MVP9 scope below; broader slices
and saved-format changes still need their own explicit boundary.
Verify exact equivalence from named values -> generated tokens -> actual parser,
with default materialization, path binding, unsupported forms, invalid options,
non-executing discovery, arrays/dependencies and preserved receipt behavior.
Human acceptance includes understanding a job from JSON/preview/script without
an agent session or reading private modules.

## MVP9 delivery scope (planned)

The useful first release is a small shared authoring/compiler path, with ordinary
scientific commands at execution time. Deliver tasks MVP9.1–3 in PLAN order:

1. One supported lightweight typed declaration feeds the CLI and a builder. Use
   plain metadata for named int/float/str/default-off-bool options and static
   defaults; reject unknown names, wrong native types and unsupported constructs.
   A narrow optional Typer adapter can inspect supported metadata, with version/
   capability tests. Never run the command or its option callbacks for validation.
2. Compile named values to literal tokens after existing path resolution, and
   shell-quote every literal value at the final renderer. Reuse preparation for
   preview and actual scripts. The contract defines the supported boolean flag
   semantics; it must not guess a parser's behavior from a Python annotation.
3. Demonstrate the shared builder through Python and a client CLI in the reference
   application, with accurate human/agent recipes and pre-save validation. Existing
   raw-script jobs still use the same engine; do not require rewriting all clients.

The bundle keeps explicit named settings and supported defaults visible. The
first release retains scalar/CSV/default-off guidance; first-class repeated lists,
tuples and default-on/negated booleans remain a later extension. This avoids
adopting blanket `list_style`/`bool_style` switches before there is a per-option
contract. Ordinary strings containing spaces should become safe literal values
through the compiler; amend the current safe-word guidance only when implemented
and verified. Do not serialize functions/parser objects or hide settings in blobs.

Before a public builder is shipped, settle helper syntax, how a saved job is
validated if its command declaration is unavailable/changed, and whether any plain
contract metadata must be retained. Prefer existing job fields and an explicit
unsupported/unknown result; no silent import/lookup of arbitrary client code.
Any persisted addition/change gets a release/data-retention decision first.

Acceptance: strict native-value/default/name validation, no callback/science work,
literal-token-to-real-parser round-trips, preview/submission equality, unchanged
path/array/dependency/receipt behavior, and a readable JSON/script walkthrough.
Tests use a disposable local reference CLI and mocked Slurm/transport. Start with
one command; additional frameworks or general signature inference are not gates.

## Open decisions and log

- Is the small optional command adapter plus ordinary command execution the
  preferred first proof? Select its syntax only after reviewing the walkthrough.
- How should a saved definition retain/find plain command-contract metadata and
  report changed/unknown command versions? Follow existing release/data rules.
- Which validations are declarative and pure, and which explicitly remain
  application runtime checks? Define unsupported adapter behavior before shipping.
- Should broader value support follow the compatible scalar proof? The accepted
  readability principle and current safe scalar guidance remain unchanged today.

**2026-11-13, PLAN.1:** user requested two next MVPs, command arguments then error
handling. Scheduled a narrow scalar contract/compiler/reference-client release
as MVP9; API sketches remain proposed and broader value styles stay deferred.
No runtime or application changes in this planning task.

**2026-11-13:** read source and client examples, checked primary framework docs,
ran the isolated design experiment, and recorded proposed interface/validation/
human-review criteria. No package installs, runtime changes, saved job edits,
cluster contact or full application test rerun. Last code baseline: 576 passing
offline tests from MVP7.2f. Documentation/link/example checks only for this study.
