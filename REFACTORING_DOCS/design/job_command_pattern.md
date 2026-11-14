# Readable command and job authoring pattern

## Status and purpose

**Investigation and proposal for review, 2026-11-13 (DOCS.3).** Alexandre wants
less integration work for agents while preserving readable settings, commands
and Slurm scripts for human cluster operation. The accepted requirement is this
readability/friction goal. The API sketches and architecture choices below are
proposals, not implemented or accepted interfaces. DOCS.1's scalar/CSV/default-off
preference remains; MVP9.2 now replaces the safe-word restriction with literal
quoting. Historical investigation text below describes the renderer at DOCS.3.

**Planning update (PLAN.1):** the user requested this work as MVP9, followed by
MVP10 error handling. Delivery scope and implementation evidence are below.
The earlier investigation's hypothetical APIs are still not supported interfaces.

**MVP9.1 implemented locally, 2026-11-13:** internal command-contract and optional
Typer adapter modules now prove one declaration feeding typed validation and the
ordinary saved-job/preview/submission path. The implemented boundary is documented
below. MVP9.2 now implements literal compilation; public integration remains MVP9.3.
The original walkthrough remains design notation rather than a supported API.

**MVP9 complete locally, 2026-11-13:** MVP9.3 exposes CommandContract,
CommandOption and optional from_typer, explicit saved-job revalidation and a
packaged agent recipe. The implemented public boundary below supersedes the
earlier checkpoint restrictions; hypothetical walkthrough APIs remain proposals.

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

## MVP9.1 implemented proof boundary

`command_contract.py` owns an in-memory, framework-free CommandOption/CommandContract
model, strict native-value and range/default validation, plain metadata discovery,
and construction of existing job dictionaries. `typer_adapter.py:from_typer` lazily
imports optional Typer 0.27, prechecks the selected app/function/options and derives
the model without parsing arguments or executing callbacks. Both modules are
experimental and absent from top-level public exports until MVP9.3's release.

The settled proof syntax is `from_typer(app, script=..., input_args=..., path_args=...)`,
then `.describe()`, `.validate(script_args)` or `.job(name=..., script_args=..., slurm=...)`.
Names/types/static defaults/min/max come from the command declaration; path roles
and resources remain explicit application/infrastructure policy. There is no
second hand-maintained option schema. Integers stay strict (bool is rejected),
numeric/float options accept int or float and return finite floats, and default-off
booleans retain explicit False in JSON. Invalid and unknown settings fail before
the client writes a bundle.

The adapter deliberately supports one plain leaf app, add_completion=False,
canonical long flags, scalar static annotations and ordinary numeric bounds.
It rejects groups/app callbacks, custom context/classes/flags, option callbacks,
prompts, env/default factories, custom parsers, forward annotation evaluation,
repeated/tuple/optional values and default-on booleans. Raw metadata is checked
before Typer constructs a parser object; version/flag/requiredness capabilities
are checked too. Discovery is not a sandbox for arbitrary imported application
code: callers supply an already-imported lightweight trusted app. No dynamic
application discovery/import is performed by the builder.

No new saved schema or contract version: jobs contain existing name/script/
script_args/slurm/path-role fields and normal snapshot metadata. Every supported
static default is materialized in script_args, including omitted False flags.
The in-memory contract and parser/callback objects are never serialized. Saved
definitions do not claim semantic revalidation at load/submit time. Clients can
explicitly validate loaded settings against their current trusted declaration;
durable identity/lookup remains a release decision for MVP9.3. Public helper
stability is deferred rather than implying today's hypothetical APIs are accepted.

At the MVP9.1 checkpoint the renderer was unchanged: non-path strings had to be
shell-safe single words/CSV; declared paths used existing quoting. Strings with
spaces and shared literal compilation were deferred to MVP9.2. Raw-script jobs,
existing clients, machine roots, array/dependency behavior and receipts were unchanged.

`typed_science_demo.py` supplies the reference command. It uses optional Typer
without importing AutoSlurm to execute science. One declaration supplies its CLI
and builder metadata; an offset/repetition/label/optional-values example proves
the saved settings are actually used. Original argparse science-demo stays intact.
Tests build a temporary launcher instead of installing an application environment.

Verification: 674 full offline tests passed in 10.53 s (42 expected collision
warnings); `.development/test-runs/command-proof.xml`, 40 new cases. Tests cover
plain metadata/defaults, wrong/unknown/unsafe values, required options, ranges,
unsupported callback/factory/parser/context/list/bool forms, version/flag capability
gates, real parser round-trips, pre-save failures without writes, readable JSON,
preview/dispatch equality and real local science output under a results root with
spaces. Scheduler acceptance is retained independently of scientific checks.

Clean wheel optional-dependency/contract/JSON smoke passed; artifact
`.development/artifacts/command-proof/autoslurm-0.1.0-py3-none-any.whl`, SHA256
`17e2ab6c8a97b16a9eea104285a80082280f680e490b84750babb13171db9221`.
Base package/core adapter imports work with Typer imports deliberately blocked;
the optional adapter reports its missing dependency explicitly when called.
No base install, cluster contact, client application outside the reference example,
daily configuration/tracking or rollback source changes.

## MVP9.2 implemented literal compiler

`argument_compilation.py` is the shared, framework-free owner of literal values,
argv compilation and shell quoting. It performs no path lookup, I/O, parser
discovery or execution. The renderer resolves through the existing ExecutionContext
first, compiles once, then shell-quotes the resulting argument groups. Shared
bundle preparation already feeds preview and dispatch, so no second invocation
builder is introduced. The private `_format_script_args` implementation is retired.

Each internal group is an immutable tuple of argv strings representing one
displayed argument line. Scalar options remain `--name=value`, booleans remain
default-off flags, and simple values render exactly as before. Quoting applies
to every value, not just declared paths. Spaces, quotes, dollar signs, operators,
glob characters and substitutions are literal data. `CommandContract` uses the
same literal validator and now accepts nonempty strings with these characters;
the experimental adapter remains optional/internal pending MVP9.3.

The narrow authoring contract still rejects list/tuple/default-on-boolean forms.
Existing raw dictionaries retain legacy `--flag a b` list semantics, None/False/
empty-list omission and trailing `__positionals__`; every list/positional element
is now quoted too. Nested values, non-finite floats, control characters, malformed
option names and duplicate normalized flags fail locally with the argument name.
No `list_style`/`bool_style`, repeated-option semantics or command introspection
has been added. Signature/scientific validation remains the client's responsibility.

### Rendering boundary and retained data

This is an explicit `dev` rendering change for scripts generated by MVP9.2, within
the user's requested MVP9 compiler work. Saved job fields, snapshots and receipt
formats do not change; no migration or historical artifact rewriting occurs.
Existing raw definitions relying on shell expansion in values must move runtime
behavior to CLI environment defaults or `runtime_environment`. Do not pre-escape
values. `script` remains an operator-owned shell command prefix; the compiler
does not parse or sandbox it, activation commands or arbitrary Slurm directives.
Queued/running job scripts and the pinned rollback source are untouched.

Verification: 723 full offline tests passed in 10.01 s (42 expected collision
warnings), report `.development/test-runs/argument-compiler.xml`. Focused checks:
105 passed. Coverage includes actual Bash argv capture without expansion,
real Typer parsing, empty/raw list and positional quoting, local/fake-remote path
resolution before compilation, invalid values before staging, unchanged plain
output, preview/dispatch equality and the reference command's exact scientific
output/label under paths with spaces. Clean wheel import/path/actual-shell smoke
passed with Typer imports blocked, artifact
`.development/artifacts/argument-compiler/autoslurm-0.1.0-py3-none-any.whl`, SHA256
`d8d846ed99b780dde236a8beb5c4e6e69d422aa1f7598991dd59c460177d9f9a`.
Installation was only into a disposable smoke target; no base or daily environment
install, actual cluster operation, external client or rollback changes.

## Open decisions and log

MVP9.3 settles the narrow public authoring and saved-validation boundary below.
The historical in-memory-only descriptions in MVP9.1/2 describe those checkpoints.

## MVP9.3 implemented public authoring and adoption

Public imports are `from autoslurm import CommandContract, CommandOption,
from_typer`. Existing module paths retain the same owners, not compatibility
wrappers. Core imports and explicit contracts need no Typer. The `commands`
extra supplies the tested Typer 0.27 profile; unsupported versions/capabilities
fail explicitly. Command declarations, arguments and metadata are pure; no
callback/help probing, automatic import by command name or remote work is added.

`describe()` returns plain metadata; `validate(values)` and
`job(name=..., script_args=..., slurm=..., dependencies=...)` materialize current
supported defaults for new jobs. Optional dependency names become the existing
field; arrays stay ordinary Slurm settings. Public constructor checks stabilize
simple names, scalar path options, immutable option/path declarations and
non-overlapping input/result roles. The existing engine owns complete graph,
path/readiness and submission-snapshot checks. This does not add a workflow runtime.

### Saved-job and release/data boundary

`validate_job(job)` checks a complete saved job against the explicitly supplied
current contract. It checks command text, input/result roles, setting names,
native types/ranges, resources mapping and dependency names, returning a detached
copy. It preserves other job/record fields and does not publish or modify records.
All supported options must already be present: new optional defaults are not
silently injected into old plans. Previously materialized values remain explicit
when defaults change. Unknown/removed options and incompatible declarations fail
locally; a client reviews and builds a new definition deliberately.

No new saved schema, contract fingerprint, arbitrary import target or migration.
This preserves existing JSON and retained historical evidence. Revalidation proves
compatibility with the supplied current contract, not historical code identity,
scientific validity or installed remote version. If no trusted supported contract
is available, raw authoring remains possible but has no automatic semantic claim.
Receipt/snapshot protections and operator-controlled submission remain unchanged;
validating settings is not permission to resubmit a saved submission.

This is the supported authoring boundary for the local `dev` MVP9 candidate,
still package version 0.1.0; it is not a public-index publication, remote rollout
or rollback-source change. No script/receipt format changes in MVP9.3. MVP9.2's
documented literal rendering boundary remains in force. A local `mvp9` tag records
closure without changing installed environments.

### Human, agent and client routes

`docs/typed_commands.md` explains purpose, review and failure meaning. The
reference client's `science-jobs plan/validate/preview` uses only public APIs;
planning/validation is local, preview explicitly performs normal readiness checks,
and no command submits automatically. Four original-index shards feed a reducer;
scientific commands have no AutoSlurm import and validate their own output identity.

`src/autoslurm/agent_resources/14_typed_commands.md` is the single source of the
new installed recipe. Context selection merges it with legacy checkout guidance,
giving packaged names precedence. `asl agent --sections 14_typed_commands` and
ACP `gather_context` with task integrate/commands/schedule expose the recipe;
existing ACP schedule still accepts a validated plain dictionary. No parser/Python
object is added to ACP. Explicit package data includes this recipe/action metadata;
complete historical documentation packaging remains L3, not implied by this slice.

Verification: 761 full offline tests passed in 11.08 s (43 expected collision
warnings), report `.development/test-runs/typed-authoring.xml`; 83 focused checks
passed. Twenty added cases cover strict saved settings/default changes, command/
role/type drift, detached copies/no I/O, public exports, recipe discovery without
a checkout, and client CLI plan/validate/preview through arrays, dependency IDs,
byte-identical dispatch scripts, receipts, cached inspection and actual scientific
outputs. Clean AutoSlurm/client wheel smoke also checks optional-dependency absence,
installed API/recipe/ACP routes, client CLI and scientific entry-point execution.
Clean wheel SHA256:
`dbcca8ede6c0135729aead31aa83b1da75a24489542bc646dffdaec9ba167ccb`, artifact
`.development/artifacts/typed-authoring/autoslurm-0.1.0-py3-none-any.whl`.
No actual cluster connection/submission/install, base install, daily config/state,
external scientific-client edit or rollback change.

## Remaining extensions

- Should repeated/tuple/default-on option support follow the scalar release?
  Literal string quoting is implemented in MVP9.2; broader parser semantics remain open.
- Broader CLI adapters, remote command availability/version checks and any future
  persisted command identity need separately scoped contracts and release choices.

**2026-11-13, MVP9.3:** exposes the narrow public contract/builder and strict
explicit saved-job validation, installed agent recipe and reference client routes.
MVP9 is complete locally; API-wide error inventory (MVP10.1) is next.

**2026-11-13, MVP9.2:** implemented the shared literal compiler and removed the
old formatter. Updated the string guidance after actual parser/shell execution
checks; saved formats and supported scalar/CSV/default-off policy are retained.

**2026-11-13, PLAN.1:** user requested two next MVPs, command arguments then error
handling. Scheduled a narrow scalar contract/compiler/reference-client release
as MVP9; API sketches remain proposed and broader value styles stay deferred.
No runtime or application changes in this planning task.

**2026-11-13:** read source and client examples, checked primary framework docs,
ran the isolated design experiment, and recorded proposed interface/validation/
human-review criteria. No package installs, runtime changes, saved job edits,
cluster contact or full application test rerun. Last code baseline: 576 passing
offline tests from MVP7.2f. Documentation/link/example checks only for this study.
