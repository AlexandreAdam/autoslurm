# AutoSlurm Refactoring Docs

This folder is the working documentation track for the AutoSlurm refactor.
It is separate from the existing user-facing docs and records the planned
architecture shift before implementation begins.

The goals of this track are:

- define the refactor direction before code changes land
- keep the current behavior inventory explicit
- centralize assumptions so later implementation work is modular
- document what should become legacy without deleting useful context

## Documents

- [Roadmap](roadmap.md): phased refactoring plan and sequencing
- [Current Architecture Flow](current-architecture-flow.md): diagram of the current command and data flow
- [Current State](current-state.md): inventory of the current interface and behavior
- [Function Map](function-map.md): flat inventory of package functions and entrypoints
- [Legacy Maps](legacy_maps/README.md): command-by-command dependency charts for the current implementation
- [Target Architecture](target-architecture.md): proposed internal model and data flow
- [Legacy Policy](legacy-policy.md): rules for preserving old code during migration

## Working Rule

The documents in this folder describe the intended future state and the migration
path toward it. They should be updated as the implementation evolves, but they
should remain distinct from the existing production documentation until the new
design is stable.
