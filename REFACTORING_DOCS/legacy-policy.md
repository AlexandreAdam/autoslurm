# Legacy Policy

This document defines how old AutoSlurm implementations should be preserved
during the refactor.

## Purpose

Legacy code remains useful while the new architecture is being built:

- as reference material
- as a compatibility fallback during migration
- as context for tests and behavior comparisons

## Rules

- Do not delete an old implementation immediately after replacing it.
- Move replaced implementations into a clearly labeled legacy location.
- Keep legacy modules out of the active code path unless explicitly required.
- Keep legacy code readable and minimally modified.
- Prefer deprecation over silent removal.

## When to Move Code to Legacy

Move code to legacy status when:

- a new implementation is the active path
- tests cover the new behavior
- the old path is no longer needed for normal operation

## What Should Stay in Legacy

- previous status-resolution logic
- previous log-resolution logic
- old array-task mapping helpers
- deprecated CLI glue that is no longer the primary implementation

## What Should Not Happen

- no destructive overwrites of historical behavior
- no hidden deletion of old assumptions
- no mixing of legacy and active implementations in the same public path

## Notes for the Transition

Legacy code should be treated as a temporary compatibility layer, not as a
second active architecture.

