# Experiment context

Use the structured `inspect_bundle` / ACP `inspect_run` contract in
`01_client_workflow.md` and `09_task_inspect.md` for operational decisions.
One shared pipeline provides scheduler state, task IDs, evidence and bounded
stdout/stderr to both programmatic and human interfaces.

`experiment_context(bundle_name, desired_date=None)` is a human overview with
saved identity, status, scripts and bounded log tails. Selection by date is
nearest-date. It uses recorded producing transport/paths directly; it does not
run or parse a remote context command. It can contact the producing cluster.
The Python string is presentation, not a serialized bundle or structured API.

The historical `autoslurm-experiment-context` entry point forwards to the
inspection CLI. Use `--full` for scripts and bounded logs, `--refresh` for remote
log tails, `--cached` for no network calls, and `--bundle-file` or `--receipt` for
exact identity. Name selection alone shows the shared job table.

```sh
asl inspect --receipt /absolute/receipt.json --json
asl inspect --bundle-file /absolute/run.json --full --refresh --tail 40
asl inspect --bundle-file /absolute/run.json --cached --script
```

Logs are bounded excerpts with exact references. No unsubmitted draft or
same-name unrelated job adopts a log. For scientific validation, use the
application's output manifest/checks rather than inferring correctness from logs.
