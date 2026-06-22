# Large-Repository Implementation Handoff — 2026-06-19

## Outcome

The unsafe and non-functional parts of the first large-repository implementation were repaired. Repository intelligence is now session-bound, search uses SQLite FTS5/BM25 instead of scanning content with `LIKE`, index migrations and lifecycle behavior are tested, and approved worktree integration executes with safety checks and rollback attempts.

This is **not yet the final large-repository Definition of Done**. The 100k-file cold-index performance gate failed to complete within five minutes, and the Windows CLI compact-output integration harness prevented a single uninterrupted `cargo test --workspace` proof. Those gaps are recorded below rather than being hidden.

## Follow-up Update — parallel cold-index pipeline landed

The cold-index bottleneck (item 1) and the cancellation proof (item 2) are now
done, and the Windows `compact_output` harness (item 3) is fixed at its root.
See `docs/LARGE_REPO_BENCHMARK_RESULTS.md` for full measured evidence.

- Cold index is now a `rayon` parallel preparation pipeline feeding a single
  batched writer; each changed file is opened once and unchanged files are not
  read at all. An O(n^2) FTS `DELETE ... WHERE path` (full-scan per file on a
  cold index) was removed.
- Synthetic 100k cold index: **76.7 s** (previously did not finish in 300 s; was
  956 s with the parallel pipeline before the FTS-delete fix). 10k cold: 9.57 s.
  Warm/one-file/100-file/search figures published.
- `refresh_index_cancellable` checkpoints between batches and before commit; a
  cancelled refresh rolls back and preserves the prior snapshot (tested).
- `repo-intel` tests: 17 passed (was 14). `cargo fmt --all -- --check` and
  `cargo clippy --workspace --all-targets -- -D warnings` pass.
- `compact_output` root cause: the test's `.env_clear()` dropped `SystemRoot`,
  so `claw.exe` aborted during crypto/socket init before any output. Fixed by
  forwarding `SystemRoot`/`SystemDrive` + inheriting a real `PATH`, plus a
  bounded-timeout, kill-the-process-tree guard so a wedged child can never
  orphan. `cargo test --workspace` now completes without orphans (476 passed,
  20 ignored, 3 pre-existing unrelated `runtime` hook failures).

Still open from the list below: items 5 (RepoImpact quality + labelled corpus),
6 (worker ownership / path-overlap enforcement), 7 (compaction/resume/fork
ledger-continuation tests), and the 3 unrelated Windows shell-hook failures.

## Changes Completed

### Session isolation

- Removed process-global repository root, repository-intelligence instance, and task-ledger store from `tools`.
- Added `ToolExecutionContext`, constructed once per CLI/runtime workspace and passed explicitly into repository and worktree tools.
- Bound subagent tool execution to its canonical workspace.
- Kept the task ledger authoritative in `ConversationRuntime`; direct context-free ledger calls are rejected.
- Added a concurrent two-repository isolation test (100 searches per repository) to detect cross-session leakage.

### Repository indexing and search

- Added a workspace-root accessor without exposing mutable global state.
- Upgraded the index schema to version 2 with in-place migration and future-schema rejection tests.
- Replaced content `LIKE` search with FTS5 `MATCH` and BM25 ranking. Path `LIKE` remains only for bounded path boosting.
- Added safe punctuation tokenization, exact-path priority, deterministic ordering, bounded result pages, and snapshot-bound cursors that reject stale pagination.
- Kept index databases outside source repositories under the platform cache root and verified different roots get different databases.
- Added create/modify/delete refresh coverage, failed-transaction rollback coverage, ignore/binary/oversized classification coverage, and schema migration coverage.
- Removed unchecked numeric casts and made the new crate pass strict Clippy.

### Worktree orchestration

- `WorktreeDiff` and `WorktreeRemove` now require a path registered to the current repository.
- Removal refuses the primary workspace.
- `WorktreeIntegrate` remains a dry-run unless `approve=true`.
- Approved integration requires clean source and target worktrees, supports merge and ordered cherry-pick, attempts Git abort on failure, verifies the target is clean afterward, and returns before/after commits plus changed paths.
- Added a real temporary-Git-repository test proving an approved clean worktree merge.

### Windows reliability

- Fixed plugin `.sh` hooks, lifecycle commands, and tools being launched as Win32 executables.
- Git-for-Windows `sh.exe` is discovered from `CLAWD_SH`, Git's exec path, or Program Files.
- Made shell exit-code fixtures platform-correct.
- Hardened an OAuth test against legitimate credentials loaded from the checkout `.env`.
- Added retrying cleanup for transient Windows test-directory locks.

## Main Files Changed

- `rust/crates/repo-intel/src/{cache,index,inventory,language,lib,overview,query,schema,test_select}.rs`
- `rust/crates/repo-intel/src/bin/repo-intel-bench.rs`
- `rust/crates/tools/src/lib.rs`
- `rust/crates/runtime/src/session.rs`
- `rust/crates/rusty-claude-cli/src/main.rs`
- `rust/crates/plugins/src/{hooks,lib}.rs`
- `rust/crates/api/src/providers/anthropic.rs`
- `docs/LARGE_REPO_BENCHMARK_RESULTS.md`

The worktree already contained many unrelated edits and untracked files. They were preserved; no reset, cleanup, or broad revert was performed.

## Verification Evidence

- `cargo fmt --all` — passed.
- `cargo clippy --workspace --all-targets -- -D warnings` — passed.
- `cargo test -p repo-intel` — 14 passed.
- `cargo test -p plugins` — 39 passed.
- `cargo test -p tools tests::worktree_integrate_merges_clean_registered_worktree_after_approval -- --exact` — passed.
- `cargo test -p tools tests::worktree_integrate_stays_dry_run_without_approval -- --exact` — passed.
- `cargo test -p rusty-claude-cli --bin claw tests::user_defined_aliases_resolve_before_provider_dispatch -- --exact` — passed.

The full workspace run previously exposed and led to fixes for two plugin failures, one environment-sensitive OAuth fixture, and one Windows cleanup race. On the final run, the `compact_output` test binary left two child `claw.exe` processes waiting on mock scenarios; the run was terminated. Do not label the workspace suite green until that harness is fixed and rerun uninterrupted.

## Measured Performance

On Windows 11, Intel i7-13850HX, 31.4 GB RAM, release build:

- Current ClawCodex checkout: 1,139 files considered, 826 text-indexed.
- Cold refresh: 36.176 seconds.
- No-change refresh: 243 milliseconds.
- Warm FTS search: 18 milliseconds.
- Synthetic 10k cold index: did not finish within 180 seconds.
- Synthetic 100k cold index: did not finish within 300 seconds.

The external fixtures are under `%LOCALAPPDATA%\ClawCodex\bench-10k` and `bench-100k`; partial benchmark processes were terminated cleanly. Index databases remain external under `%LOCALAPPDATA%\ClawCodex\repo-index`.

## Remaining Programming, in Priority Order

1. Parallelize inventory metadata/binary sampling and content preparation while preserving deterministic path order; feed SQLite through bounded batches and prepared statements. Re-run 10k and 100k cold/warm/change benchmarks.
2. Add cancellation checkpoints between discovery batches and before transaction commit; prove cancellation leaves the previous snapshot readable.
3. Diagnose `rusty-claude-cli/tests/compact_output.rs` on Windows. Add a child timeout/kill guard so a failed mock connection cannot orphan `claw.exe`, then rerun `cargo test --workspace`.
4. Add one-file and 100-file incremental benchmark modes and peak-memory capture to the benchmark binary.
5. Replace proximity-only `RepoImpact` evidence with bounded manifest/dependency/LSP/co-change signals and build a labelled retrieval-quality corpus.
6. Add an explicit worker ownership map and allowed-path contract. Registered-worktree validation now protects Git operations, but overlapping worker scopes are not yet rejected centrally.
7. Run repeated compaction/resume/fork migration scenarios and verify exactly one ledger continuation across old session formats.

## Safe Next Command

Use the external target directory so the source tree stays lean:

```powershell
$env:CARGO_TARGET_DIR="$env:LOCALAPPDATA\ClawCodex\cargo-target"
cargo clippy --workspace --all-targets -- -D warnings
```

Then work on item 1 before claiming Fable-scale readiness. The architecture is now sound enough to optimize; the cold-path implementation is the remaining hard bottleneck.
