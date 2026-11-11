# AutoSlurm installation register

## Status

**Local isolation and client contract verified, 2026-11-11.** Base Conda retains the original source
at detached baseline HEAD. A separate development checkout, environment and
state root are operational. Cluster inventory and operations remain deferred
by the user's local-only instruction. No release has been promoted.

## Lane inventory

| Field | Stable workstation | Development workstation |
|---|---|---|
| Machine/profile identity | Local workstation; no machine configuration found at resolved config path | Not established |
| Checkout and source reference | `/Users/aadam/Projects/autoslurm`, detached HEAD `33bcbd34fb167fca67aa64739a013073c64167b1`; application source/tests unchanged; documentation working copies retained | `/Users/aadam/Projects/autoslurm/.development/checkout`, branch `codex/mvp0-isolation`; latest task commit located with `git log --grep '^MVP0.3:'`; local milestone tag `mvp0` |
| Python environment | `/opt/homebrew/Caskroom/miniforge/base`; Python 3.14.7, unchanged | `/Users/aadam/Projects/autoslurm/.development/venv`; Python 3.14.7; installed offline from local cache |
| Actual import location | `/Users/aadam/Projects/autoslurm/src/autoslurm/__init__.py`; package 0.1.0; editable install points to stable source | `/Users/aadam/Projects/autoslurm/.development/checkout/src/autoslurm/__init__.py`; separate editable install, version 0.1.0; use path/branch to distinguish these unreleased installs |
| Command entry points | `/opt/homebrew/Caskroom/miniforge/base/bin/asl` and `/opt/homebrew/Caskroom/miniforge/base/bin/autoslurm` | `/Users/aadam/Projects/autoslurm/.development/asl` and `.development/python` wrappers; actual executables under `.development/venv/bin/` |
| Helper revision and invocation | Not applicable locally; remote helper not inspected | Remote behavior will be mocked |
| Configuration and tracking root | `/Users/aadam/Projects/autoslurm`; resolved `config.json` absent | `/Users/aadam/Projects/autoslurm/.development/state`, selected by both wrappers through `AUTOSLURM_STORAGE_ROOT`; no machine config created |
| Script/log locations | Root-relative `jobs/`, `slurm/`, `out/`; no non-dot files at verification | Under selected state root for manual development; tests use fresh roots under `.development/test-runs/` |
| Application working/result roots | Not configured/verified; no application launched | Installed `science-demo` 0.0.1; mocked reference runs use temporary application/state roots. Direct installed-client check under `.development/test-runs/mvp03-installed-client/`; no persistent machine profile created |
| Evidence source and verification time | Executable/prefix, metadata/import, storage API, detached HEAD and no source diff; 2026-11-11 | Import/storage identity, editable metadata, 245 full offline tests and installed reference-client check; 2026-11-11 |

Add cluster columns or rows when remote inventory is authorized. Every run
still targets one selected machine. Store nonsecret paths and identities only;
never credential contents. An environment path alone is not proof of its imports.

## Verification and release record

- **Baseline tests:** 195 unit tests and four mocked three-job submission cases
  passed. See [the baseline record](design/MVP0_safe_development.md#local-baseline-mvp01)
  for dependencies, guards, the missing accounting mock and limits.
- **Stable revision pin:** original checkout detached at the full baseline SHA.
  Base Conda is unchanged; development has its own environment. Do not edit
  stable source, advance its checkout, or upgrade its environment as part of
  ordinary development. This is operational separation, not a filesystem lock.
- **Local development isolation:** verified. Source, environment and state have
  distinct locations; the stable default root and empty runtime directories are
  unchanged. The nested `.development/` directory is ignored by the stable tree.
- **Development validation:** 238 tests passed in 1.21 s, including fresh-process
  storage/config discovery, generated paths with spaces, mocked submission/
  transfers/sync/results, mismatched/old helper failures, helper payload-root
  rejection, configuration-editor retention, and the actual helper module entry point with a local fake Slurm executable. The missing `sacct` mock is fixed;
  default test fixtures reject unmocked process/network access.
- **Remote development isolation:** deferred; all current tests are local mocks.
- **Promotions or migrations during this refactor:** none performed.
- **MVP0.3 validation:** 245 full offline tests passed; 13 focused client/context
  tests passed after final updates. Exact selected definitions survive competing
  drafts; client validation covers missing input, incomplete and incompatible
  shards. The installed standalone client produces matching single and reduced
  summaries. See [the client recipe](../agent/01_client_workflow.md) and
  [reference application](../examples/reference_client/README.md).

## Current local commands

The following wrappers select the development interpreter and state for the
child process without activating or modifying base Conda:

```sh
/Users/aadam/Projects/autoslurm/.development/asl --help
/Users/aadam/Projects/autoslurm/.development/python -m pytest -q /Users/aadam/Projects/autoslurm/.development/checkout/tests
```

For edits, work in `.development/checkout`, not the original source directory.
The wrappers/environment/state are local setup files, not versioned application
configuration. A fresh setup recreates the separate environment, installs that
checkout, and exports `AUTOSLURM_STORAGE_ROOT` to its own absolute state root.
No remote profile/helper exists for this refactor. Do not copy stable configuration
or output roots into development without reviewing their destinations.

When updating the inventory, record the command/report used, resolved locations,
revision and time; do not replace missing evidence with an assumed default.
Before promotion, add a dated record of candidate/previous revision, checks,
new-run routing, ownership of in-flight jobs and rollback destination. Retain
earlier records so old job ownership stays explainable.
