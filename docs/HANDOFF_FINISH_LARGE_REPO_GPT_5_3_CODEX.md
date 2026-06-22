# Finish handoff: large-repository support for GPT-5.3-Codex

**Repository:** `D:\ClawCodex`  
**Parent plan:** `docs/HANDOFF_LARGE_REPO_GPT_5_3_CODEX.md`  
**Implementer:** GPT-5.3-Codex  
**Purpose:** finish and prove the existing large-repository implementation. Do
not recreate the scaffolding that is already present.

## Mission

Bring the current partial implementation to the parent plan's full Definition
of Done. The work is complete only when repository intelligence is scalable,
workspace-isolated, transactionally correct, integrated into the single
`ConversationRuntime` loop, safe under worktree concurrency, and demonstrated
on measured large-repository fixtures.

## Current verified baseline

The following code exists and focused tests pass:

- `rust/crates/repo-intel` with cache, schema, inventory, language, index,
  query, overview, test-selection, and benchmark modules;
- native schemas for `RepoOverview`, `RepoSearch`, `RepoImpact`, `RepoTests`,
  and `RepoIndexStatus`;
- persisted `SessionTaskLedger` and `SessionTaskLedgerUpdate`;
- task ledger inclusion during compaction;
- automatic changed-path and verification evidence capture;
- `TaskLedgerRead` and `TaskLedgerUpdate`;
- worktree tool names, with `WorktreeIntegrate` currently report-only;
- large-repository prompt guidance;
- benchmark documentation and an initial benchmark binary.

Focused verification observed on 2026-06-19:

```text
cargo fmt --all --check                                      PASS
cargo test -p repo-intel                                    PASS (4 tests)
cargo test -p runtime compact_continuation_includes_task_ledger_once  PASS
cargo test -p runtime persists_task_ledger_across_save_load_and_fork  PASS
cargo test -p tools exposes_mvp_tools                       PASS
```

This is an MVP baseline, not completion evidence.

## Known critical gaps

1. `rust/crates/tools/src/lib.rs` stores the active repository root in a
   process-global `RwLock<Option<PathBuf>>`. `CliToolExecutor::execute` resets
   that global before every call. Concurrent sessions can query the wrong
   workspace.
2. `RepoSearch` uses `lower(content) LIKE '%query%'`, causing full content scans.
   The database is not providing scalable FTS retrieval.
3. The repo-intel crate has only four unit tests and lacks inventory/index/cache,
   rollback, isolation, migration, and refresh coverage.
4. Worktree tools lack ownership-overlap detection, allowed-path enforcement,
   dirty-tree protections, and executable safe integration.
5. `RepoImpact` and `RepoTests` are mostly same-directory heuristics.
6. Benchmark results are all `TBD`; no 5k/100k proof has been recorded.
7. Full workspace Clippy/tests are not proven. `cargo test -p tools` reportedly
   terminates with `STATUS_STACK_BUFFER_OVERRUN` on this machine.

## Binding decisions

Do not reopen these decisions.

1. Preserve `ConversationRuntime::run_turn` as the only agent loop.
2. Production repository intelligence remains Rust-native; do not add a Python
   process or Python runtime dependency.
3. Remove process-global workspace and task-ledger execution state from the
   repository tool path.
4. Every session/executor owns a canonical workspace-bound repository service.
5. Use SQLite FTS5 with BM25 for content/identifier retrieval. Do not retain
   `%query%` scans as the primary search path.
6. Index/cache data remains outside the repository.
7. All output remains bounded, attributable, deterministic, and pageable.
8. Worktree mutation requires explicit approval and must fail closed on dirty,
   overlapping, stale, or mismatched state.
9. Targeted tests accelerate iteration but never replace a required final gate.
10. Preserve the dirty working tree. Do not run `git clean`, `git reset`, or
    checkout-based reverts.
11. Keep Rust build artifacts outside this checkout:

```powershell
$env:CARGO_TARGET_DIR = "$env:LOCALAPPDATA\ClawCodex\cargo-target"
```

## Task 1 - eliminate global workspace cross-wiring

**Priority:** P0. Complete this before every other task.

### Current problem

`tools::global_repo_workspace_root` and `set_repo_workspace_root` are shared by
the process. A second `CliToolExecutor` can replace the first executor's root.
This violates session/worktree isolation and can produce phantom queries or
edits against the wrong checkout.

`global_task_ledger_store` is also a second ledger implementation that diverges
from the authoritative ledger owned by `runtime::Session`.

### Required implementation

1. Remove:
   - `global_repo_workspace_root`;
   - `set_repo_workspace_root`;
   - `effective_repo_workspace_root` fallback behavior for session tools;
   - `global_task_ledger_store` and its read/write execution path.
2. Add a workspace-bound execution context in the tools crate, for example:

```rust
pub struct ToolExecutionContext {
    pub workspace_root: PathBuf,
    pub repo_intelligence: RepoIntelligence,
}
```

   The exact name may differ, but ownership must be per executor/session, never
   static or thread-local.
3. Construct `RepoIntelligence` once in `CliToolExecutor::new` from the
   canonical `Session::workspace_root`. Fail runtime construction if repository
   tools are enabled but the workspace cannot be canonicalized.
4. Add `GlobalToolRegistry::execute_with_context` or equivalent. Repository and
   worktree tools must receive the executor-owned context explicitly.
5. Keep tool definitions and permission schemas in `GlobalToolRegistry`.
6. Continue intercepting `TaskLedgerRead/Update` inside `ConversationRuntime`,
   where the authoritative `Session` is available. Direct registry execution of
   these session-bound tools must return a typed "session context required"
   error instead of reading a global fallback.
7. Run every worktree Git command with an explicit, canonical workspace root.
   Do not rely on process current directory.
8. Preserve `--allowedTools`, hooks, permission prompts, and plugin tools.

### Required tests

- two executors in one process, bound to repositories A and B, issue interleaved
  `RepoSearch` calls and never observe the other's files;
- two threads query different repositories concurrently for at least 100
  iterations without cross-contamination;
- a resumed session keeps its original canonical workspace;
- a mismatched workspace load remains rejected;
- direct registry execution of a task-ledger tool fails with "session context
  required";
- worktree tools run relative to the bound repository even when process CWD is
  elsewhere;
- existing plugin/MCP and `--allowedTools` tests remain green.

### Exit gate

No mutable global or thread-local repository root/ledger exists in production
code. Concurrent isolation tests pass under repeated execution.

## Task 2 - replace linear LIKE search with FTS5/BM25

**Priority:** P0.

### Required schema

Add a versioned migration to an FTS5 virtual table, conceptually:

```sql
CREATE VIRTUAL TABLE file_text_fts USING fts5(
    path UNINDEXED,
    identifiers,
    content,
    tokenize = 'unicode61'
);
```

Keep file metadata in the ordinary `files` table. Hide SQL details behind the
repo-intel storage/query API.

### Required behavior

1. Insert/update/delete FTS rows in the same transaction as file metadata.
2. Use parameterized FTS `MATCH`; safely normalize/escape user text so symbols
   such as `foo::bar`, paths, quotes, punctuation, and Unicode cannot create
   syntax errors or injection.
3. Rank with these deterministic priorities:
   - exact normalized path;
   - exact basename/path component;
   - identifier FTS match;
   - content FTS match using BM25;
   - stable repository-relative path as tie-breaker.
4. Preserve path-prefix, language, and test-only filters.
5. Replace offset-only pagination with a snapshot-aware stable cursor containing
   the repository snapshot plus last score/path. Reject stale cursors after an
   index refresh with a clear restart-pagination response.
6. Return at most 20 hits and 32 KiB by default.
7. Do not fall back to a full-table content scan. Path-only fallback is allowed
   only when the query cannot be represented in FTS and must be labeled.

### Required tests

- exact path outranks identifier/content;
- identifier outranks prose-only content;
- BM25 returns seeded relevant files in the top five;
- punctuation, quoted strings, Unicode, Windows paths, and Rust/C++ symbol
  syntax do not break queries;
- filters compose correctly;
- cursor pages are deterministic and nonoverlapping;
- a cursor from an old snapshot is rejected;
- deleted files disappear from FTS results in the refresh transaction;
- query plans/tests prove content retrieval uses FTS rather than `LIKE`;
- model-visible output remains bounded.

### Exit gate

Warm top-20 search on the generated 100k-file fixture is <= 250 ms on the local
benchmark machine, with the environment recorded in results documentation.

## Task 3 - complete index correctness and recovery

**Priority:** P0/P1.

### Required implementation

1. Add explicit schema versioning and forward migrations.
2. Make refresh atomic:
   - inventory outside or before the write transaction as appropriate;
   - all metadata/FTS mutations committed together;
   - failure/cancellation rolls back to the previous readable snapshot.
3. Introduce cancellable refresh through an explicit token/flag passed to the
   refresh operation. Check it during inventory and batches.
4. Correctly handle create, modify, delete, rename, and branch-switch churn.
5. Canonicalize roots once and normalize stored relative paths to `/`.
6. Reject out-of-root, `..`, alternate-drive, symlink/reparse escape, and stale
   path-prefix requests.
7. Git inventory remains preferred. Non-Git walking must respect ignore files
   and skip generated/vendor directories.
8. Binary and >1 MiB files remain metadata-only.
9. Inaccessible files produce bounded diagnostics and do not abort the entire
   refresh.
10. Concurrent readers see the old snapshot until the new transaction commits.
11. Add an index lock/coordination mechanism so two refreshes for the same root
    do not corrupt or thrash the cache.
12. Cache rebuild after incompatible/corrupt schema must be explicit, safe, and
    observable.

### Required test modules

Add tests for `cache`, `schema`, `inventory`, `index`, `overview`, and
`test_select`; do not concentrate all coverage in `query.rs`.

Tests must cover:

- Git and non-Git ignore behavior;
- binary/oversized/inaccessible files;
- Unicode and long Windows paths;
- create/modify/delete/rename;
- zero-change and 100-change refresh counts;
- rollback after injected failure;
- cancellation;
- concurrent read during refresh;
- same-named repositories at different roots;
- corrupt-cache rebuild;
- cache remains outside repository;
- no source repository mutation.

### Exit gate

The 5k fixture passes all correctness cases. A forced refresh failure leaves the
previous query results available and unchanged.

## Task 4 - harden native tool contracts and end-to-end flow

**Priority:** P1.

### Required implementation

1. Validate every repository tool input with strict schemas:
   - unknown fields rejected;
   - limits clamped/rejected consistently;
   - paths normalized and contained;
   - refresh explicitly requested, never surprising.
2. Include snapshot id, truncation flag, and next cursor in relevant outputs.
3. Ensure `RepoOverview` does not dump every path.
4. Ensure all repository tools are read-only in permission policy; external
   cache writes do not grant workspace-write permission.
5. Keep `ToolSearch` discovery and `--allowedTools` authoritative.
6. Add structured telemetry for refresh/search timing, hit counts, truncation,
   cache failures, and stale cursor events. Never log source contents or secrets.

### End-to-end tests

Using a scripted model and a generated fixture, prove this native sequence:

```text
RepoOverview -> RepoSearch -> LSP/read_file -> edit_file -> RepoTests
-> targeted bash test -> configured completion verification -> finish
```

Assert:

- the full repository is never injected into a prompt;
- every tool call is bound to the session workspace;
- tool results remain bounded;
- a failed final gate returns feedback to the same `ConversationRuntime` loop;
- the correct file changes and unrelated files do not.

### Exit gate

The seeded task completes using bounded native tool calls, including a forced
compaction variant.

## Task 5 - finish task-ledger compatibility and compaction behavior

**Priority:** P1.

### Required implementation

1. Confirm session format/version strategy. If the serialized shape changed,
   add an explicit version migration rather than relying only on permissive
   defaults.
2. Older session fixtures without a ledger load with a default ledger.
3. New sessions round-trip all bounded ledger fields.
4. Forks copy the ledger but subsequent updates do not mutate the parent.
5. Repeated compaction replaces the prior rendered ledger section instead of
   duplicating it.
6. Resume uses the persisted ledger from the correct workspace.
7. Automatic evidence capture records only successful writes and proven command
   outcomes; denied/failed tools must not be recorded as completed.
8. Bound and redact ledger content. Do not automatically copy credentials,
   arbitrary command output, or full source excerpts.

### Required tests

- pre-ledger session fixture migration;
- current save/load/fork/resume;
- parent/fork independence;
- two and three consecutive compactions contain one ledger;
- failure/denial does not create false evidence;
- objective and next steps survive forced compaction and resume;
- malformed/oversized ledger data fails or truncates deterministically.

### Exit gate

A multi-turn forced-compaction task resumes and completes without rediscovering
its objective, relevant paths, decisions, changed paths, or pending tests.

## Task 6 - complete worktree ownership and safe integration

**Priority:** P1/P2. Do not begin until Tasks 1-5 are green.

### Required data model

Introduce persisted, workspace-bound worker ownership records:

```text
worker/session id
canonical worktree root
branch and base revision
allowed write globs
read-only context globs
owned paths/symbols
acceptance commands
status and evidence
```

### Required safety behavior

1. Validate worktree creation paths against configured trusted roots.
2. Reject branch/path collisions and unsafe branch names.
3. Refuse forced removal by default; never remove a dirty worktree without a
   separate explicit approval and surfaced diff summary.
4. Detect overlapping allowed-write scopes before worker launch.
5. Enforce allowed paths at the file tool layer, not merely in the prompt.
6. Shared manifests/generated files require exclusive ownership.
7. Worker completion requires a nonempty expected diff or an explicit verified
   no-change outcome; prevent phantom success.
8. Before integration verify:
   - correct workspace/session binding;
   - expected base/branch and freshness;
   - clean target worktree;
   - ownership compliance;
   - worker acceptance commands passed;
   - no unresolved overlapping changes.
9. Keep `WorktreeIntegrate` report-only by default. Execution requires
   `approve=true`, danger-full-access authorization, and all safety checks.
10. On merge/cherry-pick conflict, abort/recover the Git operation and leave the
    primary worktree at its pre-integration state.

### Required tests

- ownership overlap rejected;
- path traversal and symlink escape rejected;
- worker write outside scope denied;
- dirty removal denied;
- stale base denied;
- empty-diff completion denied when changes were expected;
- safe dry-run report;
- approved nonconflicting integration succeeds;
- conflict rolls back cleanly;
- two independent workers remain isolated;
- concurrent repository queries remain workspace-correct.

### Exit gate

Two workers modify independent fixture subsystems, pass scoped tests, integrate
safely, and pass the primary final gate. An overlapping variant fails before any
worker writes.

## Task 7 - upgrade impact and targeted-test intelligence

**Priority:** P2.

### Required signal stack

Replace same-directory-only selection with deterministic evidence from:

1. directly changed test files;
2. project/workspace manifests and package boundaries;
3. conventional module-to-test mappings;
4. indexed imports/dependency neighbors;
5. LSP definitions/references when healthy;
6. bounded recent Git co-change history;
7. project instructions/configured verification commands.

Every selected test must carry its reason, source signal, confidence, and
command. Deduplicate commands deterministically.

### Required behavior

- high confidence: explicit manifest/config/direct mapping;
- medium: dependency/reference evidence;
- low: proximity/naming/co-change heuristic;
- missing/broken LSP degrades gracefully;
- shared manifest/config changes recommend package/integration scope;
- no matches produce an honest low-confidence fallback;
- targeted tests run during iteration;
- the configured completion verification still gates final success.

### Required tests

- Rust workspace package selection;
- Python package/pytest selection;
- npm workspace TypeScript selection;
- shared configuration and root manifest changes;
- LSP available/unavailable paths;
- co-change boundedness;
- low-confidence fallback;
- targeted green plus integration red cannot complete;
- evidence is persisted in the task ledger.

### Exit gate

Seeded Rust, Python, and TypeScript tasks select expected commands with reasons,
and a deliberately failing integration test prevents completion.

## Task 8 - finish benchmark harness and publish measurements

**Priority:** P2, but the final gate depends on it.

### Required implementation

Expand `repo-intel-bench` or add fixture helpers to generate deterministic:

- 300-file unit fixture;
- 5,000-file integration fixture;
- 100,000-file scale fixture with 80% ignored/generated content;
- seeded identifiers, paths, tests, manifests, and expected query results.

The benchmark must measure:

- cold inventory/index time;
- peak resident memory;
- database size;
- zero-change, one-change, 100-change, delete/rename, and branch-switch refresh;
- warm top-20 query latency;
- top-five seeded retrieval rate;
- concurrent read behavior during refresh;
- interrupted refresh recovery;
- tool-output byte counts;
- agent rounds before first correct edit;
- targeted and full verification outcomes.

Write machine-readable JSON plus the human report. Record hardware, OS, build
profile, Git commit, fixture seed, and commands.

### Required published targets

Populate `docs/LARGE_REPO_BENCHMARK_RESULTS.md`; no `TBD` fields may remain.

Local acceptance targets:

- no-change 100k refresh <= 2 seconds;
- 100-change refresh <= 10 seconds;
- warm top-20 query <= 250 ms;
- refresh peak memory <= 512 MiB;
- each model-visible result <= 32 KiB;
- ignored/generated files absent from content index;
- interrupted refresh leaves prior snapshot usable.

If a target is missed, optimize or document a user-approved revised target. Do
not silently declare completion.

### Exit gate

Benchmark JSON and Markdown results are reproducible from documented commands
and contain measured values and caveats.

## Task 9 - diagnose tool-suite crash and run final gates

**Priority:** final blocker.

### Crash diagnosis

Reproduce `cargo test -p tools` with:

- test threads 1 and default;
- targeted test binary subsets;
- backtrace enabled;
- external `CARGO_TARGET_DIR`;
- host plugin/config state isolated through the existing test-isolation helpers.

Find and fix the `STATUS_STACK_BUFFER_OVERRUN` root cause. Do not mark the suite
green based only on targeted tests. Record the failing test/binary and the fix.

### Final commands

```powershell
$env:CARGO_TARGET_DIR = "$env:LOCALAPPDATA\ClawCodex\cargo-target"
$env:RUST_BACKTRACE = "1"
cd D:\ClawCodex\rust
cargo fmt --all --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test -p repo-intel
cargo test -p runtime
cargo test -p tools
cargo test --workspace
```

Also run the 5k and 100k benchmark commands and at least one real public
monorepo smoke test pinned to a commit.

### Exit gate

All commands exit zero. If platform-specific exclusions are unavoidable, they
must be narrowly justified, linked to an issue, and not cover new functionality.

## Final Definition of Done

Do not report completion until every item is proven:

- no process-global/thread-local repository workspace or ledger state;
- two concurrent sessions cannot cross-query repositories;
- FTS5/BM25 search replaces full content `LIKE` scans;
- incremental refresh is transactional, cancellable, isolated, and recoverable;
- ignored/binary/oversized/inaccessible paths are handled correctly;
- native tool inputs/outputs are strict, bounded, pageable, and workspace-bound;
- end-to-end agent flow works without a repository dump;
- task ledger migrates, compacts once, resumes, and records truthful evidence;
- workers enforce ownership and allowed paths;
- approved integration is safe and rollback-tested;
- impact/test selection uses multiple evidence signals;
- targeted tests cannot override a failing final gate;
- 5k/100k benchmarks contain measured results and meet approved targets;
- format, Clippy, package tests, and full workspace tests pass;
- no generated index, target, fixture corpus, credentials, or dependency output
  appears in the Git diff.

## GPT-5.3-Codex execution protocol

Execute Tasks 1-9 strictly in order. For each task:

1. read the named code and existing tests;
2. record a baseline for the focused tests being changed;
3. implement the smallest coherent production delta and tests together;
4. run focused format/Clippy/tests;
5. run the task exit gate;
6. inspect `git diff` for unrelated or generated changes;
7. write a short evidence report containing commands and exit codes;
8. do not proceed while the current task is red.

If context is limited, stop only at a green task boundary and write a handoff
that names the exact next task, blockers, commands run, and uncommitted files.
Never compress several unfinished tasks into a claim that the parent plan is
complete.
