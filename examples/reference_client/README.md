# Scientific client example

This small application computes the sum of squares of four measurements. The
application owns input validation, task outputs and reduction; AutoSlurm owns
job definitions, dependencies, submission and tracking. The application has no
AutoSlurm dependency.

The expected summary is `count=4`, `sum_squares=30`. The array produces four
distinct parts and a reducer that rejects missing or incompatible parts. Its
small input digest check illustrates application validation, not a general
provenance or retry system.

## Run the application locally

From the main repository, install into its isolated test environment using
already available build tools:

```sh
.development/python -m pip install --no-index --no-build-isolation --no-deps -e examples/reference_client
cd examples/reference_client
../../.development/venv/bin/science-demo --mode single --input-file data/measurements.json --output-dir demo-output/run1
```

The direct call writes a local summary without Slurm. Choose a fresh output
directory for each study. Here it is relative to the application directory;
AutoSlurm bundle output arguments are instead relative to the results root.

## Exercise AutoSlurm with mocked Slurm

From the main repository:

```sh
.development/python -m pytest -q tests/integration/test_reference_client.py
.development/python -m pytest -q tests/integration/test_execution_paths.py
.development/python -m pytest -q tests/integration/test_submission_safety.py tests/integration/test_job_environment.py
```

Tests create a temporary console launcher equivalent to the installed entry
point; no package installation or download occurs in tests. They use temporary
state, replace `sbatch`, execute generated scripts locally and check results and
saved IDs. The mock runs immediately; it does not emulate queue timing or full
Slurm scheduling behavior.

| Fixture | Workload | Expected evidence |
|---|---|---|
| [single.json](bundles/single.json) | One job | One ID and a validated summary |
| [array.json](bundles/array.json) | Four-task array and dependent reducer | Parent/reducer IDs, `afterok` dependency, four parts and a validated summary |

Tests introduce a newer competing draft: explicit selection must keep the chosen
historical definition. They also verify nonzero exits for missing inputs and
incomplete reduction. Input `data/measurements.json` is declared in `input_args`
and resolved under the profile's absolute `results_root`, as are `output_dir`
and declared `parts_dir` (default: selected storage's `results/`). AutoSlurm uses
that same data root for the working directory when roots are configured, or a
job's relative `working_directory`. `software_root` separately locates managed
code/environments. Required inputs are validated without copying them. Machine roots and prepared environment locations are infrastructure
configuration; bundle definitions keep application paths relative.

The path tests run the array/reducer under two distinct profiles from an unrelated
directory, including paths with spaces and activation that changes directory.
They compare preview, execution and saved paths, check failures before submission,
and recover artifacts using saved roots after a profile edit. Mocked remote
tests check one root probe and one batched input check, including missing inputs.

MVP2 adds receipt tests around the same submission boundary: first-job acceptance
survives a second-job rejection, response loss never dispatches again, exact
refresh recovers execution-side IDs, and unfinished helpers leave unobserved work
uncertain. Per-job environment tests check literal exports and runtime CPU/thread
variables. Scheduler acceptance and a successful scientific summary are separate
checks; AutoSlurm does not infer scientific validity from an ID.

Read the [current client recipe](../../agent/01_client_workflow.md) for exact
selection, installation ownership, operations and failure handling. This example
does not promote development code or authorize cluster access.

## MVP9.1: one typed command declaration, experimental authoring proof

[typed_science_demo.py](typed_science_demo.py) adds a separate optional Typer CLI
without changing the existing argparse demo or its fixtures. Its single function
declares required named paths, an integer with a minimum, a numeric offset, a
string label and a default-off flag. The command still runs without AutoSlurm:

```sh
science-typed --input-file data/measurements.json --output-dir demo-output/typed --repeat 2 --offset 0.5 --label pilot --include-values
```

It writes count 8, sum_squares 82 and the original values. Install the example's
`typed` extra when choosing to use this command; it needs Typer 0.27. Current
tests already have this dependency and create a temporary launcher without an
install. The original `science-demo` retains no Typer or AutoSlurm dependency.

From a workstation Python builder, the **experimental internal proof** uses the
same declaration (run from this example directory with the test interpreter):

```python
from typed_science_demo import app
from autoslurm.typer_adapter import from_typer
from autoslurm import save_bundle

command = from_typer(app, script="science-typed", input_args=("input_file",))
job = command.job(
    name="sample",
    script_args={"input_file": "data/measurements.json", "output_dir": "typed/run",
                 "repeat": 2, "offset": 0.5, "label": "pilot", "include_values": True},
    slurm={"time": "00:01:00", "mem": "64M"},
)
planned_path = save_bundle({"sample": job}, "typed-demo")
```

`command.describe()` exposes JSON-serializable option/default/range/path metadata.
`command.validate(values)` and `.job(...)` reject unknown/missing names, wrong
native types, non-finite numbers, out-of-range values and control characters before
save. Integers are accepted for numeric/float options and materialized as floats;
booleans are never accepted as integers. Static defaults, including False, remain
visible in script_args. Input availability, machine roots, Slurm resources and
scientific validity still use their existing application/AutoSlurm owners.

The adapter supports one plain Typer leaf app with add_completion=False, canonical
flag names and scalar annotations. It inspects metadata without parsing options
or running scientific/parameter callbacks. It rejects app/option callbacks,
prompts, environment/default factories, custom parsers, forward annotations,
custom flags, lists/tuples and default-on booleans; a version/capability mismatch
fails explicitly. Nonempty strings can contain spaces, quotes and shell
metacharacters. The shared MVP9.2 compiler receives resolved paths and quotes
every literal value; no manual shell escaping or runtime expression goes in
script_args. CSV remains the list convention. Default-off booleans remain flags.
For example, `label: "pilot's first run"` stays readable in JSON and becomes
one quoted CLI value. The reference execution test verifies the exact label.

This proof is not a public authoring API or a replacement for the supported
client recipe. It is intentionally absent from AutoSlurm's top-level exports.
The saved JSON contains only existing fields: name, script, script_args, slurm
and declared path roles, plus ordinary snapshot metadata. It stores no callback,
framework object, contract schema or hidden config payload. Loading/submitting
this JSON does not rediscover the declaration or certify its options against a
newer command version. A client must explicitly revalidate against its current
trusted declaration when that assurance is needed. Broader saved-contract and
public integration guarantees remain MVP9.3 release decisions.

Verification (mocked scheduler, disposable local files and launchers):

```sh
.development/python -m pytest -q tests/unit/test_command_contract.py tests/integration/test_typed_reference_client.py
```

Run that verification from the repository root. It checks real parser round-trips,
readable default-filled JSON, invalid settings without writes, preview/execution
agreement under a results path with spaces and an accepted receipt plus scientific
output. No cluster, external scientific application or daily config is touched.
