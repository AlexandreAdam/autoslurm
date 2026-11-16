# Package identity and compatibility

Use `from autoslurm import __version__` or `asl --version` /
`autoslurm --version` for the running code version. These perform no Git, cluster
or environment preparation. AutoSlurm's refactor uses 0.2.0.devN checkpoints.
Do not assume a development checkpoint completes every planned MVP or promises
final API stability. Preserve exact bundle/receipt and producing-machine evidence.

Package versions identify tested code checkpoints. For an editable checkout,
record the Git commit and whether it is dirty too: source can move between
checkpoints. `importlib.metadata.version("autoslurm")` and `pip show` describe the
last installation and can lag the running source after a pull. The configured
editable reinstall refreshes metadata/entry points; it remains an explicit update,
outside submission and compute jobs. Do not silently repair an environment or
update a shared checkout referenced by existing jobs.

The maintainer version source is the literal in `src/autoslurm/version.py`.
Build metadata and runtime/CLI use it. Versioning does not need Git at build time;
source archives retain the version. A clean artifact install must have equal
runtime/distribution versions. Maintainers bump the current dev number and add a
dated CHANGELOG.md entry when completing a supported behavior change; docs/tests
alone can remain Unreleased. Annotated v-prefixed package tags are immutable;
historical mvp tags retain their original milestone meaning. Do not derive a
package version from an MVP number or branch name.

Before 1.0, minor versions may intentionally change APIs; read the changelog and
documented client contracts. Package version, record schema, diagnostic schema
and helper protocol are separate: check actual capabilities/record versions,
never infer compatibility from equal package versions. No automatic migration,
download, remote update or PyPI publication follows from a version/tag.

The repository's docs/versioning.md defines release gates. Public index release,
truthful Python support, metadata/license/name ownership and broader compatibility
checks remain explicit release preparation. For operational errors use installed
15_diagnostics and retain authoritative receipt/update evidence before presentation.
