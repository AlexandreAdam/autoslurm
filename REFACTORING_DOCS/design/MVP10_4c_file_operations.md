# MVP10.4c transfer and filesystem diagnostics

## Status

Complete locally on dev in 0.2.0.dev10 after explicit continuation, 2026-11-17. Existing
Python transfer/path APIs and sync remain the interaction boundary. No live
cluster, daily configuration/state, environment repair or scientific-data copy.

## Implementation contract

Keep path resolution in ExecutionContext and transport addressing in transport.
Use one stdlib metadata probe locally and via the existing python3-over-SSH pattern
remotely, without importing AutoSlurm remotely or reading file contents. Follow
symlinks, preserving the existing exists meaning: ENOENT/ENOTDIR means absent;
permission/I/O/symlink-loop failures mean unavailable. A non-directory cannot be
silently skipped as a missing sync source. Validate bounded, versioned response
shape and expected path; malformed output, launch/timeout/SSH failures raise,
never False. Remote python3 is required; no shell-test fallback. Public path_exists
still returns bool on successful observation, with original producing transport
and logical/resolved paths retained. No extra root discovery for saved runs.

Required-input/data-root/working-directory preflight adopts the same metadata owner,
retaining a deduplicated batch in one remote command (zero when no checks). Missing
required paths use DiagnosticError/resource_missing instead of FileNotFoundError;
failed transport/unavailable metadata is distinct. Keep known logical/resolved paths
and labels; preview/submit add the exact bundle reference. Batch count/order/path
identity is validated under the same response bound, before staging or any claim.

One small file-command adapter owns expected process outcomes for probes, mkdir,
SCP and rsync. Pure diagnostic wording stays in errors.py. Preserve native causes,
safe errno/exit facts, source/target/machine and independent operation effects;
omit raw command output/config/keys. Probe/mkdir timeout 30 seconds; copy timeout
300 seconds. A local launch failure proves no command start; any interrupted or
failed started copy may have changed the destination. No per-file success is
invented for a failed batch. Validate managed filenames and local regular sources
before remote mutation. Direct transfer API remains None on success, batch SCP
stays one call and empty batches stay no-op. No rollback/removal/retry after failure.

Sync retains jobs/slurm/out and checksum versus ignore-existing policies. Its
existing print/None interface stays; on failure retain the failing diagnostic plus
which earlier subtrees completed, distinguish current copy unknown from later
not-started, and never print final success. Directory preparation happens only
after a positive source observation. Sync CLI renders adopted diagnostics once,
with --debug exposing native chains. Receipt-aware submit handling remains the
existing SubmissionError boundary; staging failure must stop before dispatch and
retain diagnostic/receipt. No generalized recovery or observation overhaul.

No saved format/helper capability/version migration. New diagnostic operation and
effect names are additive. Full API/ACP parity remains later MVP10 tasks. Tests:
native failures, malformed responses, permissions versus missing, partial copy,
no retries or sbatch, saved contexts, CLI/debug, no-Git build and installed smoke.

## Decisions

Dedicated diagnostic ownership and meaningful API adoption are user requirements.
Metadata probe/command bounds and module extraction are implementation choices,
not accepted broader architecture proposals. Parent 10.4 remains open until d.

## Checks and closure

99 new cases cover local/remote metadata agreement, files/directories/symlinks/
ENOTDIR, denied/I/O/loop failures, exact path/shape/duplicate/deep/oversized/invalid
UTF-8 protocol, quoted literal paths and no content reads. The process-fault matrix
covers probe/mkdir/SCP/rsync native launch/permission/I/O/timeout/encoding and SSH/
command/signal/malformed exit outcomes, with no retry. Source preflight, local
target preparation, wrong-kind/missing sources, unchanged unexpected bugs/native
interrupts, success-with-unusable-output effects, partial retention, completed
subtrees and pre-dispatch SubmissionError receipt behavior are verified. Existing
mock expectations now produce real metadata responses and existing source files;
no source checks are bypassed. Saved roots/aliases and copy policies still pass. Required-path batch tests cover
missing/denied/wrong-kind, omitted/extra/reordered entries, exact version/shape and
transport failures; public preview/submit stop before staging with bundle identity.

1583 full offline tests passed in 13.92 s, 72 expected collision warnings;
`.development/test-runs/file-operations.xml`. AST coverage remains 266 routes/
138 owners/23 broad catches, with no new broad handler or public route. New
operation/stage/effect names are additive to diagnostic version1; no saved format,
receipt/helper capability or historical migration change. Universal receipt/ACP/
observation adoption remains later tasks.

No-Git/no-runtime-import metadata, direct wheel/sdist-to-wheel rebuild and disposable
installed version/CLI/session/receipt/local-remote paths/absence/SSH failure/copy
effects/partial retention/sync/debug/packaged guidance checks pass for 0.2.0.dev10.
Direct/rebuilt wheel member contents match; hashes are in the installation register.
Base imports this checkout at dev10; editable metadata stays 0.1.0 without reinstall.
Pinned rollback remains clean at 33bcbd3. No actual cluster, daily config/state,
dependency install, scientific-result retrieval, external client or history edits.
Unrelated user documents/reports/software_preparations are excluded. Next: 10.4d
software-status observations; parent 10.4 stays open.
