[![Docs](https://readthedocs.org/projects/autoslurm/badge/?version=latest)](https://autoslurm.readthedocs.io/en/latest/?badge=latest)
[![codecov](https://codecov.io/gh/Ciela-Institute/autoslurm/graph/badge.svg?token=Pk5zRgoJCb)](https://codecov.io/gh/Ciela-Institute/autoslurm)

# AutoSlurm

`autoslurm` is a package that simplifies the process of scheduling and
running jobs on a SLURM cluster. It provides an abstraction layer over the SLURM
shell scripts and provides the following features:

- Reproducibility of job configurations
  - User-agnostic scheduling
  - Reproducible configurations saved JSON
  - Automated submission
- Submitting multiple jobs together 
- Inspecting job status and logs
- Dependency management between jobs 
- Remote jobs submission 

## Documentation

You can find the full documentation [here](https://autoslurm.readthedocs.io/en/latest/).

For the local development refactor, start with the
[human workflow overview](docs/workflow_overview.md), the
[current client workflow](agent/01_client_workflow.md) and
[scientific example](examples/reference_client/README.md). Current profiles use
`software_root` for code/environments and `results_root` for inputs, working
directories and outputs. `asl config` edits or displays these two locations.
Remote profiles store only `ssh_alias`; SSH config owns server/user/key settings.
The same relative workload can run under different machine profiles without
changing the application. Preview checks paths before submission; saved execution
locations let an agent find a run's results after a profile changes.

MVP2 records accepted job IDs as submission progresses and stops safely on
rejection or an uncertain response. `submit_jobs` returns a receipt;
`SubmissionError.receipt` preserves partial evidence. Use `asl submission` to
list receipts or inspect an exact receipt, with explicit `--refresh` to retrieve
remote execution evidence. Refresh never submits work again. Submission success
means Slurm accepted the jobs; the application still validates scientific results.

MVP3 adds `inspect_bundle` and `list_runs`, with ACP `inspect_run`/`list_runs`
and exact terminal selectors. They share task identity, scheduler evidence and
bounded logs, retain query errors and unknown tasks, and label cached evidence
stale. Remote log refresh uses recorded producing paths; broader sync refreshes
growing/replaced logs while preserving existing definitions.

MVP4 makes preview and submission share one preparation path and separates
submission records, script staging, dispatch and evidence persistence. Validated
scripts stay unchanged; local and remote dependencies use scheduler arguments.

MVP5 separates inspection collection, state calculation, caching and artifact
retrieval. Bad records and cache failures preserve healthy/current evidence;
selected log/script errors stay separate from cached scheduler status.

MVP6 separates local persistence/selection, configuration and file transfer, with
explicit public exports. Complete atomic writes protect records, rapid scheduling
cannot overwrite snapshots, and sync distinguishes connection failures from
missing directories.

Scientific software owns computation, input/output validation and task reduction.
AutoSlurm owns machine mapping, submission and tracking; agents use its public
interface and detailed operating guide. The main checkout is now branch `dev`,
used by base Conda's editable installation. Tests use isolated state and mocked
Slurm; the earlier baseline remains available in a rollback checkout. Cluster
installations have not been changed.

MVP7.1 adds the first Git software layer: shared bundle requests, fresh upstream
revision resolution, first-time cloning and isolated exact-commit source sets.
The explicit Python operation acts on its current preparation host. Environment
installation, remote preparation commands and managed-runtime submission remain
planned. See the [source preparation recipe](agent/13_software_preparation.md)
and [software preparation scope](REFACTORING_DOCS/design/MVP7_cluster_software_preparation.md).

## Installation

### Install the `autoslurm` package

```bash
git clone git@github.com:Ciela-Institute/autoslurm.git
cd autoslurm
pip install -e .
```

### Configure `autoslurm` for your environment

```bash
asl config --interactive
```

This command will configure the user-specific details required to connect to
remote SLURM machines and activate virtual environments.
More details can be found in the [AutoSlurm Configuration](#configure-autoslurm-for-your-environment) section.

### Register your application in the `pyproject.toml` file of your package

```toml
[project.scripts]
my-script = "my_package.module:main"
my-script-cli = "my_package.module:cli"
```

More details can be found in the [Register a script](#register-your-application-in-the-pyprojecttoml-file-of-your-package)
section.

## Basic Usage

### Schedule a job

```bash
autoslurm-schedule my-script --bundle=my-script \
    # Application args
    --my_job_arg1=arg1 \
    # SLURM args
    --time=00-01:00 \
    --cpus_per_task=1 \
    --gres=gpu:1 \
    --mem=16G
```

This command schedules `my-script` to run for 1 hour, using 1 CPU, 1 GPU, and
16GB of memory. Note that both the application-specific arguments and SLURM
arguments are passed in the same command.

The `--bundle` argument is optional and is used to specify the bundle name (the
JSON file that stores one or more jobs). If not provided, the script name is
used. Use `--job_name` if you need to rename the specific job entry within the
bundle.

### Submit a job

Once the job is scheduled, you can submit it at any time just by using the name
of the application.

```bash
autoslurm-submit my-script --machine=machine
```

This command submits `my-script` on the `machine` name specified in your
configuration (see [AutoSlurm Configuration](#configure-autoslurm-for-your-environment)). You can also
schedule and submit a job at the same time to skip a step.

```bash
autoslurm-schedule my-script --submit --machine=machine\
    # Application and SLURM args
    ...
```

### Inspect jobs and logs

Use `autoslurm logs` to inspect scheduled bundles without dumping the full
bundle JSON by default.

```bash
autoslurm logs
autoslurm logs my-bundle
autoslurm logs my-bundle --job my-job --status
autoslurm logs my-bundle --job my-job --logs
autoslurm logs --latest --log
```

This prints compact bundle and job summaries, SLURM status for a selected job,
or the newest `.out` log when you need to check a run quickly.

You can also submit the most recently saved bundle directly:

```bash
autoslurm submit --latest
```

### Schedule multiple jobs

Use the `--append` keyword to include additional jobs in a bundle. Use the
`--bundle` keyword to specify the name of the bundle.

```bash
autoslurm-schedule job1 --bundle=my-bundle
autoslurm-schedule job2 --append --bundle=my-bundle
```

You can then submit the bundle using the `autoslurm-submit` command.
```bash
autoslurm-submit my-bundle --machine=machine
```

In case `--append` is not used, two bundles will instead be created.
Each job will have a unique timestamps.
```
$AUTOSLURM
└─ jobs
    ├─ my-bundle_210901120000
    └─ my-bundle_210901120001
```
Furthermore, only the last bundle created will be submitted in the last example,
instead of both. This is because the default behavior is to submit the last bundle created.

<!--TODO:-->
<!--If you wanted to launch a bundle created previously to the last one, -->
<!--you can use the `--date` argument. The bundle submitted will be the -->
<!--one closest to the date specified (in an absolute sense).-->
<!--```bash-->
<!--```-->

### Schedule jobs with dependencies

Dependencies can be set by specifying the name of the job
using the `--dependencies` argument.
```bash
autoslurm-schedule job2 --append --bundle=my-bundle --dependencies job1
```
In this example, `job2` will only be submitted once `job1` has completed.

Multiple dependencies can be added as follows
```bash
autoslurm-schedule job3 --append --bundle=my-bundle --dependencies job1 job2
```

<!--TODO-->
<!--The `--dependency_type` argument specifies the type of dependency. The default-->
<!--is `afterany`.-->

**Notes**:

- Any dependency loop will be detected and raise an error (e.g. if job1 depends
  on job2 and vice versa).
- Order in which jobs are appended is not important. Jobs are sorted in
  topological order before submission.
  <!--- `--dependency_type` can be a list of same length as `--dependencies` or a-->
    <!--single value to be broadcasted.-->
