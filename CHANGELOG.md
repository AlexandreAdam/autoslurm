# Changelog

Package checkpoints use Python-compatible versions. See
[the versioning policy](docs/versioning.md) for bumps, tags and publication gates.
Entries describe observable behavior and compatibility; detailed task evidence
remains in [PLAN.md](PLAN.md). A checkpoint entry does not imply PyPI publication.

## Unreleased

Changes after the latest versioned checkpoint belong here until the next bump.

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
