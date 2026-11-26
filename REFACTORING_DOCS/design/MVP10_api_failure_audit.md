# MVP10.1 Public interface and failure audit

Audited 2026-11-13 against `61043722c4758cb188994f996e7e46ef8140003d`
on `dev`. This is the completed source inventory for
[MVP10](MVP10_actionable_errors.md), not an implemented error API. Runtime
behavior, saved formats and daily configuration remain unchanged. Diagnostic
field names, exception inheritance and exit conventions below are recommendations
to settle in MVP10.2, not accepted technical decisions.

## How to use the register

[MVP10_api_inventory.json](MVP10_api_inventory.json) is the exhaustive route and
owner register. Each route resolves to one canonical owner. Each owner records
inputs, current exception/result shape and effects, and inherits the failure
families, translation owner, desired diagnostic, next safe action, implementation
task and regression sources from its named contract. `route_notes` refine ACP
actions and routes whose semantics need separate explanation. These are explicit
references, not additional implementations of each alias.

At the original audit, all diagnostic adoption was pending. MVP10.2, MVP10.3a and
MVP10.3b.1–3 and MVP10.3c.1 amendments below record foundation, configuration,
authoring, selection, pure paths/render and shared publication adoption. Other regression
anchors prove only their current tested behavior, not the proposed contract.
Use the owner row plus its contract and any route note when closing a later task.
An owner may need several regressions and more than one implementation slice.

The read-only AST checker discovers exports, methods, dispatchers, package scripts,
ACP metadata/dispatch and broad catches without importing AutoSlurm, a science
application, or any CLI. Run from the main checkout:

```sh
.development/python REFACTORING_DOCS/design/check_mvp10_inventory.py
```

`--discover` prints source identities for review. It does not update or approve
the register. A changed route/catch must be reviewed, rather than automatically
accepted into the inventory. The checker verifies surface coverage and referenced
test-file existence; it does not establish diagnostic correctness, test-case
coverage, or unchanged function bodies. This is a development audit utility,
requiring Python 3.11+; it is not a public package API or runtime dependency.

## Coverage boundary

| Surface | Recorded routes | Coverage policy |
|---|---:|---|
| Python names | 176 | Root and every module's explicit `__all__`, plus documented context/sync and three `logs` compatibility names |
| Public instance methods | 9 | CommandOption, CommandContract and ExecutionContext; constructors are covered by class rows |
| Root CLI actions | 15 | Every ACTION_HANDLERS entry |
| Root aliases | 6 | Resolve to the same owner as their canonical action |
| Software CLI subactions | 2 | Separate status/update semantics, same dispatcher |
| Installed console names | 16 | Every project.scripts entry, including both root names |
| Executable helper module | 1 | `python -m autoslurm.apps.bulk_submit_driver`, including capabilities and execution |
| ACP actions | 8 | Metadata and actual dispatch must agree |
| **Total** | **233** | **112 distinct owners**, including constants and data/exception constructors |

The register includes all compatibility reexports through `configuration`,
`utils` and `save_load_jobs`. The historical standalone experiment-context module
reexports `apps.inspect.main`, so it shares the current inspect handler too.
`legacy_submit_driver.__all__` is empty: its retired names are not new public APIs.
Private adapters/probes are reviewed as implementation boundaries below, not
promoted to supported imports merely because their names lack an underscore.
Arbitrary imported names and executing modules without a main guard are excluded.
The in-repository reference client is an integration consumer; an external Gaia
client change is a separate authorized repository task.

The fifteen CLI action owners are config, schedule, submit, submission, cancel,
clean, filter, sync, initialize, status, software, scan, inspect, logs and agent.
Config includes view/summary, explicit setting/default writes and interactive
editing/optional validation. Software includes status and update. Status/inspect/
logs include selection, cached/fresh observations and text/JSON modes. Cancel and
clean include preview and explicit execution. These modes inherit the appropriate
effect boundary, even when they are flags rather than parser subcommands.

`scan` currently only scans a repository and saves its catalog. Old help strings
mentioning `asl apps scan` or listing a catalog do not create those CLI actions.
Empty `sync` starts a default-machine sync; it is not a help-only invocation.

## Findings that drive the implementation

These are source findings, not fixes delivered by MVP10.1. Priority expresses
implementation order within the planned slices, not evidence that an incident
has occurred beyond the user's stale-venv report.

| ID | Boundary and current behavior | Required regression and destination |
|---|---|---|
| E01 | `software_update_probe.update_checkout` assigns installation.python only after `_environment_python` succeeds. Missing/nonexecutable Python reaches a broad OS/timeout/interrupt branch with a generic preflight message, losing attempted executable and cause. | Preserve configured executable, setting, errno and machine; prove pull/install never start. MVP10.4, stale-venv regression. |
| E02 | `software_update.update_software` collapses remote launch, timeout, invalid response and interruption into unknown transport evidence without the original cause. A failure to launch SSH is earlier than a lost response after launch. | Separate before-launch failure from possibly executed update; retain chained cause and observed commit/install facts. MVP10.4. |
| E03 | `remote_fs.path_exists` returns False for every nonzero test/SSH result. `ExecutionContext.validate_resolved_jobs` labels any remote nonzero as FileNotFoundError. | Test actual absence versus SSH255, command failure and permission uncertainty. Never report unavailable access as missing data. Explicit API release note required. MVP10.3/4/6. |
| E04 | Direct `run_slurm_locally` ignores sbatch returncode/stderr and parses stdout. Direct local/remote submit helpers and callback orchestrator have no owned receipt. | Rejection detail versus malformed/lost accepted-ID response; preserve prior accepted IDs/unknown effects. Decide and document the lower-level supported contract rather than quietly giving it high-level receipt guarantees. MVP10.5/8. |
| E05 | Driver/coordinator/refresh broad catches protect receipts and accepted IDs, but nested persistence/cleanup failure can obscure the initiating failure. Driver errors without a receipt propagate without partial-result ownership. | Failure injection before dispatch, after acceptance and during tracking, including KeyboardInterrupt; preserve primary plus secondary evidence and no replay. MVP10.5. |
| E06 | `record_files.atomic_json` can fail after publication during directory fsync or temporary cleanup. `create_slurm_script` opens/truncates before rendering; dependency patching writes directly. | Distinguish not-published from already-published/partial files; cleanup failure must not mask original error. No automatic repeat append. MVP10.3/5. |
| E07 | `list_submissions` loads all receipts before filtering; one broken/unreadable unrelated receipt aborts discovery. Some fields used for sorting are not fully validated. | Mixed valid/corrupt batch retains healthy identities with per-record diagnostics; define listing result boundary explicitly. MVP10.5/8. |
| E08 | `list_saved_bundles` replaces unreadable/corrupt payload with jobs=[]; snapshot analysis returns broken without cause; filter loading catches any Exception and chooses active. | Empty, missing, corrupt, denied and unknown differ. Keep filename-only selection and show per-entry failures. MVP10.3. |
| E09 | Interactive config catches EnvironmentError during load and enters fresh-default creation, including an unreadable existing file. JSON/normalization failures take different paths. | Denied/invalid existing config cannot silently become an invitation to overwrite evidence. Preserve existing editor authorization rules; show exact file/cause. MVP10.3. |
| E10 | Remote helper/root/software/log/scheduler adapters use different timeouts, response checks and string errors. Some include raw unbounded output; others discard useful safe stderr. | Bounded/redacted detail, executable/alias/stage and return code; malformed response is not a scheduler/job result. No authentication guessing. MVP10.4/6. |
| E11 | Inspection already retains broken/partial/stale/error evidence and good data. Remote scheduler/log broad catches also flatten unexpected bugs into observation strings; cache failures are separate but inconsistent. | Preserve good evidence, timestamps, missing/empty/not_cached distinctions and bounds; unexpected bugs stay debuggable. Do not turn failed science into failed inspection. MVP10.6. |
| E12 | Cancel prints Cancelled after scancel accepts requests; a later target failure loses the per-target success summary. FIX.CANCEL.1 now retains saved producing transport, uses shared local/remote routing and resolves targets before dispatch; legacy definitions use explicit current profiles. | Request acceptance versus terminal observation; mixed accepted/rejected/unknown targets; changed-profile regression is covered by FIX.CANCEL.1; full per-target diagnostics remain open. MVP10.7. |
| E13 | Clean broadly skips failed bundle loads; status reads can occur even in preview. A later unlink failure follows earlier deletion without structured per-file effects. | Retain unreadable/submitted evidence, report skipped/retained/deleted/failed separately, reject changed selection safely. Preview means no deletion, not no queries. MVP10.7. |
| E14 | Sync can copy earlier directories before a later transfer fails; scp/rsync staging can leave partial files. The API returns no partial-copy result. | Per-target effects and exact destinations; absent source directory differs from failed SSH test (already separated by the pull adapter). MVP10.4/7. |
| E15 | Root/standalone CLI catches differ: some emit SystemExit strings, some tracebacks, some error JSON. Status/inspect partial observations usually exit0; logs exits1 for error entries; software concerns and failed requests both exit1. | Deliberate operation-versus-observation exit policy, consistent expected diagnostics, retained JSON evidence and debug path. No retroactive assumption that every non-success science state should exit1. MVP10.8. |
| E16 | ACP general catch returns only error/message, hides unexpected bugs and most structured causes; malformed nonmapping request can fail before catch. Metadata loading silently yields {} on any exception. | Equivalent domain diagnostic/result/receipt across eight actions; malformed envelope distinct; unavailable metadata visible; unknown task does not masquerade as a matched recipe. MVP10.7/8. |
| E17 | Scan treats corrupt/denied catalog as empty, then writes a new catalog directly. Context can return empty text when sections/resources are unavailable. Inspect may print successfully then fail copying to clipboard. | Preserve valid discovery data and distinguish no match/unavailable; presentation failure is secondary and cannot imply an operation should be replayed. MVP10.7/8. |
| E18 | Raw schedule CLI runs the application --help, guesses arguments and saves before optional submission. Typed authoring validates static declarations without execution. | Explain application-help launch/parse and save-versus-submit stages accurately; retain saved path on later failure. No new automatic app imports or replacement argument engine. MVP10.3/8. |

## Strategic translation and effect contracts

Recommended common dimensions are operation/stage, code/category/summary,
selected machine/project/bundle/job/task/setting, logical and resolved path or
attempted executable, safe cause/returncode, known/unknown effects, evidence
reference, next safe action and secondary errors. Exact names remain MVP10.2 work.
Category alone cannot determine effects or whether retrying is safe.

| Boundary | Outcome policy to preserve or establish | What the shared error module must not do |
|---|---|---|
| Pure config/command/argument/path/graph validation | Raise a known diagnostic before operation effects; include the named field and expected constraint. Bad constructor shape can remain normal Python call-signature TypeError. | Read config, inspect machines, import a command or supply an alternative environment. |
| Local read/selection | Missing exact record differs from corrupt, denied and broken per-item evidence. Empty discovery is a normal observation. | Silently select another snapshot/root or overwrite historical records. |
| Publication | Report attempted path and whether publication is known not to have happened, known published, or uncertain. | Treat a post-rename/fsync failure as safe-to-repeat append. |
| Process launch and read-only probes | Keep launch failure distinct from nonzero response, timeout, malformed protocol and unavailable observation. A path's existence may be unknown. | Diagnose SSH password/2FA/key problems without evidence or handle credentials. |
| Software preflight/update/install | Preflight failure has no pull/install; after pull/install starts preserve observed before/after commit and environment state, including partial/unknown. | Say nothing changed after a pip failure, or auto-reset, clone, repair dependencies or retry. |
| Submission | Keep SubmissionError.receipt, exact selected identity, accepted IDs, blocked/unattempted/uncertain jobs, original cause and secondary tracking failure. | Retry or reclassify unknown acceptance as scheduler rejection. |
| Inspection/status/log/cache | Return healthy per-item evidence alongside unavailable/stale/failed observations; distinguish absent/empty/not_cached. Invalid operation requests still raise. | Infer a failed job from failed observation, erase good logs or retrieve science datasets. |
| Cancel/clean/sync | Accumulate per-target effects before reporting a later failure. scancel acceptance is a request, not terminal cancellation. | Retry destructive work or infer safe cleanup from unavailable state. |
| Terminal/ACP | Translate once at the outer presentation boundary; retain structured evidence and debug-visible unexpected causes. Helper protocol remains separate. | Rebuild domain messages independently or flatten partial success into a generic failure string. |

No blanket decorator around all functions is proposed. The module should be
dependency-light and contain diagnostic data/constructors/serialization; adapters
collect facts where known. Presentation belongs in a thin separate adapter.
Existing exception payloads remain readable; additive diagnostics are preferred.
If an API must change, especially path_exists or discovery results, document the
release boundary and old-record interpretation before changing callers.

## Catch-site review

The JSON register contains **all 18 broad handlers in 13 scopes**, in source order
within each scope, with an individual review for each. There are no blanket
instructions to remove them. Three families require different treatment:

- **Retain evidence protection:** coordinator dispatch/publication, driver
  sbatch/persistence, refresh secondary tracking failure and owned-session cleanup.
  Keep accepted IDs and original cause even for unexpected exceptions/interrupts;
  give cleanup/tracking failure a secondary place.
- **Keep observation behavior, narrow expected causes:** scheduler and bounded
  log query adapters must still return unavailable observations when external
  reads fail. Unexpected implementation failures need a debug path.
- **Stop silent defaulting or generic flattening:** filter config, clean skips,
  action metadata, submit snapshot classification and ACP general envelope.
  Default only explicitly optional absent data; expose corruption/access failures.

Narrow handlers also matter. Reviewed examples include the advisory ssh -G probe
(fallback to an owned short socket is intentional, not resubmission), config load
EnvironmentError fallback, software probe OSError/timeout/interrupt flattening,
software status exception asymmetry, invalid bundle JSON reclassified as OSError,
log missing/unreadable/nonregular states, missing versus corrupt cache, unavailable
Git metadata as expectation warnings, snapshot timestamp fallback, exclusive-save
collision retry, and source-summary parse skips. These policies are assigned in
owner rows/findings; optional-data fallback must not be generalized to action
recovery. No new user prompt, retry or global exception hook is authorized here.

## Regression and delivery plan

Existing suites are listed per contract in the register. Add failure injection
against each affected public boundary rather than testing message strings alone:
assert identity/cause, text/structured equivalence, bounded safe output, retained
known effects, unknown states, next action and forbidden command absence. Specific
new cases E01–E18 remain open until their implementation tasks run them.

Concrete starting evidence, with the remaining gap kept explicit:

| Existing test | What it establishes today | Still required |
|---|---|---|
| `test_wrong_or_unavailable_environment_is_rejected_before_pulling` in test_software_update | Missing/wrong interpreter stops before pull | Attempted executable, errno and setting in the shared diagnosis (E01) |
| `test_lost_or_invalid_remote_response_is_unknown_without_retry_or_fallback` in test_software_update | Unknown update is not retried | Separate SSH launch failure and retain original transport cause (E02) |
| `test_install_failure_retains_successful_pull_evidence` in test_software_update | Pip failure keeps commit evidence | Equivalent diagnostic/cause/effects through Python/CLI (E02/E15) |
| `test_receipt_write_failure_after_acceptance_preserves_in_memory_id_and_stops` in test_submission_safety | Accepted ID survives storage failure | Primary/secondary diagnostic parity and interruption combinations (E05) |
| `test_remote_receipts_survive_response_loss_and_refresh_without_resubmission` in test_submission_safety | Read-only refresh preserves receipt, no replay | Structured safe transport diagnosis without erasing IDs (E05) |
| `test_path_exists_remote` in test_remote_fs | Nominal remote test return is mapped to bool | SSH255/error versus genuine absent path (E03) |
| `test_sync_remote_skips_missing_dirs` in test_sync | Missing remote directory is skipped | Report earlier copied directories after a later failure (E14) |

Paths for these modules are in the corresponding contract's regression_evidence
list. These tests are anchors for extension, not a claim that all failure variants
are already covered.

1. **MVP10.2:** isolated diagnostic model/catalogue, safe serialization and a thin
   terminal adapter. Settle inheritance/additive envelope/debug/exit decisions
   with focused tests independent of backends. Do not migrate every API at once.
2. **MVP10.3–4:** input/publication and transport/software slices. Within 10.4,
   stale-venv and launch-versus-lost-response diagnostics should ship first.
3. **MVP10.5:** protect submission evidence, interrupts and secondary failures
   before broad presentation adoption. Lower-level exports need an explicit
   weaker/stronger contract decision; they cannot inherit guarantees by wording.
4. **MVP10.6–7:** preserve observation quality, then destructive/partial workflow
   effects and discovery. Split a task further if it combines unrelated owners.
5. **MVP10.8–9:** route parity, client/agent/human diagnosis guidance, full offline
   and packaged/reference-client checks; close every owner with named regression
   evidence. Keep scientific application behavior outside AutoSlurm.

This is a multi-slice milestone. Planning allowance after this audit: roughly
one focused day for the small shared model/adapter, one to two per adoption slice
(10.3–7), and one to two for parity/closure, about **7–13 focused days** in total.
These are uncertain engineering effort ranges with agent assistance, not elapsed
deadlines. Receipt/interruption fault injection and public result-shape changes
are the main risks. Re-estimate each slice from its concrete boundary; useful
improvements ship incrementally. No cluster deployment, environment repair,
historical-data migration or full architecture rewrite is included.

## Verification record

MVP10.1 adds this audit, its plain-data coverage register and read-only checker.
No package implementation changes, dependency installation, cluster contact or
daily-state changes are part of this task. Test and checker results are recorded
in PLAN.md's Done log after they actually run. Successful source coverage is not
MVP10 diagnostic completion, and offline tests do not establish live compatibility.

## MVP10.2 amendment

The historical counts/findings above describe the original MVP10.1 audit.
The register now also covers the implemented diagnostic foundation: 248 routes,
127 owners, 185 Python names and 15 public method/property members. This adds nine
explicit module exports and six members (including category's property) without
changing root exports. All 18 existing broad handlers remain as audited.

The new diagnostics contract references test_errors/test_error_output, with
36 focused tests and 797 passing offline tests overall. Domain exceptions now
accept optional diagnostic= while retaining positional messages/payload identity
and causes. Model/adapter ownership is implemented; E01–E18 service adoption and
command/ACP parity remain open. The [design's current contract](MVP10_actionable_errors.md#mvp102-implemented-foundation)
and installed agent recipe specify the exact opt-in API and its bounds.

## MVP10.3a amendment

Current coverage is 251 routes/129 owners: ConfigurationError is exported at root
and leaf, and configuration_failure at leaf. Python names total 188; public
method/property members stay 15 and all 18 broad catches remain. The config
contract and four public owner rows now describe implemented read/profile/
selection diagnostics, alongside the shared CLI root/alias/standalone/debug policy.

E09's read/editor replacement risk is addressed: missing, denied, corrupt JSON,
UTF-8, invalid shapes/settings, dangling links and entries appearing during a
failed read are distinct; existing files are preserved. Original cause and actual
canonical/legacy source identity are retained. This is not complete publication
race protection. E08's filter/selection defaults remain MVP10.3b; E06's publication
phase/secondary failures remain MVP10.3c. Stale-venv E01 remains MVP10.4.

The explicit dev exception boundary replaces known configuration OSError/
AttributeError failures with ConfigurationError (DiagnosticError/RuntimeError and
ValueError compatible); original exceptions remain chained. Persisted shapes and
historical evidence are unchanged. The config CLI renders expected errors through
the shared adapter; other CLI/ACP routes are not claimed migrated.

`tests/integration/test_configuration_diagnostics.py` and updated error/legacy
configuration tests verify the contract through public Python and CLI boundaries,
no reset/write on read failure, early submit/preview rejection without commands,
and unexpected-bug visibility. Full offline suite: 851 passed. Clean-wheel smoke
verifies imports, all config routes/debug, retained files and installed agent
recipe. Remaining tasks stay open; source coverage is not diagnostic completion.

## MVP10.3b.1 amendment

Current coverage is 253 routes/130 owners: InvalidRequestError is exported at
root and errors module. Python names total 190; public method/property members
stay 15 and all 18 broad catches remain. MVP10.3b was split before implementation
into authoring (b.1), snapshot selection (b.2) and pure path/render preparation
(b.3). Parent b remains open.

Command/literal/adapter, dependency graph and historical software-intent validation
adopt explicit field/option/job/project diagnostics; original tokenizer/import/
repository-parser/cycle causes remain chained. Save/schedule shape/key/script
guards and in-memory preparation adopt the same family, with exact bundle/machine
context through public preview/submit. Schedule root/standalone routes use the
shared stderr/exit/debug boundary. Submitted/saved settings are not silently
changed and callbacks are not executed by typed discovery. Generic code bugs,
process discovery and publication failures remain distinct.

Known save TypeError/KeyError and graph CycleError now use InvalidRequestError
(ValueError/DiagnosticError compatible): this dev boundary is documented without
rewriting records. Raw bundle signatures still require a trusted client contract.
The graph contract remains partial for bulk callback/ID mapping (MVP10.5); preview
still needs path/render/readiness adoption. The submit CLI's earlier broken-record
gate and filter/selector behavior remain b.2; record reads/publication remain 3c.
No universal CLI/ACP completion or stale-venv fix is claimed.

`tests/integration/test_authoring_diagnostics.py` adds 54 contract/evidence cases:
named settings, exact saved validation, literal readability, malformed/cyclic DAGs,
retained records/no commands, safe manifest/import causes, CLI/debug parity,
long bounded identity enrichment and unexpected-bug visibility. Full offline suite:
905 passed, 43 expected warnings. Clean-wheel isolated API/graph/record/CLI/debug/
optional-Typer/agent-recipe smoke passed. The register describes adopted portions
and pending boundaries; source coverage still is not diagnostic completion.

## MVP10.3b.2 amendment

Current coverage is 256 routes/132 owners, including root/leaf SelectionError
and leaf selection_failure. Python names total 193; public methods/properties
remain 15. The get-filter and submit-snapshot broad catches are removed, leaving
16 handlers. Their retired review reasons remain in the register's amendment;
all receipt-saving and other effect-boundary catches retain their safeguards.

E08's snapshot/filter masking is addressed at discovery/selection: shared analysis
retains per-entry diagnostic and broken/unavailable/missing states, healthy
neighbours, nullable unknown jobs/counts and observed graph-invalid metadata.
Configuration owns filter validation, and only absence defaults reads. Exact/
nearest selection remains payload-free; invalid selectors are typed and a newer
failed entry cannot redirect submission to an older draft. Listing creates no
directories, and automatic stale/unsubmitted cleanup excludes unknown counts.
The strict submit record gate now raises the concrete diagnosis before machine
selection. CLI and ACP discovery routes expose adopted facts while other
observation, request-validation and post-dispatch policies remain later work.

Explicit dev contracts replace missing-selection FileNotFoundError with
SelectionError and use jobs/counts=None for unknown contents. Saved JSON has no
new schema or historical rewrite. Name loading inherits typed selection errors;
direct generic record I/O/publication remains MVP10.3c, path/render b.3, stale-venv
and readiness 10.4. Selection state is not a new scheduler observation policy.

`tests/integration/test_selection_diagnostics.py` adds 60 cases covering invalid/
conflicting selectors, stable indices, no fallback/writes, directory/read denial,
missing versus broken/link/FIFO files, per-entry/known-ID evidence, invalid filter
preservation, cleanup protection, Python/CLI/JSON/debug/ACP and visible programming
bugs. Full offline suite: 965 passed, 43 expected warnings. Clean-source offline
wheel/temporary-target discovery/selection/retained-record/CLI/JSON/debug/ACP/agent
smoke passed. Source coverage still does not establish broad MVP10 completion.

## MVP10.3b.3 adoption amendment (2026-11-14)

Base `bfa69ca`; 256 routes/132 owners/16 broad catches remain registered. Pure
ExecutionContext resolution, path-selector conflicts, render/export/directive
guards and shared preview/submit shell validation use InvalidRequestError with
named field/job/machine and logical/attempted resolved paths where known. Exact
bundle identity survives shell rejection; arbitrary Bash stderr literals do not.
Status 2 is syntax rejection; killed/failed checkers retain process failures for
10.4. One structural render guard serves preparation and direct script creation.

Saved execution lookup validates producing roots/transport using SelectionError,
distinguishing absent/ambiguous/invalid evidence and retaining historical roots/
legacy transport without current-profile discovery. Direct loader I/O stays 3c;
observation-side producing_machine remains 10.6. The direct script renderer now
finishes before opening its destination, addressing E06's pre-render truncation
gap; file-write atomicity/publication effects remain 3c. Submit --debug now also
preserves preparation errors. No new error catalogue, public route or record schema.

`tests/integration/test_preparation_diagnostics.py` adds 61 checks: pure path/role/
mapping/base guards, readable evidence, preview/submit parity, environment/directive
errors without value disclosure, saved producing metadata, legacy roots, retained
script files, named late-job shell rejection, process-versus-syntax separation,
CLI/debug and unclassified programming bugs. Full offline suite: 1026 passed,
43 expected warnings. Clean-source offline wheel/temporary-target public path/
render/producing-context/retained-script/CLI/debug/ACP/installed-recipe smoke passed.
External readiness, generic record I/O/publication and universal observation/CLI/
ACP adoption remain pending.

## MVP10.3c.1 adoption amendment (2026-11-14)

Base `0e51823`; c was split before implementation into shared publication (c.1),
bundle/config domain boundaries (c.2) and receipt/cache/script persistence (c.3).
The shared atomic JSON writer now translates known serialization/OSError failures
to RecordWriteError, retaining exact destination/stage, native cause/errno and
separate destination publication/durability effects. Serialization explicitly
changes from raw TypeError/ValueError to this OSError/DiagnosticError family.
RecordCollisionError preserves FileExistsError compatibility; snapshots advance
timestamps only after clean exclusive collisions, never uncertain publication or
failed cleanup. Other direct reads/domain wrappers remain their staged adoption.

E06's shared-writer cleanup masking is addressed: temp/directory close and unlink
cannot replace primary error/cause; observed complete publication survives later
directory-sync failure. Link/replace failure keeps unknown publication even when a
file happens to exist. Secondary diagnostics are bounded, native debug causes are
retained, and unexpected bugs/interrupts remain unchanged. Two BaseException
safeguards explicitly protect resource/evidence cleanup, without broad error
classification. E06's script/domain write boundaries remain c.2/c.3 and 10.5.

32 new cases in `tests/integration/test_record_publication_diagnostics.py` cover
pre/during/post-publication fault injection, failure after an actual successful
syscall, complete retained records, directory/temp close masking, cleanup-only and
secondary failures, native interruptions/bugs, bounded secondary evidence, legacy
note support, clean versus failed-cleanup collisions and payload-free facts.
Full offline suite: 1058 passed, 43 expected warnings; clean-source offline wheel/
temporary-target API/publication/durability/cleanup/retained-record/JSON/debug/ACP/
installed-recipe smoke passed. Register matches 260 routes/135 owners/18 individually
reviewed broad catches. No record schema rewrite or scheduler outcome inference.

## VERSION.1 package identity amendment (2026-11-16)

Base `ef4b199`. Two Python routes expose one version constant owner; 262 total
routes/136 owners/18 unchanged broad catches. Root --version exits0 with the
running code version, without config/Git/cluster/command effects. It is handled
only before action dispatch, preserving application --version forwarding. Static
version imports add no diagnostic family. Console output/usage failures retain
their existing parser/I/O behavior. Editable metadata can lag source; fresh wheel/
sdist installs must match metadata/runtime/console identity. Existing helper/
record capability versions are independent. tests/unit/test_version.py covers
single-source static configuration/changelog, canonical version, effect-free
version output and forwarding; artifact smoke verifies installed parity/guidance.
Current error adoption still resumes at MVP10.3c.2, without a PyPI release.

## MVP10.3c.2 adoption amendment (2026-11-16)

Base `91136fe`; 262 routes/136 owners/18 broad catches remain registered. Direct
bundle reads, append and compatibility metadata updates reuse the existing
snapshot reader and graph validation. Missing/unreadable/malformed direct files
now raise SelectionError rather than raw FileNotFoundError/OSError; invalid saved
graphs retain InvalidRequestError. Failed opens recheck absence so raced-in
replacements and dangling links cannot trigger empty-record fallback. Bundle
names/path selectors reject unsafe separators/controls before storage access.

Shared bundle publication retains RecordWriteError, native causes, secondary
cleanup and actual publication/durability facts, adding known bundle/job/source
identity. Config publication adds configuration identity without claiming a
write never started. Metadata mutations validate before publication and refuse
replacement/clearing of known scheduler IDs. Malformed originals survive intact;
post-publication failures retain the complete new record and its known IDs.
These explicit development exception boundaries do not rewrite saved formats.

Config/configuration, filter, initialize, schedule and submit render adopted
failures once through the shared text/debug adapter; ACP retains writer
diagnostics. Preview/submit attach machine context to direct-read failures.
Unexpected bugs still propagate. Receipt/cache/script persistence remains c.3;
external readiness, orchestration and universal observation/CLI/ACP adoption
remain open.

53 new cases in `tests/integration/test_bundle_record_diagnostics.py` cover direct
read parity, races/special files, retained records/IDs, phase-aware publication,
safe selectors, metadata guards, CLI aliases/debug and ACP. Full offline suite:
1115 passed, 43 expected collision warnings. Clean-source no-Git metadata,
wheel/sdist-to-wheel and temporary installed API/CLI/ACP/guidance checks passed
for 0.2.0.dev2. The route/owner/catch register checker passes unchanged counts.

## MVP10.3c.3 adoption amendment (2026-11-16)

Base `64288dc`; 262 routes/136 owners remain registered. Broad catches now total
20: the two shared writer safeguards moved from atomic_json to _atomic_record,
and two read/close safeguards were added and individually reviewed. These broad
guards retain native bugs/interrupts and resource cleanup, without generic error
classification. Shared errors.py remains the pure diagnostic constructor owner.

Receipt/cache reads reuse extracted regular-file UTF-8 JSON/metadata I/O;
low-level operation record_read replaces the old snapshot-specific I/O stage.
Selectors and saved graph errors retain existing contracts. Local receipt
validation/list failures use SelectionError with exact path/known identity,
replacing raw file/JSON/protocol exceptions. Denied directories and broken
receipts cannot silently produce an incomplete list. Missing directories remain
empty, and reads do not create storage or launch commands.

Receipt/projection writes retain actual publication/durability/secondary cleanup
facts and accepted IDs, with submission context. Tracking identity/ID conflicts
leave original bytes intact. Existing SubmissionError wrappers and ACP retain
adopted local diagnostics with authoritative receipt payloads; secondary tracking
evidence is additive. No new scheduler/retry/interruption policy is claimed.

JSON and scripts share the same atomic publication implementation. Direct and
staged scripts preserve old or completely published text, with job/submission
context; dispatch does not follow staging failure. Cache faults add diagnostic
to existing per-item error fields without erasing live status/log text. Missing
caches stay quiet. Receipt overlay errors retain existing snapshot IDs.
asl submission text/JSON/debug exposes adopted local persistence failures and
keeps receipt/ID fields on failed refresh. Generic observation/CLI/ACP migration
remains staged.

58 new cases in tests/integration/test_evidence_record_diagnostics.py cover
read/parse/contract/special-file/race/close faults, retained IDs, projection guards,
cache/live evidence, before/after publication and public CLI/ACP boundaries.
Existing fault injection now targets the extracted reader and atomic script
adapter. Full offline suite: 1173 passed, 45 expected collision warnings. Clean-
source no-Git metadata, wheel/sdist-to-wheel and installed receipt/cache/script/
CLI/debug/ACP/guidance checks passed for 0.2.0.dev3. MVP10.3 is complete; external
transport/readiness/software adoption remains MVP10.4 next.

## MVP10.4a adoption amendment (2026-11-16)

Base `cb8ce56`; 262 routes/136 owners/20 broad catches unchanged. MVP10.4 was
split before implementation into software updates (a), SSH/helper readiness (b),
transfers/filesystem (c) and software-status observations (d). a resolves the
reported stale-venv case: installation.python is recorded before launch, failure
names executable/venv_path/correction, and effects confirm no pull/install.
Native local causes and validated standalone remote facts share the pure host
errors.py constructor; no remote package dependency or copied worker is added.

Update target selection, one remote dispatch, protocol validation and diagnostic
enrichment have focused owners. Separate pull/install effects retain completed
pulls, partial pip changes, post-pull unreadable commits and unknown responses.
Generic OSError during possible communication stays unknown; launch failures are
distinct. Arbitrary Git query failures do not imply detached/no-upstream state.
Remote identity/process/check/effect contradictions are protocol_invalid with
unknown effects, without fallback/retry. Legacy failure facts remain unknown.
Raw Git/SSH output is excluded; useful bounded pip tails are retained/redacted.
SoftwareUpdateError carries evidence+diagnostic and native local cause; update
CLI uses stderr/exit1, JSON evidence plus diagnostic and --debug. Expected request
guards use existing families, invalid explicit machines cannot default, and
unexpected local probe/update bugs propagate. Status and general adapters remain
their later tasks. No update/install/dependency policy, saved schema or history
rewrite is introduced.

66 new cases in tests/integration/test_software_update_diagnostics.py plus the
actual temporary Git/editable-install fixture's mocked-SSH missing-venv case
cover pre/during/post-operation faults and retained effects. Full offline suite:
1239 passed, 44 expected collision warnings. No-Git metadata, wheel/sdist-to-wheel
and installed version/stale-venv/native-cause/remote-facts/partial-install/CLI/debug/
guidance checks passed for 0.2.0.dev4. b SSH/helper readiness is next; parent
MVP10.4 stays open, as do broader submission/observation/CLI/ACP policies.

## FIX.ENVIRONMENT.1 amendment (2026-11-16)

Module-init configuration validation and explicit detection adopt ConfigurationError
and shared diagnostics for missing readable candidates, SSH255, launch, timeout
and unexpected responses. Detection never executes setup and saves only on a
valid selected candidate. Shared runtime Bash error wording names module_init,
env_command or venv_path; job guards stop before the application even without a
cwd. Pure setup generation lives in environment_setup.py, explicit file discovery
in module_initialization.py, and config persistence remains in config.py. No new
public routes or broad catches: 262 routes, 136 owners, 20 reviewed catches.
49 new regressions and 1288 full offline tests pass; installed section17 documents
the recipe/limits. General helper/SSH readiness remains MVP10.4b; this is not an
activation preflight, compute-readiness guarantee or receipt discovery change.

## FETCH.1 amendment (2026-11-16)

Reviewed four additions: root/module fetch_run exports, root fetch CLI, and ACP
fetch_run. Two canonical owners delegate to existing inspection/selection/cache
rather than a second retrieval engine. Total 266 routes/138 owners/20 broad
catches; route/owner facts and regression anchors are in the register. Bounded
receipt transport owns command/size/regular-file/encoding response facts; errors.py
owns diagnostic construction. Receipt refresh retains authoritative evidence;
inspection_receipts validates links and reuses one in-memory receipt overlay to
retain IDs after persistence failure. Cached fetch performs no source/remote
reads or writes. 49 new cases, 1337 offline tests and installed API/CLI/ACP/worker/
partial/cached/guidance checks pass. Wider transport/submission/observation and
universal diagnostic route parity remain staged, not completed by this slice.

## FIX.TRACKING.1 amendment (2026-11-16)

266 routes/138 owners unchanged. BulkSubmitPayload adds optional tracking_bundle;
the existing helper negotiates execution_tracking=1 separately from protocol1.
One new reviewed catch retains a rejected pre-scheduler receipt when execution
snapshot creation fails, without replay or scheduling; 21 broad catches total.
The existing persist guard first writes the authoritative receipt, then uses the
shared projection owner to update the derived cluster view. Failure stops further
submission while retaining accepted IDs. The new execution_tracking module owns
view localization/path validation, with no scheduler or transport engine.
Cluster receipt selectors verify exact backlinks; workstation paths/transport
remain original evidence. status/log/fetch/inspect/ACP reuse their existing
owners. 24 new tests cover cross-installation behavior and failure cases.
General helper/readiness/submission diagnostic adoption remains MVP10.4b/10.5.

## MVP10.4b.1 adoption amendment (2026-11-16)

266 routes/138 owners/21 reviewed broad catches unchanged. transport root and
run_slurm helper checks delegate process/UTF-8 bounds and strict response parsing
to remote_readiness; errors.py owns codes/wording/actions. ConfigurationError
guards invalid explicit roots/venvs locally. DiagnosticError carries expected
launch/timeout/signal/SSH/remote-exit/protocol/mismatch facts, native causes and
no-submission effects. Optional diagnostic context adds storage_root without a
record/protocol rewrite. Arbitrary SSH/startup output is omitted, not parsed into
authentication claims. Existing commands/setup/legacy path selection are retained.
Submit CLI renders once and honors --debug. The broad submission/receipt policy
is not changed. 70 new cases, 1431 offline tests and installed checks pass.
b.2 session lifecycle and c/d transfer/software status remain open; universal
CLI/ACP and observation diagnostic parity remain staged.

## MVP10.4b.2 adoption amendment (2026-11-16)

266 routes/138 owners/23 reviewed broad catches. Public session still yields
None/local, []/borrowed or options/owned; a focused ssh_session_resources owner
pins destination/options and observes directory/open/close/remove independently.
errors.py owns diagnostic codes/wording/actions. Expected filesystem/process
failures retain safe errno/exit facts and native causes; open/close timeouts are
30/10 seconds. Optional ssh -G is bounded and falls back on expected failures,
while invalid profiles/bugs propagate. Borrowed sharing is never explicitly closed.

Cleanup-only failure now raises. Existing body/open primary errors or interrupts
stay original, with bounded secondary diagnostics and native cleanup errors.
Three resource/evidence broad guards are reviewed, including the changed public
guard; they preserve bugs rather than relabel them. Tracked receipts preserve
known IDs/state and workstation-owned session_cleanup_diagnostics across refresh;
remote execution evidence cannot invent/replace local cleanup facts. No retries,
authentication handling, scheduler inference or historical migration. 53 new cases,
1484 offline tests and installed artifact checks pass. b is complete; 10.4c/d
transfer/filesystem/software status and 10.5/10.8 receipt/route parity remain open.

## MVP10.4c adoption amendment (2026-11-17)

266 routes/138 owners/23 broad catches unchanged. file_commands owns one-shot
process facts for metadata/mkdir/SCP/rsync, path_probe is a shared standalone
stat worker, path_observations validates metadata and remote_fs keeps resolution.
errors.py owns pure failure wording/actions. ENOENT/ENOTDIR alone means absent;
failed/denied/malformed checks raise with selected producing paths and native or
safe remote causes. Remote python3 is required, without package import/install
or fallback. Metadata reads no contents and does not prove future readiness.

Transfer sources/managed names are validated before mutation; failed started
copies stay unknown. Independent source/destination/copy effects preserve safe
phase facts; sync adds completed/unstarted/unknown subtree copy effects. Targets
are created after positive source observation, partial files retained, no final
success on failure and no retry/rollback. CLI renders once or preserves chains
with --debug. Direct success APIs and batch/checksum/ignore-existing policies
remain. Existing source/protocol mocks now meet the enforced contracts. 99 new
cases, 1583 offline tests and installed artifact checks pass. Saved formats and
helper protocols remain unchanged. Software-status adoption is 10.4d; general
receipt/observation/ACP/CLI parity and broader sync redesign remain staged.

Required-path execution preflight uses the same metadata owner with one remote
batch; exact batch count/order/path identities are validated. validate_jobs and
validate_resolved_jobs now raise DiagnosticError/resource_missing for observed
missing required paths instead of FileNotFoundError. Local native causes and
known logical/resolved paths/labels survive. Preview/submit enrich those diagnostics
with bundle identity and stop before staging/receipt/helper dispatch. This closes
the remaining false-missing preflight path, without extra remote queries.

## MVP10.4d adoption amendment (2026-11-17)

266 routes/138 owners/23 broad catches unchanged. software_expectations validates
requests and local declarations with typed errors/exact paths/native causes.
inspect_software owns one selected profile/SSH request and whole process/response
failure translation; software_status_evidence owns pure item validation/plain
diagnostic projection. Standalone Git/environment workers emit safe stage/errno/
exit facts, retain healthy neighbours and known commit/version across later failed
checks, and do not catch arbitrary TypeError/AttributeError bugs. Missing metadata
is distinct from denied/unavailable. Interpreter identity is verified on its own
machine, supporting symlinked venvs without workstation resolution. No setup,
scientific imports, code fetch/pull, dependency install, fallback or retry.

Compatibility mismatch/unknown remain findings with per-check diagnostics and
existing major-dependency/target-marker scope. Missing undeclared metadata targets
do not mandate installation. Whole operation CLI errors use shared stderr/exit1,
JSON error envelope and --debug; partial observation JSON/useful evidence/nonzero
remain. Invalid whole identity fails; malformed items become unavailable beside
good data. 86 new cases, 1669 offline tests and installed artifact checks pass.
No saved format/helper capability/history migration. Parent 10.4 is complete;
10.5–8 submission/inspection/destructive operations and universal route parity
remain open, as does planned MVP11 job-status work.


2026-11-23, FIX.CLEAN.1: completed/terminal scope eligibility reuses exact run/
receipt loading and fresh task projection. Removed the two broad app-level load
suppression catches; 266 routes/138 owners/21 broad catches remain. Unknown task
or receipt evidence cannot authorize terminal deletion. This is a focused scope
addition; per-item deletion diagnostics, partial effects and general CLI parity
remain MVP10.7/10.8. See FIX_CLEAN_1_scopes.md and test_clean_scopes.py.


2026-11-23, MULTI.1a–c: 292 routes/146 owners/21 broad catches. Added connection
observations and opt-in campaign record/inspection/fetch contracts, explicit
per-member failures and bounds. Existing scheduler/log/receipt services remain
the read owners; campaign composition does not claim their pending universal
MVP10.6 diagnostic adoption. No new broad bug-flattening handlers. Full offline
and installed fake-two-machine evidence is recorded in the installation register.
