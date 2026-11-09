# AutoSlurm installation register

## Status

**Local baseline verified, 2026-11-09.** The user installed AutoSlurm in base
Conda. Metadata and actual imports confirm an editable install from this
checkout. Separate stable/development installations do not yet exist. Cluster
inventory and operations are deferred by the user's local-only instruction.

## Lane inventory

| Field | Current local installation | Development workstation |
|---|---|---|
| Machine/profile identity | Local workstation; no machine configuration found at resolved config path | Not established |
| Checkout and source reference | `/Users/aadam/Projects/autoslurm`, main, HEAD `33bcbd34fb167fca67aa64739a013073c64167b1`; application source/tests unchanged from HEAD; planning/docs changes uncommitted | Separate checkout not established |
| Python environment | `/opt/homebrew/Caskroom/miniforge/base`; Python 3.14.7 | Separate development environment not established |
| Actual import location | `/Users/aadam/Projects/autoslurm/src/autoslurm/__init__.py`; package 0.1.0; editable install metadata points to this checkout | Disposable baseline environment reads the same source; this is not a development lane |
| Command entry points | `/opt/homebrew/Caskroom/miniforge/base/bin/asl` and `/opt/homebrew/Caskroom/miniforge/base/bin/autoslurm` | Not established |
| Helper revision and invocation | Not applicable locally; remote helper not inspected | Remote behavior will be mocked |
| Configuration and tracking root | `/Users/aadam/Projects/autoslurm`; resolved `config.json` absent | Temporary test roots only; supported persistent selector pending MVP0.2 |
| Script/log locations | Root-relative `jobs/`, `slurm/`, `out/`; no non-dot files at verification | Temporary test roots only |
| Application working/result roots | Not configured/verified; no application launched | Not established |
| Evidence source and verification time | Python executable/prefix, import metadata, actual module path and storage API; 2026-11-09 | Guarded local baseline run, 2026-11-09 |

Add cluster columns or rows when remote inventory is authorized. Every run
still targets one selected machine. Store nonsecret paths and identities only;
never credential contents. An environment path alone is not proof of its imports.

## Verification and release record

- **Baseline tests:** 195 unit tests and four mocked three-job submission cases
  passed. See [the baseline record](design/MVP0_safe_development.md#local-baseline-mvp01)
  for dependencies, guards, the missing accounting mock and limits.
- **Stable revision reference:** full HEAD SHA recorded above. The editable
  installation still follows this checkout; a separate retained stable checkout
  and environment pin have **not** been created. That is part of MVP0.2.
- **Local development isolation:** disposable test environment/storage verified;
  separate stable/development checkouts/environments not yet established.
- **Remote development isolation:** deferred; all current tests are local mocks.
- **Promotions or migrations during this refactor:** none performed.

When updating the inventory, record the command/report used, resolved locations,
revision and time; do not replace missing evidence with an assumed default.
Before promotion, add a dated record of candidate/previous revision, checks,
new-run routing, ownership of in-flight jobs and rollback destination. Retain
earlier records so old job ownership stays explainable.
