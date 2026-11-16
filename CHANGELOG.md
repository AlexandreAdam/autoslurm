# Changelog

Package checkpoints use Python-compatible versions. See
[the versioning policy](docs/versioning.md) for bumps, tags and publication gates.
Entries describe observable behavior and compatibility; detailed task evidence
remains in [PLAN.md](PLAN.md). A checkpoint entry does not imply PyPI publication.

## Unreleased

Changes after the latest versioned checkpoint belong here until the next bump.

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
