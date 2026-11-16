# Versions and release checkpoints

AutoSlurm's running code reports its version with `asl --version`,
`autoslurm --version`, or `autoslurm.__version__` in Python. The current refactor
starts the `0.2.0` development line. A development version identifies a tested
checkpoint; it does not promise that every planned MVP is complete.

## One version source

Maintainers edit only `src/autoslurm/version.py::__version__`. Setuptools reads
that literal for wheel/source metadata, and the CLI/Python interface imports it.
Do not duplicate the version in pyproject.toml or derive it from a branch name.
Builds from source archives work without Git metadata. No command, Git discovery,
cluster access or package installation occurs just to obtain the running version.

An editable checkout can move while its installed distribution metadata stays
older. The running-code version follows the checkout; `pip show` and
`importlib.metadata.version("autoslurm")` describe the last installation. A normal
editable reinstall refreshes that metadata. Record the Git commit and whether the
checkout is dirty as well when working between checkpoints. The package version
does not identify uncommitted code. Fresh artifact installs must report matching
runtime and distribution versions; verify this before tagging a checkpoint.

## Choosing the next version

| Version | Meaning |
|---|---|
| `0.2.0.dev1`, `.dev2`, … | Reviewed development checkpoints of the current refactor |
| `0.2.0a1`, `b1`, `rc1` | Explicit alpha, beta or release-candidate testing when useful |
| `0.2.0` | Deliberately approved final release of that version line |
| `0.2.1` | Compatible bug fixes after `0.2.0` |
| `0.3.0` | New features or intentional breaking changes while pre-1.0 |

Before 1.0, minor releases may break compatibility; describe changed APIs, config
or record behavior and how retained history is handled. After 1.0, use a major
bump for breaking changes, minor for compatible features and patch for fixes.
Pre-release/dev suffixes follow the Python version specification, so packaging
tools order them correctly. A development suffix alone is not a compatibility
guarantee. Never use the package version as a helper-protocol capability or a
record-schema version; those contracts keep their own explicit identifiers.

For each completed task that changes supported package behavior, bump the next
development checkpoint and move its Unreleased notes into a dated version entry
in the same commit. Documentation/test-only work can stay under Unreleased until
the next checkpoint. Record task IDs in PLAN.md and behavior in CHANGELOG.md.
Commits between checkpoints remain identified by Git revision; local test rebuilds
are not new published releases.

## Tagging and publishing

1. Review compatibility notes and verify the expected next version and changelog.
2. Run the applicable offline tests. Build a wheel and source archive; build a
   wheel from the archive without `.git`. Check installed metadata, Python/CLI
   versions, package resources and the narrow fake-cluster workflow outside the
   repository. Keep artifacts/hashes in the installation register.
3. Commit the exact checkpoint. Add an annotated `v<VERSION>` Git tag to that
   tested commit, for example `v0.2.0.dev1`, then push the commit and that tag.
   Never move/reuse a checkpoint tag. Existing `mvp*` tags retain their original
   meaning and targets; they are not package versions.
4. Public index upload is a separate, explicitly authorized release action.
   Before PyPI, verify name ownership, license/metadata, truthful supported Python
   versions, installation/resource contents and upgrade/client-helper behavior.
   The current `requires-python` declaration still needs a supported-version audit;
   this checkpoint does not establish a broad compatibility matrix. TestPyPI can
   be a separate rehearsal. Do not recreate GitHub Actions to publish implicitly.
5. Publish the tested artifacts from the tag and retain their hashes. Never upload
   different code under an existing published version. Follow with a new version
   and changelog entry for corrections. Publication, deployment and cluster updates
   each remain explicit operations.

The [changelog](../CHANGELOG.md) tracks package checkpoints. The
[plan](../PLAN.md) tracks refactor tasks; completing an MVP does not by itself
make a final release. The [installation register](../REFACTORING_DOCS/installation-register.md)
records what was tested and which installation is in use.

The policy uses the [Python version specification](https://packaging.python.org/en/latest/specifications/version-specifiers/)
and setuptools' [single-source attribute configuration](https://setuptools.pypa.io/en/latest/userguide/pyproject_config.html#dynamic-metadata).
