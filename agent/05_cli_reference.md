## CLI Reference for Agents

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
