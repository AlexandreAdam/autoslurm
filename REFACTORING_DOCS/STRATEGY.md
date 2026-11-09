# AutoSlurm MVP strategy

Improve the working implementation through small usable releases. [PLAN.md](../PLAN.md)
owns the active order and boundaries; the earlier broad architecture remains a
longer-term direction rather than a first-release prerequisite.

## Priorities

1. Protect daily jobs with a pinned stable installation and isolated development.
2. Centralize existing machine, relative-path and bundle-selection rules.
3. Stop unsafe retries and preserve known accepted jobs on partial failure.
4. Share one task/status/log view between agents and terminal commands.
5. Add scientific conveniences and complete packaging/documentation later.

A single source of truth is one active policy implementation. Use small shared
helpers and the current bundle shapes first. Do not begin with a database,
complete schema migration, broad module move or generic execution framework.

## Incremental method

Use the interaction map as a coverage checklist. Settle only the contracts needed
by the current MVP; add focused regressions and the matching small agent recipe.
A full product specification or documentation site does not block early fixes.
Keep mechanical extraction separate from logic changes and preserve existing
useful tests. Prefer completing a narrow working path over migrating every
entry point at once, but do not leave contradictory policy copies active in the
path being released.

Every promoted release needs a useful demonstrated outcome, a stated limitation,
and a rollback path. Measure repeated external commands on exercised workflows;
reduce duplicate queries/discovery before adding caches or promising speedups.
Do not confuse shorter code or more modules with a more reliable product.

## Daily use and breaking changes

Stable code/environments/roots continue owning their jobs. Development uses
separate workstation and cluster code, helper, config, tracking and test outputs.
Main can continue evolving in development without changing a pinned production
installation. Promote tested revisions for new work, retain the previous lane
for old work, and never mutate a queued job's referenced environment.

Breaking changes are allowed at release boundaries. Keep production data intact;
provide an explicit later import path where needed, rather than preserving every
private API and intermediate format. Git history and the retained stable install
are the default legacy reference; avoid maintaining two active engines.

## Safety scope

MVP2 records known/partial outcomes and stops on uncertainty. It does not promise
automatic scheduler adoption, DAG resume or exactly-once execution. Those need
more design and remain L1 work. Scientific retries/reducer compatibility are L2.
Compute jobs use prepared environments without Git/network installation work.

Relative application paths have explicit bases. AutoSlurm owns selected-machine
roots and working-directory context; resolving a path does not transfer its
inputs. Every run uses one machine. Automatic deployment and multi-machine
routing stay outside scope.

## Documentation and release scope

Accurate integration and operate/diagnose recipes ship with each MVP; a short
human map and example ship with trustworthy inspection. Keep development
installation usable and use a narrow built-artifact smoke check before promotion.
Complete published human docs, installed agent-resource coverage, full provenance,
broad compatibility matrices and public package release are later layers.
