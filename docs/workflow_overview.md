# From a scientific question to trustworthy run evidence

AutoSlurm connects your scientific application to Slurm. You or an agent describe
the computation, resources and dependencies; AutoSlurm resolves machine paths,
prepares scripts, submits the jobs and exposes evidence about what happened.
Your application remains responsible for the science and its results.

This page describes the development workflow through MVP7.1. The user activated `dev`
in the main repository for local daily use through base Conda on 2026-11-12.
Tests use isolated state and mocked Slurm/SSH. A baseline rollback checkout is
retained; the cluster installation has not been changed or validated.

## The map

```text
Scientific application: command + relative inputs + independent outputs
       |
       v
Saved definition --> path preview --> submit once --> exact receipt/run path
                                                       |
                                                       v
                                      status + task evidence + bounded logs
                                                       |
                                                       v
                             application validates results; human decides next
```

Saving a definition publishes a complete record. Rapid scheduling creates distinct
snapshots, and appending several jobs updates the file once. Configuration changes
use the same protected writer. A save failure needs inspection before dispatch;
a copy failure is reported separately and never triggers another job submission.

A machine profile maps two locations: software/code and shared scientific data
(inputs, working directories and results). Use `asl config` to set `software_root`
and `results_root`. `asl software update --machine NAME --project PROJECT`
runs `git pull --ff-only` in the one existing checkout under `software_root`.
Its current tracking branch determines what gets updated. Local changes and
non-fast-forward history block the pull; there are no clones, source caches,
additional environments or release records. The command refreshes the editable
project installation in the configured environment after every successful pull,
including unchanged HEAD. Dependencies remain machine-owned. Submission stays independent and
uses the configured environment. The [walkthrough](software.md) and
[agent recipe](../agent/13_software_preparation.md) document the interface.

Before choosing a run, `asl software status --machine NAME` shows the machine's
project branches, commits and local changes. Add `--local-project PATH` to compare
the important declared dependencies and desired application revision against
its configured Python environment. Matching version strings can still hide a
different Git revision. The report flags mismatches and unknowns, and reads
metadata without loading scientific libraries or modifying the cluster.
Application definitions keep relative paths, so they do not branch on machine
names or embed cluster filesystem prefixes. Compute nodes use prepared software;
they do not need Git access or package downloads inside jobs.

Preview and submission now share the same preparation checks. Preview rejects
invalid or already-submitted work; existing runs use inspection. Submission stages
the prepared script unchanged and supplies dependencies directly to Slurm.

A saved definition describes intended work. A submission receipt records what
Slurm accepted, rejected or left uncertain. An observation records what queue
and accounting reported at a particular time. These answer different questions.
Keep their exact references when asking another agent to continue a study.

## An example: four shards and a summary

The [reference application](../examples/reference_client/README.md) runs either
one small calculation or four array shards followed by a reducer. Its numerical
code does not import AutoSlurm. Each shard writes its own output; the reducer
checks that every expected shard exists and matches the study inputs.

After authorized submission, retain the receipt path returned by `submit_jobs`.
For a terminal session, replace these paths with that run's actual references:

```sh
asl status --bundle-file /absolute/saved/run.json --array
asl inspect --receipt /absolute/local/receipt.json --job shards --log --refresh --tail 40
asl inspect --receipt /absolute/local/receipt.json --cached --json
```

The array view keeps missing tasks unknown, shows observed failure reasons and
exit codes, and distinguishes a failed query from a failed job. An observed
parent failure stays visible even if individual task records are unavailable.
Log excerpts use the producing run's recorded paths and exact task IDs. Refresh
updates growing or replaced logs; excerpts remain bounded and reference full
artifacts. Cached scheduler evidence is explicitly stale. Invalid records are isolated
from healthy jobs; unavailable caches never turn missing evidence into success.
A failed log/script read belongs to that request, so it does not contaminate
later status-only inspection.

If a connection drops during submission, retain its receipt and inspect that
operation before deciding what to do next. Repeating submission can duplicate
work. If Slurm reports completion, validate the application outputs before
claiming a successful scientific result.

## Working with an agent

Give the agent the selected installation, study inputs/output namespace, exact
receipt/run paths and the action you authorize. The agent should use public
structured inspection, report observation time/errors, select relevant log tails
and preserve a handoff. You should be able to understand the run and its next
step without reading backend code.

The [client workflow](../agent/01_client_workflow.md) supplies the detailed
application design and operating contract for agents. Internal modules, storage
layouts and transport details are maintained behind that interface; client
software should not depend on them. The fuller documentation site, packaged
agent resources and public distribution remain later release work.
