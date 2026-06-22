# Handoff to Next Coder: Large-Repository Support

Date: 2026-06-19  
Repository: `D:\ClawCodex`  
Current commit base: `219fc2a` with a heavily modified, uncommitted working tree

## Mission

Finish ClawCodex's large-repository implementation without replacing its existing `ConversationRuntime` control loop.

The architecture and correctness problems have largely been repaired. The main remaining blocker is cold-index throughput: interactive warm operations work, but the current serial filesystem/content pipeline does not scale to a 100k-file repository.

Do not claim Fable-scale readiness until the 100k benchmark and complete workspace test gate pass.

## What Was Broken

1. Repository tools used process-global workspace and ledger state. Concurrent sessions could read or mutate the wrong repository.
2. `RepoSearch` created an FTS table but searched file contents with SQL `LIKE`, causing full content scans.
3. Search cursors were not tied to an index snapshot.
4. Index schema migration and create/modify/delete/rollback behavior lacked adequate tests.
5. `WorktreeIntegrate` only returned a report even with approval; worktree paths were not verified against the repository.
6. Plugin `.sh` tools and hooks were executed directly on Windows, producing WinError 193.
7. The benchmark document contained placeholders instead of measured evidence.

## What Was Implemented

### Session-bound execution

- Added `ToolExecutionContext` in `rust/crates/tools/src/lib.rs`.
- It owns the canonical workspace root and `RepoIntelligence` instance.
- Removed the global repository-root, repository-intelligence, and task-ledger stores.
- Added `execute_tool_with_context` and `GlobalToolRegistry::execute_with_context`.
- CLI and subagent execution now construct and retain an explicit context.
- Direct `TaskLedgerRead`/`TaskLedgerUpdate` calls without `ConversationRuntime` session context are rejected.
- Added a two-thread/two-repository isolation test with repeated searches.

### Real repository search

- `rust/crates/repo-intel/src/query.rs` now uses FTS5 `MATCH` with `bm25(...)` ranking.
- SQL `LIKE` remains only for path filtering/boosting—not source-content scanning.
- Added exact-path priority, identifier/source categories, punctuation-safe FTS tokenization, deterministic ordering, bounded page sizes, and snapshot-bound cursors.
- A cursor from an old snapshot is rejected after refresh.

### Index correctness

- Schema version is now 2.
- Added v1-to-v2 migration and unknown-future-version rejection tests.
- Added tests for create, modify, delete, and transaction rollback.
- Added inventory tests for ignored directories, binary files, and oversized files.
- Verified indexes are stored externally and isolated by canonical workspace hash.
- Removed unchecked numeric casts and made `repo-intel` strict-Clippy clean.

### Worktree safety

- Diff/remove/integrate operations verify that the supplied path is a registered worktree for the current repository.
- Primary-workspace removal is rejected.
- Integration requires `approve=true`; otherwise it is a dry run.
- Approved integration requires clean source and target worktrees.
- Merge and ordered cherry-pick are supported.
- Failed integrations attempt `git merge --abort` or `git cherry-pick --abort`.
- Successful integration returns before/after commits and changed paths.
- A real temporary-repository merge integration test passes.

### Windows portability

- `.sh` plugin hooks, tools, and lifecycle commands resolve Git-for-Windows' `sh.exe`.
- Discovery order: `CLAWD_SH`, Git's exec path, then Program Files.
- Windows shell exit-code test fixtures were corrected.
- All 39 plugin tests pass.

## Current Measured Behavior

Machine: Windows 11 Enterprise, Intel i7-13850HX, 31.4 GB RAM. Release benchmark binary.

| Scenario | Result |
|---|---:|
| ClawCodex cold index: 1,139 considered / 826 text-indexed | 36.176 s |
| ClawCodex no-change refresh | 243 ms |
| Warm FTS search | 18 ms |
| Synthetic 10k cold index | Did not finish within 180 s |
| Synthetic 100k cold index | Did not finish within 300 s |

The warm architecture is viable. Cold indexing is not.

Synthetic fixtures remain outside the repository:

- `%LOCALAPPDATA%\ClawCodex\bench-10k`
- `%LOCALAPPDATA%\ClawCodex\bench-100k`

The benchmark executable is:

`%LOCALAPPDATA%\ClawCodex\cargo-target\release\repo-intel-bench.exe`

## Root Cause of the Remaining Scale Problem

`rust/crates/repo-intel/src/inventory.rs` and `index.rs` perform too much per-file work serially:

1. Discover candidate.
2. Read metadata.
3. Open/sample it for binary detection.
4. Reopen/read text content.
5. Hash and extract identifiers.
6. Perform per-file SQLite/FTS statements.

On Windows, filesystem opens and security scanning dominate the cold path. The transaction prevents partial commits but does not make discovery or content preparation concurrent. The process used little memory and modest CPU during the failed synthetic runs, supporting the conclusion that the pipeline is I/O-serialized rather than compute- or memory-bound.

## Recommended Implementation Sequence

### 1. Build a parallel preparation pipeline

- Keep final database writes deterministic and single-writer.
- Discover paths in stable normalized order.
- Use a bounded worker pool for metadata, binary sampling, text read, hash, line count, language/test classification, and identifier extraction.
- Return prepared records through a bounded channel.
- Sort or sequence records by normalized relative path before committing.
- Avoid reading unchanged files: compare size and nanosecond mtime against the existing index before binary sampling or content reads.
- Prepare and reuse SQLite statements; insert/update records in bounded batches.

Do not add a Python production dependency. A Rust dependency such as `rayon` is acceptable if justified and workspace-compatible.

### 2. Add cancellation and rollback proof

- Add cancellation checks between discovery/preparation batches and immediately before commit.
- Inject cancellation in a test after some records are prepared.
- Verify the previous snapshot, file rows, and FTS rows remain readable and unchanged.

### 3. Expand the benchmark binary

Add explicit modes for:

- cold index;
- no-change refresh;
- one changed file;
- 100 changed files;
- repeated top-20 queries;
- peak working set and database size reporting.

Target the 10k fixture first, then 100k. Record all results in `docs/LARGE_REPO_BENCHMARK_RESULTS.md`.

### 4. Fix the Windows full-suite harness

`cargo test --workspace` reached the CLI integration tests, where `rusty-claude-cli/tests/compact_output.rs` left child `claw.exe` processes waiting on mock scenarios. The children had commands similar to:

```text
claw.exe --model sonnet --permission-mode read-only --compact PARITY_SCENARIO:streaming_text
claw.exe --model sonnet --permission-mode read-only --allowedTools read_file --compact PARITY_SCENARIO:read_file_roundtrip
```

Reproduce with:

```powershell
$env:CARGO_TARGET_DIR="$env:LOCALAPPDATA\ClawCodex\cargo-target"
cargo test -p rusty-claude-cli --test compact_output compact_flag_streaming_text_only_emits_final_message_text -- --exact --nocapture
```

Add a bounded child timeout and kill-on-drop guard to the test harness. Then determine why the mock service is not completing on Windows. Do not merely ignore the tests.

### 5. Complete intelligence quality and orchestration contracts

- Replace proximity-heavy `RepoImpact` evidence with bounded manifest/dependency/LSP/co-change signals.
- Build a labelled retrieval corpus and record top-5 accuracy.
- Add central worker ownership scopes and reject overlapping allowed paths.
- Add repeated compaction/resume/fork tests proving exactly one task-ledger continuation.

## Verification Already Passing

```text
cargo clippy --workspace --all-targets -- -D warnings
cargo test -p repo-intel                       # 14 passed
cargo test -p plugins                          # 39 passed
cargo test -p tools tests::worktree_integrate_merges_clean_registered_worktree_after_approval -- --exact
cargo test -p tools tests::worktree_integrate_stays_dry_run_without_approval -- --exact
```

## Definition of Done for the Next Coder

- 100k fixture cold indexing completes within an agreed measured target.
- No-change, one-file, and 100-file refresh results are published.
- Search remains bounded, deterministic, snapshot-safe, and accurate after parallelization.
- Cancellation leaves the previous snapshot intact.
- `cargo fmt --all -- --check` passes.
- `cargo clippy --workspace --all-targets -- -D warnings` passes.
- `cargo test --workspace` completes without orphan processes or ignored failures.
- Worktree ownership/path-overlap enforcement is tested.
- Benchmark and handoff documents contain actual evidence, not `TBD` values.

## Working-Tree Warning

The repository was already heavily dirty before this work. Preserve all unrelated modifications and untracked files. Do not use `git reset --hard`, broad checkout/revert commands, or cleanup commands. Keep Cargo build artifacts under `%LOCALAPPDATA%\ClawCodex\cargo-target`.

For the more detailed audit trail, also read:

- `docs/HANDOFF_LARGE_REPO_IMPLEMENTATION_2026-06-19.md`
- `docs/LARGE_REPO_BENCHMARK_RESULTS.md`
- `docs/HANDOFF_FINISH_LARGE_REPO_GPT_5_3_CODEX.md`
