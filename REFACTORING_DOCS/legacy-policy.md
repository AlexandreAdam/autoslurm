# Legacy Policy

This document defines how old AutoSlurm implementations should be preserved
during the refactor.

The [MVP plan](../PLAN.md) supersedes the earlier assumption of preserving every
public interface throughout development. Intentional breaking changes are
allowed at explicit promotion boundaries. Initially daily-use code was pinned
while a separate development lane changed. On 2026-11-12 the user activated `dev`
in the main folder for daily base Conda use; the old baseline is now a separate
rollback checkout. See the installation register for current source/state routing.
Existing remote runs remain owned by their unchanged submitting installations.

## Purpose

Legacy code remains useful while the new architecture is being built:

- as reference material
- as a compatibility fallback during migration
- as context for tests and behavior comparisons

## Rules

- Pin the working implementation and its environment before replacing it.
- Git history plus the retained stable installation are the default reference;
  a separate legacy module is useful only when a concrete comparison/import
  requirement needs it. Do not duplicate the entire old package by default.
- Replace one active policy path at a time. Reuse existing loaders/helpers
  during incremental extraction; avoid a second active implementation of the
  same resolver, selection rule or task-state mapping.
- Keep legacy code readable and minimally modified.
- Prefer deprecation over silent removal.
- Record a breaking public change and its new-run/data boundary explicitly.
  No compatibility promise for private helper names or every intermediate format.
- Old live jobs and tracking records remain with their submitting installation.
  Development cannot write production records. Review retained compatibility
  code at each promotion so it does not become an indefinite second engine.

## When to Move Code to Legacy

Move code to legacy status when:

- a new implementation is the active path
- tests cover the new behavior
- the old path is no longer needed for normal operation
- retaining executable old code has a concrete use beyond the stable snapshot

## What Should Stay in Legacy

- previous status-resolution logic
- previous log-resolution logic
- old array-task mapping helpers
- deprecated CLI glue that is no longer the primary implementation

## What Should Not Happen

- no destructive overwrites of historical behavior
- no hidden deletion of old assumptions or production records
- no mixing of legacy and active implementations in the same public path

## Notes for the Transition

Legacy code should be treated as a temporary compatibility layer, not as a
second active architecture.
