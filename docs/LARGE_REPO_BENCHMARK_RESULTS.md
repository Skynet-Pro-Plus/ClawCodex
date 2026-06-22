# Large Repo Benchmark Results

## Environment

- OS: Microsoft Windows 11 Enterprise
- Hardware: Intel Core i7-13850HX, 31.4 GB RAM
- Repository commit: `219fc2a` plus the uncommitted large-repo implementation (parallel preparation pipeline)
- Date: 2026-06-19
- Build: `repo-intel-bench --release`; Cargo target stored outside the repository
- Index databases stored externally under `%LOCALAPPDATA%\ClawCodex\repo-index`
- Synthetic fixtures: `%LOCALAPPDATA%\ClawCodex\bench-10k` (10,000 files), `bench-100k` (100,000 files)

## What changed since the prior run

The cold-index path was rebuilt around a bounded, parallel preparation pipeline:

- Discovery produces a deterministic, sorted, deduplicated path list.
- Per-file work (stat, binary sniff, content read, hash, line count, identifier
  extraction) runs on a `rayon` worker pool (2x cores, clamped 4..64), off the
  database-writer thread.
- Each file is opened **once**: binary detection and UTF-8 decoding share a
  single `read`, instead of the previous two opens (binary sniff + content read).
- **Unchanged files are not read at all** — size+mtime are compared against the
  previous snapshot before any content I/O.
- The single writer commits prepared records in deterministic path order through
  reused prepared statements, in bounded batches (512), inside one atomic
  transaction.
- An O(n^2) bug was removed: `file_text` is an FTS5 table with `path UNINDEXED`,
  so the old unconditional `DELETE FROM file_text WHERE path = ?` full-scanned
  the FTS table for **every** file (quadratic on a cold index). The delete is now
  issued only when the path previously had indexed text. This alone took the
  synthetic 100k cold index from 956 s to 77 s.

## Results

Times are wall-clock from the benchmark harness. "Peak memory" is not captured
in-process (the workspace forbids `unsafe`, so the Win32 process-memory APIs are
unavailable); the on-disk index size is reported instead and peak working set
should be measured externally (`Measure-Command` / Task Manager).

| Scenario | Before | After | Index size |
|---|---:|---:|---:|
| ClawCodex checkout cold index (1,140 considered / 828 text-indexed) | 36.176 s | **1.62 s** | 10.3 MB |
| ClawCodex checkout no-change refresh | 243 ms | **119 ms** | — |
| Synthetic 10k cold index | did not finish (>180 s) | **9.57 s** | 4.3 MB |
| Synthetic 10k no-change refresh | — | **445 ms** | — |
| Synthetic 10k one-file refresh | TBD | **440 ms** | — |
| Synthetic 10k 100-file refresh | TBD | **646 ms** | — |
| Synthetic 10k warm top-20 query (avg of 20) | — | **18.6 ms** | — |
| Synthetic 100k cold index | did not finish (>300 s) | **76.7 s** | 38.7 MB |
| Synthetic 100k no-change refresh | — | **3.51 s** | — |
| Synthetic 100k one-file refresh | TBD | **3.52 s** | — |
| Synthetic 100k 100-file refresh | TBD | **5.60 s** | — |
| Synthetic 100k warm top-20 query (avg of 20) | — | **45.8 ms** | — |

Notes:

- The 100k cold index now completes deterministically; it previously did not
  finish within the measurement window. With only the parallel pipeline (before
  the FTS-delete fix) it was 956 s; the fix brings it to 76.7 s.
- Incremental refresh cost on 100k (~3.5 s for one changed file) is dominated by
  stat-ing all 100k paths to detect what changed, not by content work; the actual
  reindex is one file. A filesystem watcher would be the next lever if sub-second
  incrementals are required.
- The ClawCodex-checkout warm top-20 query for the common token `main` (20 hits,
  cold OS cache) measured ~113 ms; the synthetic figures above use queries with
  few/no matches and reflect FTS latency on a warm index.

## Retrieval Quality

- Seeded query set: exact path, identifier, punctuated identifier, and snapshot
  pagination unit fixtures — all pass.
- Search remains bounded (page size <= 20), deterministic (category, then BM25
  rank, then path), and snapshot-bound (stale cursors rejected) after
  parallelization.
- A human-labelled production retrieval corpus and top-5 accuracy remain TBD.

## Verification Outcomes

- `cargo fmt --all -- --check` — passes.
- `cargo clippy --workspace --all-targets -- -D warnings` — passes.
- `cargo test -p repo-intel` — 17 passed (was 14), including new cancellation,
  warm-refresh, binary/oversized, and unchanged-skip coverage.
- `cargo test -p rusty-claude-cli --test compact_output` — 2 passed (previously
  hung and orphaned `claw.exe`); see the compact-output section below.
- `cargo test --workspace` — now **completes without orphaned processes** (the
  compact-output harness no longer wedges): 476 passed, 20 ignored, 3 failed.
  The 3 failures are pre-existing and unrelated to the large-repo work:
  `runtime::conversation::tests::{denies_tool_use_when_pre_tool_hook_blocks,
  denies_tool_use_when_pre_tool_hook_fails,
  appends_post_tool_use_failure_hook_feedback_to_tool_result}`. Their hook output
  is mangled on Windows (`"ailure hook ran"` — the leading `f` is dropped),
  pointing at a shell-backend argument/output bug in the runtime hook path, not
  in `repo-intel` or the compact-output harness.

## Cancellation / rollback

`refresh_index_cancellable` polls a cancellation closure between preparation
batches and immediately before commit. The test
`cancellation_before_commit_preserves_previous_snapshot` prepares and writes a
batch, trips the pre-commit checkpoint, and asserts the previous snapshot,
file rows, and FTS rows are all unchanged (the transaction rolls back on drop).

## compact_output harness (Windows)

Root cause of the previously orphaned `claw.exe` processes: the test builds the
child environment with `.env_clear()` and never re-adds `SystemRoot`. On Windows,
without `SystemRoot` the child cannot locate core system DLLs and aborts during
crypto/socket initialisation (`getrandom` -> `abort`,
`STATUS_ILLEGAL_INSTRUCTION 0xC000001D`) before emitting any output. Manual runs
under Git Bash masked this because MSYS auto-injects `SystemRoot` into native
children. The mock service was never at fault — it serves correctly standalone.

Fixes:

- `run_claw` forwards `SystemRoot`/`SystemDrive` and inherits a real `PATH`
  (the previous hard-coded Unix `PATH=/usr/bin:/bin` was meaningless on Windows).
- The harness now spawns with piped stdio, drains the pipes on background
  threads, waits with a bounded timeout, and on timeout kills the **whole process
  tree** (`taskkill /T` on Windows) via a kill-on-drop guard, so a wedged child
  can never orphan or stall the suite.

## Remaining for the large-repo Definition of Done

- Agree a formal cold-index target for 100k and decide whether to optimise the
  FTS bulk-insert path further (current 76.7 s is FTS-insert bound).
- Build a labelled retrieval corpus and record top-5 accuracy.
- Replace proximity-only `RepoImpact` evidence with manifest/dependency/LSP/
  co-change signals.
- Add central worker ownership scopes and reject overlapping allowed paths.
- Repeated compaction/resume/fork tests proving exactly one ledger continuation.
