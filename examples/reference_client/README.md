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

From the development checkout, install into its isolated environment using
already available build tools:

```sh
../venv/bin/python -m pip install --no-index --no-build-isolation --no-deps -e examples/reference_client
cd examples/reference_client
../../../venv/bin/science-demo --mode single --input-file data/measurements.json --output-dir demo-output/run1
```

The direct call writes a local summary without Slurm. Choose a fresh output
directory for each study. Here it is relative to the application directory;
AutoSlurm bundle output arguments are instead relative to the results root.

## Exercise AutoSlurm with mocked Slurm

From the development checkout:

```sh
../python -m pytest -q tests/integration/test_reference_client.py
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
incomplete reduction. Input `data/measurements.json` is relative to this application
directory; `output_dir` and declared `parts_dir` use AutoSlurm's results root.
AutoSlurm does not yet establish the application directory or copy inputs.

Read the [current client recipe](../../agent/01_client_workflow.md) for exact
selection, installation ownership, operations and failure handling. This example
does not promote development code or authorize cluster access.
