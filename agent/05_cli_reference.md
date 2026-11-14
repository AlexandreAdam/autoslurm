## CLI Reference for Agents

Snapshot/filter selection failures in filter/submit/status/inspect/logs use shared
diagnostics: stderr and exit 1, `--debug` for original causes; existing `--json`
status/inspect/logs modes return the shared error envelope. Parser usage remains
exit 2. Failed discovery entries carry a diagnostic and remain visible; unknown
contents are not empty jobs. These additions cover selection/configuration, not
all scheduler/log/post-dispatch errors. `asl submit` also renders adopted path/render
preparation failures with job/field/machine/bundle identity and supports `--debug`.
Installed `15_diagnostics` describes limits.

`asl schedule` uses shared diagnostics for adopted authoring failures (stderr,
exit 1). `--autoslurm-debug` preserves original errors; application `--debug`
retains its forwarding behavior. Help discovery remains heuristic; prefer trusted
typed contracts for client integration. Publication and process
diagnostics are separate adoption tasks; this is not universal CLI/ACP parity.

- `asl software status --machine NAME`: read Git project status under the configured
  software_root; `--project` is relative to that root. Add `--local-project PATH`
  or `--requirements FILE` for focused environment comparisons, and `--dependency`
  to include another major library. `--package`, `--expected-version` and
  `--expected-commit` override application expectations. `--json` returns one
  evidence object; mismatch/unknown checks exit 1. This performs read-only SSH,
  with no fetch/install/jobs or requirement for a newer remote AutoSlurm.
- `autoslurm-schedule <script>`: schedules or appends jobs. Recognizes SLURM flags (`--time`, `--mem`, `--gres`, etc.), dependencies (`--dependencies`), bundles (`--bundle`/`--append`), pre-commands (`--pre-commands`), and machine overrides (`--machine`, `--ssh-alias`). Use `--job-name` to override the job identity stored inside the bundle; without it the script name is reused, and AutoSlurm appends `_001`, `_002`, etc., when duplicate job names appear in the same bundle.
- `autoslurm-submit <bundle>`: submits the most recent bundle matching the name. Add `--machine` or an SSH alias override if you need a non-default endpoint.
- `asl config --interactive`: manage machine profiles. `--summary`/`--view` inspect local configuration; `--machine NAME --ssh-alias ALIAS --software-root PATH --results-root PATH` saves the alias/two roots without remote commands. `results_root` covers inputs, working directories and outputs. `configuration` remains a compatibility alias.
  **Edit machine fields** includes an optional **Environment setup command**
  (`env_command`) after the venv path. Enter keeps it, a command replaces it and
  `-` removes it. Creation offers the same prompt. Setup precedes venv activation
  in jobs and config validation; interactive edits retain post-save validation.
  Known configuration failures exit 1 with path/field/cause/action; `--debug`
  preserves original exceptions. Existing unreadable/corrupt files are retained,
  and only observed absence starts first-use creation. `--view` keeps raw JSON.

- `asl status --bundle-file PATH --array`: fresh shared status and task evidence;
  `--json` returns structured observations (a list); `--cached` avoids cluster calls.
- `asl inspect --receipt PATH --json`: exact structured run observation;
  `--bundle-file PATH` is the other exact selector. A single run is a JSON object.
- `asl inspect --receipt PATH --job NAME --log --refresh --tail 40`: selected
  bounded producing stdout/stderr. Remote log fetch is explicit; cached reads
  never contact the cluster. `--script --cached` reads saved scripts locally.
- `asl submission PATH --refresh --json`: fetch execution-side submission
  evidence separately; never resubmits. Without refresh reads the local receipt.

Name/date/index/latest are convenience selectors; retain exact paths in handoffs.
`--date` is nearest-date selection. Inspect freshness/errors before using state.
