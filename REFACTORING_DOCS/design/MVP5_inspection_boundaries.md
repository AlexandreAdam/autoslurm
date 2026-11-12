# MVP5 Inspection responsibility boundaries

## Status

Complete locally, 2026-11-12, in main checkout on `dev`. Tests use the isolated wrapper
and mocked Slurm/transport. Task commit: `git log --grep '^MVP5.3:'`;
local tag `mvp5` closes the milestone. User authorized this MVP; no cluster
operations, package installation or migration are part of this work.

## Problems

`resolve_jobs` can query a scheduler and read configuration despite appearing to
transform observations. `inspect_bundles` loads records, overlays receipts,
queries, projects states, handles caches and reads artifacts in one function.
`read_job_logs` imports inspection helpers, combining reference selection,
transport, decoding and storage. A malformed ID poisons a machine-wide batch;
a valid-JSON malformed cache can crash inspection. Cached artifact errors may
leak into unrelated reads, and cache-write failure can discard fetched log text.

## Decisions (implementation scope; reviewable)

- **D1 Explicit collection.** `inspection_collection` owns local record/receipt
  loading, current profile reads and batched scheduler collection. Retain saved
  producing transport; unresolved/malformed remote metadata never becomes local.
  Isolate malformed IDs before batching healthy jobs.
- **D2 Pure projection.** `inspection_state` transforms provided jobs,
  observations and producing profiles into the existing task/job dictionaries.
  No reads, writes, clock or scheduler calls. Presentation wrappers explicitly
  request collection before using projection. Reuse array identity/state rules.
- **D3 Cache ownership.** `inspection_cache` owns observation and excerpt JSON
  paths/reads/writes. Treat malformed caches as unavailable evidence, preserve
  current observations when writes fail and report errors. Cache state separately
  from request-specific log/script attachment; retain compatible existing files.
- **D4 Artifact boundary.** `inspection_artifacts` owns selector validation and
  log/script attachment. `log_files` separates pure candidate selection from
  local reading, remote batching/decoding and excerpt cache use. Move shared
  producing-machine interpretation into execution rather than importing the
  inspection coordinator. Cached mode performs no remote calls.
- **D5 Bounded refactor.** `inspection` coordinates these stages and retains
  public inspect/list signatures, result fields, bounds and batching. No new
  domain framework or record version. Internal helpers can change; revise test
  patches to the actual side-effect adapter owners.

## Validation

Reproduce invalid-ID batch poisoning, malformed cache crashes and request-specific
artifact errors contaminating cached status. Prove projection/ref selection
require no file/process access and do not mutate inputs. Exercise malformed
producing transport, failed/partial queries, cached remote tails, malformed and
unwritable caches, bounded decoding and fetched-log retention on cache failure.
Retain full offline scientific/receipt/CLI/ACP coverage and verify daily runtime
and baseline rollback files remain untouched.

The baseline **333 tests** passed before changes. Four new regressions first
failed, demonstrating invalid-ID batch poisoning, malformed-cache crashes,
artifact errors leaking into cached status and malformed remote metadata querying
local Slurm. These now pass with the prior scientific/receipt/CLI/ACP workflows.

The final full offline suite passed **366 tests in 3.15 s**, with 39 expected
snapshot-collision warnings; report `.development/test-runs/mvp5-final.xml`.
The 33 added cases cover pure projection/reference selection without I/O or input
mutation, malformed producing metadata/profiles, cache schemas and write failures,
bounded/invalid remote payloads, cached no-network errors, task identity on shared
paths, legacy local profiles/sidecars, receipt identity changes, partial parent
state with absent tasks and source changes during record loading.

`inspect_bundles` coordinates 22 lines (previously 80), and `read_job_logs`
coordinates 24 (previously 114). The substantive boundary is that state projection
has required observation input and no external effects; cache and artifact failures
cannot replace live state or leak into unrelated requests. Shared producing-machine
interpretation is in execution; logs no longer depend on inspection orchestration.
Record loading checks its definition fingerprint across loading; changed files
become broken/unavailable evidence rather than being cached under the wrong hash.
No general transactional/concurrent-writer guarantee is claimed.

Public Python/CLI/ACP selectors, result fields, batching and existing observation/
excerpt file paths are retained. Decimal task selector strings from historical
context helpers remain supported. Invalid log bounds fail before queries/cache
writes. Fetched excerpts can include `cache_error`; the same error is exposed in
the run's errors while text/state remain available. Old artifact-bearing sidecars
are read with request-specific fields/errors removed. Daily and rollback runtime
roots remain unchanged; local base commands import the active code. No cluster
access, dependency changes, migration or push occurred.

## Open questions and forward constraints

Existing receipts/bundles remain dictionaries. No general concurrent-writer or
historical scheduler-incarnation guarantee. Mutable scientific source/inputs and
software releases remain separate concerns (MVP7). Persistence/transfer and
configuration/public-export cleanup remain MVP6. Do not infer scientific
validity or retry submission from observations or log text.

## Log

| Date | Event |
|---|---|
| 2026-11-12 | MVP5.0 bounded around explicit collection/projection/cache/artifact responsibilities |
| 2026-11-12 | MVP5.1 collection and pure state projection extracted; invalid IDs/producing metadata isolated |
| 2026-11-12 | MVP5.2 observation/excerpt cache and artifact boundaries extracted; log reference/read/transport/decode steps separated |
| 2026-11-12 | MVP5.3 366 offline tests passed; current guide/map updated; local `mvp5` checkpoint |
