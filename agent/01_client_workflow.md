# Current client workflow

Use this recipe with the development installation through MVP8 and MVP7.2f
(single-checkout Git updates plus editable refresh; no managed releases). As of
2026-11-12, main branch `dev` is the active base Conda editable installation;
the retained baseline rollback installation does not have these additions. Read `00_operating_rules.md`
first; this recipe takes precedence over older examples where their claims
differ. Current repository work is local only: submissions are tested with
mocked Slurm, never a real cluster.

## Identify the installation

Record the interpreter, actual AutoSlurm import path, source revision, selected
machine and resolved storage root. Both local installations report version
0.1.0, so version alone cannot identify them. The repository's
`REFACTORING_DOCS/installation-register.md` records the actual local setup.

Use `AUTOSLURM_STORAGE_ROOT` for every development process. Keep its config,
tracking, logs and results separate from stable storage. Prepared environments
are operator-owned; compute jobs do not install packages, pull Git repositories
or change shared code. One bundle targets one machine. The
[software recipe](13_software_preparation.md) documents explicit `update_software`
and `asl software update`: pull the existing checkout and refresh its editable
install in the configured environment before submission, with commit/install
evidence. Keep one checkout per project; the operator owns scientific dependencies
and persistent environment creation. Editable updates use pip's temporary build
isolation and may download build requirements on the login host; --no-deps keeps
runtime dependencies unchanged. Updates do not create/select release runtimes.
Historical software-manifest helpers remain pure data utilities; new runs use
the configured environment without a `software` runtime request.

MVP9 adds [supported typed-command authoring](../examples/reference_client/README.md#typed-command-authoring)
through public `CommandContract`, `CommandOption` and optional `from_typer`.
They validate named settings before save and revalidate exact jobs against a
caller-supplied trusted contract. Saved bundles do not retain or automatically
rediscover command schemas; use explicit `validate_job` before relying on a
changed declaration. Existing JSON/preview/submission contracts remain unchanged.

MVP10.2 adds the opt-in [diagnostic foundation](../src/autoslurm/agent_resources/15_diagnostics.md).
Use explicit diagnostic facts at client boundaries and retain original receipts/
update evidence before presentation. Existing services are adopting diagnostics
in later slices; an error's optional `.diagnostic` can still be None. No universal
CLI/ACP behavior change is claimed; software-update adoption is described below.

MVP10.3a adopts that contract for configuration reads, profile/setting validation
and machine selection. Catch `from autoslurm import ConfigurationError`, retain
its `.diagnostic` and original `__cause__`, and correct the reported source/field.
Invalid configuration stops preview/submission before commands; it never selects
another profile or repairs an environment. The config CLI renders these failures
once and supports `--debug`. Existing corrupt/unreadable files are preserved.
Read failures/missing activation no longer use OSError/AttributeError; validation
remains ValueError-compatible. Other services are still adopting diagnostics;
see the packaged diagnostic recipe for current coverage.

MVP10.3b.1 adds public `InvalidRequestError` for typed authoring, literal arguments,
graphs, software-intent metadata and bundle input/preparation guards. Inspect its
diagnostic field/option/job/stage and correct the definition before saving or
submitting. Preserve explicit saved settings; a missing setting is not permission
to insert a new default. It is ValueError/DiagnosticError compatible; old
TypeError/KeyError authoring guards and cycle errors now use this class. Transport
adoption remains pending. Snapshot selection and path/
render preparation now adopt the shared diagnostic contract as described below.

MVP10.3b.3 extends InvalidRequestError to pure path/render preparation. Inspect
field/option/job/machine, logical_path and attempted resolved_path where known;
rejected candidate paths are not destinations. Correct the explicit definition
and preview the same bundle again. Preview/submit enrich these failures with the
exact bundle_path. Environment/directive errors omit values; syntax errors retain
the job/line without copying Bash's arbitrary literals. `asl submit --debug`
re-raises adopted preparation failures. Saved execution lookup uses SelectionError
for missing evidence (resource_missing) or malformed roots/transport (record_invalid),
preserving historical producing roots without current-profile discovery. Preserve
the original file. No inferred effects, automatic repair or resubmission follows.
Readiness/existence/process diagnostics remain MVP10.4; local persistence is
adopted through MVP10.3c.3.

MVP10.3c.1 adds shared JSON publication diagnostics. Catch public RecordWriteError
(DiagnosticError and OSError), retain its `.diagnostic` and original `__cause__`,
and inspect the exact destination before repeating a write. Serialization failures
now use this class too, replacing raw TypeError/ValueError at this dev boundary.
record_publication distinguishes not_started/unknown/succeeded; record_durability
is separate. Cleanup failures retain the primary and known publication effects.
These facts cover one local record, not scheduler acceptance or a multi-file
transaction. Bundle/config domain context/presentation and direct reads are adopted
in MVP10.3c.2; c.3 adds receipt/cache/script integration. Retain the existing
receipt/update payloads alongside diagnostics. See installed 15_diagnostics.

MVP10.3c.2 adopts direct bundle reads and bundle/config writes. Catch SelectionError
for missing/inaccessible/malformed direct files (replacing the old FileNotFoundError/
OSError mix); invalid saved DAGs retain InvalidRequestError. Retain exact path,
safe diagnostic and native cause. Append/metadata mutations validate the original
record and never treat broken evidence as an empty bundle. RecordWriteError keeps
publication/durability/secondary cleanup plus bundle/job or configuration identity
and calling context.source. A local publication failure is not scheduler rejection;
inspect the exact destination before retrying an append. Config/filter/initialize/
schedule/submit use shared text/exit 1 and debug; schedule retains --autoslurm-debug.
ACP preserves shared write diagnostics. Broad observation and post-dispatch
policy remain separate slices. Do not operate through private files
or metadata helpers; retain the supported receipt/inspection workflow.

MVP10.3c.3 adopts local receipt/cache I/O and atomic script publication. Low-level
bundle/receipt/cache reads share operation record_read, while selector validation
retains selection. Receipt reads raise SelectionError with exact receipt identity;
cache/per-item receipt errors carry diagnostic without erasing known IDs or live
status/logs. SubmissionError retains its receipt and any adopted persistence
diagnostic. Scripts use the shared atomic writer: old bytes survive before
publication and complete new text survives after observed publication. Multi-file
staging is not a transaction, and no file error authorizes resubmission.

MVP10.4a adds software-update diagnostics, including stale venv paths. Catch
SoftwareUpdateError and retain both .evidence and .diagnostic. A missing Python
names the attempted venv_path/bin/python and correction through asl config, with
pull/install not_started. Separate git_pull/editable_install effects retain
completed pulls, partial installs and unknown outcomes; do not retry a lost
response blindly. The update CLI supports --json evidence/diagnostic and --debug.
Invalid update requests use InvalidRequestError/ConfigurationError; unexpected
bugs propagate. General SSH/helper/transfer/software-status adoption remains
MVP10.4b–d. See the [software recipe](13_software_preparation.md).

MVP10.4b.1 adopts remote root discovery and helper capability checks. Catch
autoslurm.errors.DiagnosticError for expected process/protocol/compatibility
failures; invalid explicit root/venv settings use ConfigurationError. Retain the
diagnostic's machine/ssh_alias/storage_root and attempted executable/path. A
local SSH launch failure, timeout, SSH255, remote nonzero, invalid response and
old helper are distinct. Availability remains unverified on a failed probe;
do not infer a missing path, rejected job or particular authentication problem.
Checks run once, with a 30-second timeout and 64-KiB accepted response bound.
Root/capability parsing is strict; no fallback, install or retry is introduced.
The submit CLI renders the diagnosis and next action once; --debug retains the
original cause. Session cleanup, transfers, software-status and general CLI/ACP
adoption remain later tasks. See installed 15_diagnostics and
[the human failure guide](../docs/errors.md#remote-readiness-before-submission).

## Adapt scientific software

Record `autoslurm.__version__` (or `asl --version`) alongside the client's exact
bundle/receipt when reporting integration issues. Development versions identify
checkpoints; add commit/dirty evidence for a moving editable checkout. Installed
distribution metadata can lag source until editable reinstall. Consult the
[versioning policy](../docs/versioning.md), [changelog](../CHANGELOG.md) or installed
`16_versioning` recipe; protocol/schema compatibility remains separately checked.

Keep computation independent of AutoSlurm. Expose an installed command with
explicit arguments, useful `--help`, a cheap smoke run and nonzero exits for
invalid input or failed computation. A thin adapter may read
`SLURM_ARRAY_TASK_ID`; scientific functions need not know Slurm. Give each shard
a distinct output. A reducer validates all expected shards and their input
compatibility before reporting success.

## Fetch execution evidence

Use public `fetch_run(receipt_path=...)` or `fetch_run(bundle_path=...)` to refresh
linked receipts before status and bounded logs. The exact snapshot's receipt
links and recorded producing transport/paths remain authoritative; no guessing
by bundle name or scientific-result transfer occurs. `asl fetch` shares status/
log selectors; `--cached` or Python `refresh=False` reads local cached evidence
without source/remote reads or writes. Receipt reads are limited to 1 MiB/30
seconds; log defaults remain 40 lines, 64 KiB/file, 20 files/run. Check errors and
freshness; retain known IDs and readable logs on partial failure. Persistence
failure may leave new IDs only in returned evidence. Never resubmit because
fetching failed. ACP `fetch_run` exposes the same result and per-item errors;
installed section `18_fetching` documents the recipe. Legacy `asl sync` mirrors
whole jobs/scripts/out directories and is not equivalent to bounded fetching.

## Explicit named job arguments

**Alexandre's lasting preference, 2026-11-13:** job arguments are explicit,
named and readable in the bundle. Follow this contract when building a client,
writing/reviewing bundles or helping an existing application adopt AutoSlurm.

- Expose one typed CLI command per kind of job; **Typer is preferred**. For
  `science-tool fit --seed 17 --n-stars 8`, use `script: "science-tool fit"` and
  individual named options in `script_args`. The command/subcommand is fixed;
  job settings belong in named options rather than positional payloads.
- Give every job one `script_args` key per setting. Include effective defaults
  so the saved JSON records the settings actually used. Do not send a whole run
  definition, unrelated jobs' settings or a nested configuration as one value.
  Never use base64, JSON blobs, or a single config-file argument to hide settings.
  Data files remain legitimate declared inputs; their paths must not hide job
  configuration that should be explicit arguments.
- Values are scalars: `int`, `float`, `str` or `bool`, not nested mappings,
  `None` or Python/JSON lists. Represent a list as one readable comma-separated
  string, such as `"g,r,i"`, with a typed client parser for its elements. Current
  list rendering is `--flag a b`, which Typer rejects for this single-value
  option pattern; it is not a supported way to pass lists in Alexandre's clients.
- Boolean options default to off. Use real booleans in `script_args`, not
  `"True"`/`"False"`: `True` emits `--flag`, and `False` emits nothing. Record
  `False` in JSON for readability; its omission in the rendered command relies
  on the CLI's default being off. Do not use omission to disable a default-on flag.
- String values are literal data. Spaces, quotes, dollar signs and shell
  metacharacters are supported: AutoSlurm quotes every value after resolving
  declared paths. Supply the original value, without manual shell escaping;
  reject control characters. `"$(command)"`, `"$HOME"` and `"*.fits"` remain text,
  not substitution or wildcard expressions. Use `runtime_environment` or a CLI's
  environment defaults for runtime values. Keep application paths relative.

For example, a job can declare its complete, readable option mapping:

```json
{
  "name": "fit",
  "script": "science-tool fit",
  "input_args": ["input_file"],
  "script_args": {
    "input_file": "data/measurements.json",
    "output_dir": "study/fit",
    "seed": 17,
    "n_stars": 8,
    "learning_rate": 0.001,
    "bands": "g,r,i",
    "require_gpu": true,
    "verbose": false
  },
  "slurm": {"tasks": 1, "gres": "gpu:1", "cpus_per_task": 1, "mem": "1G", "time": "00:05:00"}
}
```

The scalar rule applies to `script_args` values; `input_args` and `path_args`
remain lists of argument names under AutoSlurm's path declaration contract.

**Validate before writing a bundle.** The client's bundle builder must check
each job against the actual typed command signature: reject unknown option names,
missing required options, wrong scalar/CSV element types, control characters and
incompatible boolean defaults. Map Python-style names consistently to CLI names
(`n_stars` becomes `--n-stars`) and preserve valid native scalar values rather
than blindly stringifying everything. Run this before `save_bundle` or
`schedule_job`; repeat before submitting if the signature or definition changed.
AutoSlurm's existing structural/path/shell preflight does not replace this
client-side semantic validation. A syntactically valid shell script can still
contain an unknown option or the wrong CLI value type.

During reviews, flag encoded configuration and suggest a concrete replacement:
one job-specific typed command plus a flat named argument mapping. Read both the
saved JSON and previewed invocation to confirm that settings stay understandable.
Client signature checks remain distinct from AutoSlurm's structural/literal
checks. No command schema is stored or rediscovered automatically on loading a
bundle. Use the supported `from autoslurm import from_typer` adapter for its narrow
Typer profile, or explicit `CommandContract` / `CommandOption` metadata for other
clients. `command.job(...)` validates new settings and fills defaults;
`command.validate_job(saved_job)` rechecks complete saved settings against a
current trusted contract without filling new defaults or changing files. See the
[packaged authoring recipe](../src/autoslurm/agent_resources/14_typed_commands.md).

MVP9.2 changes rendering for newly generated scripts only; saved job fields and
historical scripts/receipts are retained. Legacy raw bundles still support
space-separated lists and trailing `__positionals__`, with each element now
quoted. New integrations follow the named scalar/CSV pattern above. Do not rely
on shell expansion inside any argument value; `script` remains an operator-owned
shell command prefix and must not contain untrusted settings.

## Dependency failure default

Jobs with a nonempty `dependencies` list default to
`#SBATCH --kill-on-invalid-dep=yes`. Slurm then cancels a dependent job whose
dependency can never be satisfied, instead of leaving it pending indefinitely.
To retain pending behavior for a particular job, set
`"slurm": {"kill_on_invalid_dep": "no"}`. Jobs without dependencies receive no
automatic directive. Preview shows the effective policy; actual dependency IDs
are still bound at submission. Existing queued jobs and saved scripts are unchanged.

## Application paths

Client definitions keep paths relative. These are the current bases:

| Field | Base and behavior |
|---|---|
| `script` | Installed application command in the prepared environment |
| `working_directory` | Directory relative to `results_root`; defaults to `.` when using configured roots |
| String arguments named in `input_args` | Required, pre-existing inputs relative to `results_root`, independent of `working_directory` |
| `script_args.output_dir` | Results-relative; AutoSlurm resolves under machine `results_root`, or selected execution storage's `results/` |
| String arguments named in `path_args` | Same results-relative base, for example a reducer's `parts_dir` |
| Undeclared arguments | Passed through; relative paths depend on the established working directory |
| Paths inside application config files | Never rewritten by AutoSlurm; do not use a config-file option to hide job settings that must be named arguments |

Configure absolute infrastructure roots once in the selected machine profile;
keep application declarations relative. Jobs using configured software/data roots reject absolute paths
and `..` traversal in declared inputs, results and working directories. Use
`working_directory`, not a separate Slurm `chdir`. AutoSlurm validates the data root,
working directory and required inputs before writing scripts or submitting.

For example, an operator-prepared remote profile contains these infrastructure
settings (replace them with its real isolated locations):

```json
{
  "ssh_alias": "cluster-development",
  "storage_root": "/cluster/autoslurm-development",
  "software_root": "/cluster/science-software",
  "results_root": "/cluster/science-data",
  "venv_path": "/cluster/prepared-environment",
  "slurm_account": "account"
}
```

For module-based clusters, the operator can run
`asl config --machine cluster --detect-module-init` once to record the first
readable known site initializer, or set `--module-init /absolute/site/init.sh`.
Detection explicitly contacts the selected machine, only checks files and never
executes env_command. Ordinary config reads/set/clear flags do not discover hosts.
New jobs initialize module only when unavailable, then run env_command and
activate venv_path. Setup failures stop before the application, including unrooted
jobs; inspect bounded Slurm logs for the named stage/field. Keep module selection
in machine env_command, not application code or per-job commands. Do not source
login profiles globally or put submit/update commands in environment setup.
Neither detection nor shell-syntax preview establishes compute-node readiness;
submission has no activation preflight. Use `--clear-module-init` to remove the
setting. Existing attempts/scripts are not rewritten. Installed agents can read
`asl agent --sections 17_environment_setup` for the complete recipe.

`slurm_account` is optional infrastructure configuration. Missing/null/blank
means no profile `#SBATCH --account` directive. Use
`asl config --machine cluster --clear-slurm-account` to remove it locally without
SSH, or `--slurm-account ACCOUNT` to set it. The interactive editor accepts `-`
to clear optional fields; Enter keeps the current value. Do not invent an account
for a cluster that does not need one. Explicit job `slurm.account` values are
still rendered; omit those too when no account should be sent. This changes
future scripts, not historical scripts/receipts, and does not establish whether
Slurm will accept a particular account/partition combination.

Remote profiles use only `ssh_alias`, the `Host` name in SSH config. HostName, User,
IdentityFile and other connection options are owned by SSH, not AutoSlurm.
Submission reads effective settings with non-connecting `ssh -G`: a configured
ControlPath plus automatic sharing/persistence is reused without Control options
or explicit open/close commands. Otherwise AutoSlurm owns a temporary master
under `/tmp/asl-ssh-*/cm-%C` on POSIX (default temp directory if `/tmp` is absent).
Failed/unreadable settings fall back once to that owned session. Never edit SSH
config or handle keys/passphrases to work around submission in a client agent.
MVP10.4b.2 diagnoses owned socket allocation/length/open/close/removal, using
operation ssh_session and independent resource effects; open/close timeouts are
30/10 seconds. The optional ssh -G check stays 10 seconds and accepts at most
64 KiB; invalid profiles and programming bugs propagate instead of falling back.
Cleanup now reports failure instead of silently ignoring it. Retain
SubmissionError.receipt: state/IDs remain submitted after known acceptance,
partial and uncertain outcomes stay distinct. session_cleanup_diagnostics is an
optional bounded receipt field for workstation cleanup evidence; refresh keeps
it. An existing body error stays primary with secondary cleanup facts and native
causes available for debugging. A removed directory does not establish master
closure. Never retry jobs because cleanup failed. See installed 15_diagnostics.
Local profiles omit SSH identity and use the process's selected storage root;
legacy local `path` does not override that selection. Set profile roots through
`asl config --interactive` or the public configuration API. For an existing profile:

```sh
asl config --machine cluster --ssh-alias cluster-development --software-root /cluster/science-software --results-root /cluster/science-data
asl config --summary
```

Root-setting flags only save local configuration; they do not contact a cluster
or move files. `update_software` separately pulls the existing project on the selected
machine. It creates no code copies or release records.
Both inputs and outputs live under `results_root`; the data root
and required working directories/inputs must already exist before preview.
The two roots default to `<storage_root>/software` and `<storage_root>/results`.
`storage_root` remains AutoSlurm's internal tracking location.
Custom relative Slurm `output` paths need an existing parent directory;
otherwise use the default log destination managed by AutoSlurm.

Inputs must already exist on the selected machine; staging and opaque config
rewriting are not supported. Declare an upstream job's future results in
`path_args`, rather than required pre-existing `input_args`. Use fresh study/output
namespaces for attempts; scientific validity belongs to the client. Legacy jobs with no explicit software/data roots, input declarations or working
directory retain their previous absolute-output/current-directory behavior.

## Save and select an exact definition

In MVP0.3, public `save_bundle` returns the exact saved `Path`. For one job,
`schedule_job` returns `(saved_job, path)`; retain the saved name because append
operations can rename duplicates.

```python
from uuid import uuid4
from autoslurm import save_bundle, load_bundle_from_path

bundle_name = f"study-{uuid4().hex}"
definition = {
    "sample": {
        "name": "sample",
        "script": "science-demo",
        "input_args": ["input_file"],
        "script_args": {
            "mode": "single",
            "input_file": "data/measurements.json",
            "output_dir": f"{bundle_name}/summary",
        },
        "slurm": {"tasks": 1, "cpus_per_task": 1, "mem": "64M", "time": "00:01:00"},
    }
}
planned_path = save_bundle(definition, bundle_name)
jobs, dependencies, saved_date = load_bundle_from_path(planned_path)
```

MVP6 publishes complete JSON records through one atomic writer. New snapshots
never replace an existing timestamp, including rapid `schedule_job` calls.
Appending several jobs publishes the complete batch once. A failed serialization
or write before publication keeps the previous record intact; an error during
final directory synchronization can occur after the complete file is visible.
After a save error, rediscover and inspect the exact definition before submitting.
This does not provide concurrent append locking or a transaction across records.

Record the bundle name, planned path and definition in the client handoff before
submission. Rediscover work with `list_saved_bundles(bundle_name=...)` or ACP
`list_experiments`; load the returned path with `load_bundle_from_path`. Do not
reconstruct filenames, edit tracking JSON or parse terminal rows. Name, `latest`
and index selectors can move. `load_bundle(name, desired_date=...)` selects the
nearest date, as does `submit_jobs(..., date=...)`. Neither is an exact snapshot
selector. `select_bundle_snapshot` owns the shared CLI/name selection policy:
submission name/latest selection prefers ready drafts; inspection resolves the
newest selected snapshot. Dated loading selects the nearest timestamp across
saved snapshots.

MVP10.3b.2 returns per-snapshot `state` and plain `diagnostic` from discovery,
including list_runs and ACP listings. An unreadable or unparseable snapshot has
unknown jobs/counts (`None`), distinct from an empty draft (`[]`/zero). Retain the
failed entry alongside healthy records and report its diagnosis; do not silently
choose an older definition. The newest failed snapshot remains visible and blocks
ready-draft fallback. Catch public SelectionError for selector/discovery failures;
it replaces FileNotFoundError for missing selections and remains ValueError/
DiagnosticError compatible. Only absent config defaults the visibility filter;
corrupt/unreadable/invalid config must be corrected explicitly. Exact filename-
only selection does not validate contents. Strict bundle_snapshot_state is used
by the submit CLI before connecting. Publication, readiness and
inspection observation-policy migration remain separate tasks.

Before submission, `preview_bundle(planned_path, machine="target")` validates and
returns plain resolved paths and rendered script text without writing scripts or
submitting. MVP4 shares the same definition validation and script preparation
between preview and submit. Empty, invalid or already-submitted definitions are
rejected by both; use inspection for existing submissions. Mapping fields such
as application arguments and environment exports must contain mappings.
Prepared scripts remain unchanged through submission; AutoSlurm passes resolved
dependency IDs as Slurm command arguments. Preview checks are point-in-time and
do not freeze inputs, environments or scheduler availability.

A remote preview still contacts the configured machine for root
discovery and batched input validation. Under this repository's local-only scope,
remote interactions must be mocked.

## Control application threads

Use job `environment` for literal scalar exports, applied after activation.
Values are shell-quoted: `$HOME` and `$(...)` stay literal. Use
`runtime_environment` for values supplied at job execution; each value names
one shell variable, without `$`, braces or expressions. An unset/empty runtime
source stops the job before the application runs. For example:

```json
{
  "environment": {"OPENBLAS_NUM_THREADS": "1"},
  "runtime_environment": {"OMP_NUM_THREADS": "SLURM_CPUS_PER_TASK"}
}
```

Set the corresponding Slurm CPU request explicitly; applications still own
worker/process counts and scientific parallelism. Environment names must be
valid shell identifiers; literal and runtime mappings cannot define the same
name. AutoSlurm does not evaluate arbitrary shell interpolation.

## Submit once and retain evidence

For an already authorized operation in the selected lane, or a mocked test:

```python
from autoslurm import submit_jobs, SubmissionError

try:
    receipt = submit_jobs(bundle_name, machine="target", bundle_path=planned_path)
except SubmissionError as error:
    receipt = error.receipt
    print(receipt["receipt_path"])  # Retain this exact reference in the handoff.
    raise  # Stop; inspect this operation rather than submitting it again.

submission_path = receipt["bundle_path"]
submission_id = receipt["submission_id"]
accepted_ids = {name: job["id"] for name, job in receipt["jobs"].items() if job.get("id")}
```

Submission always creates a new exact tracking snapshot and random submission
identity; it leaves the selected definition unchanged. The receipt records
planned/tracking paths, machine, producing receipt location, per-job state/IDs,
errors and update time. Execution persists each accepted ID before another
scheduler call. IDs are also mirrored into the existing tracking snapshot.
Save the exact receipt path in the client handoff; do not reconstruct filenames.
Definition/readiness errors before receipt creation raise ordinary validation
errors and submit nothing; once the operation exists, submission errors carry
its receipt, including any tracking/storage error. Initial receipt-write failures
also carry in-memory evidence and stop before dispatch. An interruption while
persisting an accepted ID preserves that ID and stops further submissions.
This is incremental submission evidence, not an immutable scientific attempt
store or a guarantee against every concurrent writer or scheduler crash.

FIX.TRACKING.1: new remote submissions also create an exact tracking snapshot in
the producing installation before sbatch, projecting incremental IDs only after
the execution receipt is durable. On the cluster, normal status/log/fetch/inspect
use local Slurm and recorded producing paths, with no workstation files/profile
or SSH to itself. Use the producing storage root; row indices and snapshot dates
can differ between machines. The submission_id remains the attempt identity.
Receipts retain origin bundle_path/receipt_path/planned_path/execution; additive
execution_bundle_path identifies the cluster view. New execution receipts use
`.execution.json`, avoiding ambiguity with identical directory names at both
ends. Select the actual execution_receipt_path when inspecting on the cluster;
receipt selectors validate the exact backlink and resolve the local view.
Cluster refresh never rewrites the helper-owned receipt. Workstation refresh
still updates its original tracking snapshot through the recorded transport.
Clients preserve returned references rather than constructing storage paths.
Both installations must support execution_tracking=1 and submission_protocol=1;
older helpers fail before staging/dispatch. No auto-install, historical draft
adoption, name/latest receipt matching, sync requirement or submission retry.

| Receipt state | Interpretation |
|---|---|
| `submitted` | Every job has a known accepted scheduler ID; computation may still fail |
| `rejected` | No known accepted jobs; preparation or submission stopped with a known rejection |
| `partial` | Some jobs accepted; a later rejection stopped the remaining graph |
| `uncertain` | Some execution-side outcomes are unobserved; preserve any known IDs |
| `prepared` / `submitting` | Last recorded intermediate evidence; no final outcome, no proof the helper is still alive |

Per-job `blocked` means execution deliberately did not submit a dependent after
an upstream submission stopped. Unrelated jobs left untouched are
`not_submitted`. On response loss, unobserved jobs are `uncertain`, not assumed
rejected or blocked: the remote helper may still be submitting them.

The CLI equivalent is `asl submit NAME --bundle-file PATH --machine PROFILE`.
Outside mocked tests it creates real scheduler effects. ACP supports scheduling,
listing, receipt inspection and context gathering; it has no submit action.

An exception or absent ID does not prove rejection. Remote bulk-to-legacy
fallback is removed in MVP2. The legacy graph driver is retired. A prepared
remote `venv_path` with a receipt/tracking-capable matching helper is required; capability
failure stops before dispatch, without an automatic install or alternate submit.
All generated scripts receive shell syntax checks before the first submission.

Never automatically retry, erase IDs or resubmit a saved submission snapshot.
AutoSlurm refuses receipt-bearing/submitted snapshots and helper identity replay.
Submitting the original draft again would create a new operation; do that only
as an explicit, reconciled decision. There is no exactly-once guarantee across
the gap between scheduler acceptance and receipt persistence.

## Rediscover and inspect submission evidence

`list_submissions(bundle_name=...)` lists receipts in the selected local
installation. `load_submission(receipt_path)` reads one exact local record
without network or scheduler queries. `refresh_submission(receipt_path)` fetches
only that execution receipt using its recorded transport/root, then mirrors known
IDs into the original tracking snapshot. Profile edits do not redirect it.
Remote refresh may contact the cluster; it never submits, cancels, adopts or
retries work. A missing or unfinished execution receipt remains unknown. A
refresh error preserves known IDs and carries `observation_error` evidence.
MVP10.3c.3 uses SelectionError for missing/inaccessible/malformed local receipts,
with exact receipt_path and original cause, replacing raw file/JSON/protocol
errors. An absent receipt directory lists no items; an unreadable directory or
broken receipt raises explicitly. SubmissionError keeps the authoritative receipt
and any adopted local persistence diagnostic; preserve both. A failed local write
does not prove Slurm rejected a job. Tracking failures may add tracking_diagnostic.
`asl submission` supports --debug, stderr/exit1 and --json diagnostics; failed
refresh JSON keeps receipt/ID fields with additive diagnostic where available.

```sh
asl submission --bundle STUDY
asl submission /absolute/local/receipt.json --json
asl submission /absolute/local/receipt.json --refresh --json
```

ACP `list_submissions` accepts an optional `bundle`; `inspect_submission` requires
`receipt_path` and accepts explicit `refresh: true`. Both expose the same plain
receipt. Reading a partial/uncertain receipt can succeed as an inspection; check
its state rather than treating a successful read as accepted compute. Ordinary
cleanup retains receipt-bearing tracking snapshots, including ones without IDs.

## Inspect and hand off

`load_bundle_from_path` reads recorded IDs/machine, not fresh scheduler evidence.
`recorded_execution(submission_path, job_name)` reads the job's producing roots,
logical/resolved paths, working directory and transport identity. It does not
discover today's profile. Use
`resolve_results_path(relative, bundle_path=submission_path, job_name=job_name)`
or `path_exists(relative, bundle_path=submission_path, job_name=job_name)` to use
those producing roots/transport even after profile edits. A legacy record without
execution evidence fails explicitly; select its original profile yourself.
These records preserve locations, not immutable code/input contents or scheduler
observations.

MVP3 provides one structured observation pipeline for Python, ACP and terminal:

```python
from autoslurm import list_runs, inspect_bundle, inspect_logs

runs = list_runs(bundle_name="study")  # Local discovery, no cluster calls.
view = inspect_bundle(receipt_path=receipt_path)  # Exact tracking snapshot.
failed = [task for job in view["jobs"] for task in job["tasks"]
          if task["state"] in {"FAILED", "TIMEOUT", "OUT_OF_MEMORY"}]
detail = inspect_logs(receipt_path=receipt_path, job_name="shards",
                      task_index=1, stream="both", tail=40)
cached = inspect_bundle(receipt_path=receipt_path, refresh=False)
```

`inspect_bundle(bundle_path)` is the other exact selector; provide one path or
receipt, never both. Inspection overlays known IDs from its local receipt in
memory; it never edits the definition, tracking snapshot or receipt. To fetch
updated remote submission evidence first, use explicit `refresh_submission`.
Inspection queries queue and accounting once per producing machine across the
selected runs (`inspect_bundles(paths)` batches them). It never submits work.

| Evidence | Meaning and next step |
|---|---|
| `state`, `jobs[].state`, `tasks[].state` | Scheduler aggregate and concrete task states; completion requires every expected task, and parent failure stays visible |
| `jobs[].submission_state`, `submissions` | Submission evidence, separate from scheduler progress; an uncertain receipt remains uncertain even when a known job is observable |
| `tasks[].job_id`, `parent_id`, `task_index`, `raw_id` | Canonical `parent_index`, array index and distinct accounting raw ID; step rows are excluded |
| `observed_at`, task `source` | Observation time and queue/accounting provenance; queue wins when both report a task |
| `reason`, `exit_code` | Scheduler evidence, not an inferred diagnosis; absence stays null |
| `freshness: fresh` | Queries returned; empty rows still leave tasks `UNKNOWN` |
| `freshness: partial` / `failed`, `errors` | Some or all evidence failed; retain known observations and report the query/transport error |
| `freshness: stale` / `never` | Explicit cached read or no matching saved observation; never claim current state from these |
| `last_observed` | Prior observation's state/time, explicitly stale after a failed refresh |

MVP5 isolates bad records from healthy observations in the same machine batch.
Malformed producing metadata never redirects a remote job to local Slurm.
Observation caches contain scheduler/receipt evidence; log/script errors belong
to the particular artifact request and do not contaminate later status-only
reads. Invalid caches are reported as unavailable evidence. A cache-write error
keeps current scheduler observations and fetched log text available, with explicit
cache errors and partial freshness. Adopted cache/receipt errors include a plain
diagnostic with exact local path, cause and actual publication facts. A genuine
cache miss stays quiet; failed evidence does not become an empty successful read.
Cached log excerpts retain their task identity
and cannot be relabelled for another job sharing an output path.

Missing declared array tasks remain `UNKNOWN`; parent state never fabricates
individual task completion, failure or reasons. `COMPLETED` means scheduler
completion. Validate scientific outputs, shard compatibility and reducer results
in the application. Do not trigger retries from state aggregation or log text.

```sh
asl status --bundle-file /absolute/saved/run.json --array
asl inspect --receipt /absolute/local/receipt.json --json
asl logs --receipt /absolute/local/receipt.json --job shards --task 1 --stream stderr --tail 40
asl inspect --receipt /absolute/local/receipt.json --cached --json
```

CLI/Python/ACP status and requested logs are fresh by default. `asl logs` reads
logs immediately. Humans can use `asl logs 1 --job 2` with the bundle/job indices
from `asl status`, or `asl logs 1 --array --job 5` for an expanded array row.
`--task N` selects the actual Slurm task index; `--array` filters match status
and apply before file limits. Names/ranges/latest/date selection and `--view`
are also supported. Indices can move; agents retain exact `--bundle-file` or
`--receipt` paths in durable handoffs. An empty command shows help.
`inspect_logs` returns the same structured view as `inspect_bundle(include_logs=True)`.
ACP `inspect_run` accepts `include_logs=True` and `stream` (`both`, `stdout`, `stderr`).
With `refresh=False` / `--cached`, neither scheduler nor source logs are queried,
locally or remotely. Available cached excerpts are stale; `not_cached` means no
matching excerpt. Increasing limits cannot recover text never cached. Script-only
CLI reads can use `--cached`; scripts are separate local artifacts.

Logs use saved producing roots/cwd and exact job/task identities, including raw
IDs for `%j`, and support `%x`, `%j`, `%A`, `%a`, `%%`. Unsupported placeholders
or absent producing metadata produce explicit errors. An unsubmitted draft does
not adopt a same-name log. Logs default to 40 lines, at most 64 KiB read per file
and 20 files. Python/ACP accept `tail`, `max_log_bytes` (up to 1 MiB), `max_logs`
(up to 100); omitted/truncated content is marked and full paths retained.
`asl logs` exposes these as `--tail`, `--max-bytes`, `--max-logs`. Filter by
job/task/stream before applying file limits. Combined stdout/stderr is one entry
with `streams: ["stdout", "stderr"]`; selecting stderr cannot separate mixed text.
Available entries include `path`, `machine`, job/task identity, `observed_at`,
`freshness`, `bytes_read`, `bytes_returned`, `empty`, `truncated` and
`changed_during_read`. Empty differs from missing, error and not_cached. Permission
and transport failures mean unavailable evidence. Concurrent change is flagged;
refresh for a newer excerpt. Read only regular files, never scan directories or
fetch scientific datasets/results. Cache errors retain live text with errors;
inspect partial evidence before any diagnosis. Log text never authorizes retry.

`sync_machine` / `asl sync` remain broader profile-based storage operations:
immutable existing job/script files are retained; logs refresh with checksum
comparison, including append/replacement/truncation. Use exact run inspection
for producing-run identity and custom logs. Sync does not fetch submission
receipts or arbitrary application results.

A fresh agent needs lane/interpreter/import/revision, machine/root, exact receipt
path/submission ID and last recorded submission outcome, client input
and output namespace, exact planned and submission references, job/task IDs,
actions already taken, observation time/errors and next safe action. Missing
accounting rows/logs mean unknown evidence, not successful science. Keep excerpts
bounded and reference full artifacts. Exclude credentials.

`examples/reference_client/` demonstrates one job and four shards followed by a
reducer. Its application does not import AutoSlurm; tests exercise this recipe
with temporary state and mocked submission commands.

## Configuration and transfer failures

`config` is the canonical command; `configuration` and the installed
`autoslurm-configuration` entry point remain aliases. Python implementations live
in `config`; clients keep importing supported functions from `autoslurm`.
The Python configuration API and terminal editor share one configuration writer.
Reading local profiles, saving/selecting definitions and cached inspection do not
contact a cluster. Remote root discovery and transfers are explicit operations;
a supplied execution context keeps its recorded profile and roots.

`sync` raises on a connection/probe/copy failure. A reported missing remote
directory is distinct from a transport failure. It copies jobs/scripts using the
existing ignore-existing policy and refreshes mutable logs using checksums;
it does not reconcile receipt state or recover submissions. Interrupted copies
may leave partial local transfer results, so inspect the exact run's evidence.
Never infer scheduler acceptance from a copy outcome or retry compute submission
as a remedy for a transfer failure.

Client imports stay under `autoslurm`. Public exports are explicit; accidental
imports of typing helpers or dataclass utilities are removed. Internal module
aliases remain for compatibility and do not replace this supported recipe.

An old profile containing only `project_root` is read as `results_root`; equal
old roots are coalesced. Conflicting old roots are rejected until the operator
explicitly chooses one with `asl config --machine NAME --results-root PATH`.
That edit drops the old setting but never moves input/output files. Retain the
existing data or prepare it at the selected location before submitting new work.
Saved runs remain readable using their original input/result roots; new execution
records contain `software_root` and `results_root`, with no duplicate project root.

MVP7.0d removes hostname/hosturl/username/key_path from current profile writes,
editor prompts and submit/schedule overrides. Use `--ssh-alias` for explicit
selection; omit it for a local profile. Old hostname aliases normalize on read/save;
old explicit host/user profiles need an explicit alias choice through config.
New run transport evidence contains only the alias. Historical recorded connection
fields remain readable for existing runs and are never rewritten implicitly.
The saved alias refers to the current SSH config entry: editing that entry can
change its destination. AutoSlurm does not snapshot or resolve SSH credentials or
hostnames. Inspect connection failures rather than substituting another profile.
