# Changelog

Package checkpoints use Python-compatible versions. See
[the versioning policy](docs/versioning.md) for bumps, tags and publication gates.
Entries describe observable behavior and compatibility; detailed task evidence
remains in [PLAN.md](PLAN.md). A checkpoint entry does not imply PyPI publication.

## Unreleased

Changes after the latest versioned checkpoint belong here until the next bump.

## 0.2.0.dev7 — 2026-11-16

- New remote submissions create an exact cluster-side tracking snapshot before
  the first scheduler call. Incremental accepted IDs are mirrored after durable
  receipts; cluster-local status, logs, inspect and fetch use local Slurm and
  producing paths without workstation files, profiles or SSH to themselves.
- Origin receipt paths/transport stay intact. Additive execution_bundle_path
  identifies the cluster view; new remote execution receipts use the distinct
  `.execution.json` suffix, including when both machines have identical path
  names. Independent attempts never replace existing drafts or tracking files.
- New remote submissions require helper capability execution_tracking=1 as well
  as submission_protocol=1. Update AutoSlurm at both ends before using this
  behavior; no automatic helper install or historical draft/receipt migration.
  Partial acceptance, lost-response recovery and replay protection are retained.

## 0.2.0.dev6 — 2026-11-16

- `asl fetch`, public `fetch_run` and ACP `fetch_run` refresh exact linked receipts
  before status and bounded log excerpts, reusing existing selectors, inspection
  and caches. Cached fetch has no remote receipt or source-log reads, and no
  projection/cache writes.
- Partial receipt/persistence failures retain known or newly recovered IDs and
  available logs. Error/freshness fields remain explicit; CLI JSON/text retains
  partial results and exits 1 for collection failures. No submission retry.
- Remote receipt refresh replaces unbounded cat with the existing standalone
  regular-file reader, capped at 1 MiB and 30 seconds, with shared diagnostics for
  missing, unreadable, changing, oversized/malformed and transport failures.
  Remote python3 is required; no remote AutoSlurm installation is needed.
- Log bounds and inspect/logs defaults are unchanged. Fetch follows recorded
  paths/transport and exact receipt links, without scientific-result transfer,
  receipt guessing or whole-directory mirroring. Legacy sync remains separate.

## 0.2.0.dev5 — 2026-11-16

- Optional machine module_init records an absolute trusted module initialization
  file. New jobs source it only when module is missing, verify module availability,
  run env_command and activate venv_path, with shared setup generation.
- Config adds --module-init, --clear-module-init, explicit --detect-module-init,
  an interactive field/detection action and a summary column. Detection checks
  common readable site files without executing setup and preserves configuration
  on failure, with shared diagnostics. It does not establish compute readiness.
- Job setup/activation failures stop before the application with the failed field,
  including legacy profiles without a working directory. Profiles without a module
  initializer need no module system. Existing scripts/receipts remain unchanged.
- No global login-profile sourcing, activation preflight, helper launch-policy
  change, runtime file guessing, package installation or submission retry.

## 0.2.0.dev4 — 2026-11-16

- Software-update errors identify the exact failing check, selected machine,
  project and executable. A stale venv reports its attempted `bin/python`, points
  to `venv_path` in `asl config`, and confirms pull/install did not start.
- SoftwareUpdateError retains its evidence and native local cause, and now
  supplies a shared diagnostic also present in its JSON evidence. Standalone SSH
  probes return validated plain failure facts; no remote AutoSlurm is required.
- Separate Git-pull and editable-install effects distinguish not started,
  completed, partial and unknown work. Failed installs keep observed commits and
  a bounded, redacted pip tail. Lost/invalid SSH responses remain unknown without
  retry; generic communication errors do not imply that nothing ran.
- Invalid update requests use existing InvalidRequestError/ConfigurationError
  families, retaining ValueError compatibility. Invalid explicit machine values
  no longer silently choose the default. Unexpected updater bugs propagate.
- `asl software update` renders adopted errors once to stderr/exit 1; `--json`
  preserves evidence with additive diagnostic and `--debug` re-raises original
  errors. Broader SSH/helper/transfer/status adoption remains MVP10.4b–d.
- In-place pull, default editable install, operator-owned dependencies and
  single-checkout policy are unchanged. No saved schema/history migration.

## 0.2.0.dev3 — 2026-11-16

- Receipt reads use SelectionError for missing, inaccessible or invalid local
  evidence, replacing raw file/JSON/protocol exceptions at this development
  boundary. Receipt listing reports a broken record or denied directory instead
  of silently omitting it. Empty/missing receipt directories still yield no items.
- Bundles, receipts and caches share regular-file UTF-8 JSON reading, including
  nonblocking special-file checks, absence rechecks and primary/secondary close
  evidence. Low-level read diagnostics use operation `record_read`; selector and
  saved-graph validation retain their existing families. No history is rewritten.
- Receipt/projection writes identify their submission and preserve known IDs and
  actual publication/durability facts. Existing SubmissionError wrappers and ACP
  retain adopted diagnostics alongside authoritative receipts; submission policy,
  retries and scheduler acceptance semantics are unchanged.
- Generated and staged Slurm scripts use the same atomic publication owner as
  JSON records. A failed write retains old bytes or a complete published script;
  scripts carry job/receipt context where known. RecordWriteError also covers
  text publication and encoding, with original causes retained.
- Cache read/write diagnostics are returned in existing per-item errors without
  erasing live scheduler observations or fetched log text. A genuine cache miss
  remains quiet. Invalid structure is distinct from inaccessible evidence.
- `asl submission` renders adopted local errors in text/JSON, supports `--debug`,
  and preserves receipt/ID fields when refresh fails. Broader process, submission
  orchestration and observation policies remain later MVP10 work.

## 0.2.0.dev2 — 2026-11-16

- Bundle loads, append reads and metadata updates reuse discovery's regular-file
  UTF-8 JSON reader. Missing, inaccessible and malformed files have distinct
  SelectionError diagnostics with safe causes and exact paths. This explicitly
  replaces direct loading's previous FileNotFoundError/OSError mix. Existing
  invalid job/dependency guards retain InvalidRequestError and bundle identity.
- Bundle/config writes retain RecordWriteError publication/durability/cleanup
  facts and add bundle, job or configuration context. Failed appends and metadata
  changes preserve existing evidence; malformed saved graphs are not rewritten.
- Config/filter/schedule/initialize/submit commands show adopted record errors
  once and preserve debug access to original causes. ACP retains adopted shared
  write diagnostics. Schedule still forwards application --debug; use its existing
  --autoslurm-debug for AutoSlurm failures.
- Bundle names must be file names without path separators/control characters.
  Metadata update inputs and resulting job/dependency structures are validated
  before publication. Record formats and historical roots remain unchanged.
- Receipt/cache/script persistence, external readiness and universal CLI/ACP
  adoption remain later MVP10 slices; no automatic repair, write replay or submit.

## 0.2.0.dev1 — 2026-11-16

Development checkpoint of the active refactor; not a final release.

- Add one version source, Python `autoslurm.__version__`, and `asl --version` /
  `autoslurm --version`. Build metadata comes from that same literal without Git.
- Record the already implemented refactor baseline: shared path resolution,
  submission receipts retaining accepted/uncertain outcomes, bounded inspection/
  logs, explicit single-checkout software updates, typed command authoring and
  staged diagnostics through MVP10.3c.1. See PLAN.md for exact completion/limits.
- Compatibility: current profiles use SSH aliases and software/results roots;
  Slurm account is optional. Software updates refresh editable installs without
  changing scientific dependencies. Known authoring/config/selection/write guards
  use the documented diagnostic exception families. Publication errors distinguish
  unknown versus observed effects; do not infer scheduler rejection from them.
- This baseline includes intentional pre-1.0 API changes. Saved history remains
  retained; record/protocol versions are independent of the package version.
- Existing `mvp0`–`mvp9` tags stay historical milestones. Earlier builds reported
  `0.1.0` across different revisions, so that value alone cannot identify them.
