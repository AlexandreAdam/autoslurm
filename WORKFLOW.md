# AutoSlurm MVP working agreement

Keep AutoSlurm usable for daily science while improving it through small,
independently tested releases. This agreement governs the refactor process;
[PLAN.md](PLAN.md) owns tasks/progress and
[the installation register](REFACTORING_DOCS/installation-register.md) records
which installations are actually in use.

## Scope of the first step

Establish these rules and agent entry guidance first. This does not establish
that installations are isolated, tests pass, or any release has been promoted.
Those require recorded evidence in the subsequent MVP0 tasks. Do not infer that
the current checkout is safe to edit for development just because it contains
the new planning files; an editable production install may import it directly.

**Current execution scope (2026-11-09): local only.** The user requested mocked
Slurm tests. Do not contact a cluster, discover remote installations, submit live
jobs or install remote helpers. Test remote behavior with fake commands. This
scope supersedes live-check suggestions elsewhere in the design documents until
the user authorizes cluster work. On 2026-11-12 the user explicitly activated
`dev` in the main folder for daily use through base Conda. Code changes now belong
in that main checkout. Keep tests in their separate state/environment and the
baseline rollback checkout untouched. No cluster installation was changed.

## Sources of truth

| Question | Read or update |
|---|---|
| What are we doing next and what is complete? | PLAN.md Status, active task, Decisions log and Done log |
| How do we work safely? | This agreement; AGENTS.md and CLAUDE.md point here |
| Why does the current MVP have this design? | Its document in REFACTORING_DOCS/design |
| Which code, helper and state belong to a real run? | Installation register and the run's saved submission evidence |
| How should an application agent operate the current version? | Installed agent guidance and that installation's public help/API |

The interaction map and full documentation designs are coverage references.
They do not advertise implemented capabilities or expand the current task.

## Release lanes

- **Active local development** is `/Users/aadam/Projects/autoslurm`, branch
  `dev`, imported by base Conda's existing editable installation. The user chose
  to use and evolve this code directly for local daily work.
- **Test execution** uses `.development/venv` and `.development/python`, importing
  the active main source while selecting `.development/state` and temporary
  test roots. Default tests reject unmocked cluster/network commands.
- **Rollback** retains baseline `33bcbd3` in `.development/stable`, with explicit
  source-selecting wrappers and its own default state. Remote installations
  remain uninspected/unchanged; they retain ownership of existing cluster jobs.
- Keep one Git repository. A second checkout is not a new project or a second
  independent codebase. Development may use main; production runs a pinned
  revision outside that moving checkout.
- The initial isolated development worktree `.development/checkout` remains at
  the tested MVP4 checkpoint on `codex/mvp0-isolation`; do not continue editing
  there. The main folder is now the active `dev` checkout. Older lane records
  below and in milestone designs describe history, not today's editing location.
- The local switch was authorized explicitly, after 333 offline tests and an
  isolated wheel smoke check. No local tracked jobs/config existed to migrate.
  Original working files were backed up and stashed; the two user-edited
  documents were restored unchanged. See the installation register for paths.
- Branch names, directory names and environment activation alone do not prove
  isolation. Verify import locations and resolved local/remote roots before
  development writes, package installs or cluster checks.
- Until isolation is verified, limit work to documentation and read-only
  discovery. Do not run scheduling/configuration commands or a test suite whose
  file/remote side effects have not been inspected.
- Never update a shared scientific application environment or checkout referenced
  by queued/running jobs. Test processes must not write daily records/outputs.
  Daily commands use the main root unless the operator explicitly selects another
  storage root; no records are implicitly copied between roots.
- Do not put private keys, tokens or credential contents in the register, plan,
  test fixtures or commits. Record locations and nonsecret identities only.

## One task at a time

1. Read PLAN.md Status, the task's completion criteria, the current MVP design
   and the installation register. Check the working tree for unrelated changes.
2. State the small outcome, affected interfaces, active lane and verification
   needed. If the task is too large, split it before coding.
3. Resolve only blocking contract decisions. Routine choices within the agreed
   task proceed without another approval round. Do not redesign future layers.
4. Make the smallest coherent change. Reuse working representations; centralize
   one shared rule rather than building a parallel engine. Separate mechanical
   moves from behavior changes.
5. Add meaningful focused checks, run the applicable test gate below, and
   update the affected agent recipe with the implemented behavior and limits.
6. Update the task, Status, Done log and design decisions together. Record the
   actual check results and any unresolved failure; unmet criteria stay open.
7. Commit task work with its ID and preserve unrelated changes. Push according
   to the implementation session's instructions. A code commit, push, merge or
   tag does not change the stable installation or count as deployment.

The initial planning/rules documents remained uncommitted during baseline
identification. Preserve unrelated working files during later commits and lane
changes; do not sweep user edits into a task commit to clean the working tree.

## Test and release gates

| Change or boundary | Minimum evidence |
|---|---|
| Documentation/rules | Read back the result; check relative links, task references and conflicting instructions |
| Small code change | Focused behavior regression and applicable fast tests in verified development isolation |
| Shared path/state/submission change | Relevant failure cases and full offline suite before promotion; record existing exceptions |
| Cluster behavior | Local mocked Slurm/transport checks, including failure cases; actual cluster validation deferred under current scope |
| Promotion | Tested candidate revision, narrow artifact-install smoke check, working agent recipe, current installation register and rollback destination |

Do not claim success from a command that was not run, or from a test skipped due
to unavailable prerequisites. Existing failures remain distinguishable from new
regressions. No full documentation site, database or migration framework is
required to complete a small reliability MVP.

## Keeping agents operational

- Development agents follow AGENTS.md and this agreement. Agents building or
  operating scientific applications use the supported guide for their selected
  installation. These are different contexts, even when the same agent does both.
- Before an operation with side effects, identify the installation/lane, machine,
  selected bundle/job and output scope. If those cannot be established, perform
  read-only discovery and request the specific missing fact before writing.
- Preserve exact selected bundle/version, target machine and returned scheduler
  IDs in the client experiment/handoff record. Do not rely on a remembered
  `latest` value or terminal row number after the session ends.
- Preserve known outcomes when a request partly fails. A lost connection may
  leave a remote helper running; no blind submit fallback or resubmission.
- Document only implemented operations and known limits. MVP0.2 implements an
  explicit root selector in development; the stable baseline does not have it.
  Development MVP2 adds incremental submission receipts and exact read-only
  refresh. Development MVP3 shares status/task/log evidence with explicit
  errors/staleness and bounded refresh. Automatic recovery remains planned. A passing
  mock helper check is not evidence about a real installation.
- Update the small integration/operate/diagnose recipe in the same task as a
  changed public behavior. Include the source of evidence, unknown state and a
  supported next step. Human examples use the same supported operations.

## Promotion and rollback

Promotion is a separate release action, performed when authorized by the task or
session. Do not repeat approval requests for actions already authorized. A
request to implement an MVP alone does not select a new daily-use installation.

Before promotion, record candidate and previous stable revision, environment,
helper and roots; checks and limitations; who manages in-flight runs; the
new-run entry point; and the rollback destination. Change new-run routing
explicitly. Existing jobs remain managed by their original installation.

After a failed promotion, identify every candidate submission before launching
replacement work. Returning to old code does not undo scheduler effects or make
new records readable by an old version. Keep both lanes' records available.
Do not migrate, merge or overwrite live state implicitly during promotion or
rollback. Breaking interfaces/formats are documented at the release boundary;
historical compatibility is added only when needed.

## Session handoff

Leave PLAN.md Status and Done log sufficient for the next development session.
For operational work, retain the exact installation/lane, machine, saved bundle
reference, job/task IDs, actions taken, latest evidence/time, unresolved outcomes
and next supported action. Exclude secrets and unbounded log dumps.

If work is blocked, name the missing evidence and what can still proceed. Never
mark an entire MVP complete because its documentation or a subset of checks is
finished.
