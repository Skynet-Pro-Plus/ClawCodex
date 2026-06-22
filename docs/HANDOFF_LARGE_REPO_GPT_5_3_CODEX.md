# Handoff: make ClawCodex effective on very large repositories

**Implementer:** GPT-5.3-Codex  
**Repository:** `D:\ClawCodex`  
**Canonical runtime:** the Rust workspace under `rust/`  
**Mission:** scale ClawCodex from ad-hoc grep/read exploration to reliable work on
large monorepos without replacing its single persistent agent loop.

## Outcome

After this roadmap, a Claw session opened at a large repository must be able to:

1. build and incrementally refresh a compact repository index;
2. retrieve relevant paths and bounded source excerpts on demand;
3. combine lexical retrieval with the existing LSP tool for definitions and references;
4. retain the objective, decisions, changed paths, and verification state across compaction;
5. decompose genuinely independent work into workspace-bound workers/worktrees;
6. select targeted tests from the changed surface, then run the configured integration gate;
7. resume later without rediscovering the entire repository.

The desired execution spine is:

```text
User
  -> ConversationRuntime (the only agent brain)
       -> repository intelligence tools
       -> ordinary read/edit/bash/LSP tools
       -> task ledger preserved across compaction
       -> optional scoped workers/worktrees
       -> targeted tests
       -> existing completion verification
```

## Binding decisions

These decisions are part of the task. Do not reopen them during implementation.

1. **Keep one agent loop.** `runtime::ConversationRuntime::run_turn` remains the
   sole chat/tool/observation loop. Do not add chat -> planner -> coder handoffs.
2. **Implement production indexing in Rust.** The Python modules under
   `src/engine/state_model`, `src/engine/project`, and `src/engine/analysis` are
   behavioral prototypes, not a runtime dependency. The current Python index is
   Python-only by default and must not be spawned from every Rust session.
3. **Add a new Rust crate named `repo-intel`.** It owns scanning, persistence,
   retrieval, repository summaries, and test-selection evidence. Runtime and
   tools depend on its public interfaces, not its SQLite schema.
4. **Store generated state outside the repository.** On Windows use
   `%LOCALAPPDATA%\ClawCodex\repo-index\<root-hash>\index.sqlite`; on other
   platforms use the normal user cache directory. Never create a multi-gigabyte
   `.claw/index` inside the target repository.
5. **Use Git as the preferred inventory.** In a Git repository, enumerate
   `git ls-files -co --exclude-standard`. Fall back to the Rust `ignore` walker
   outside Git. Never recursively scan `.git`, `target`, `node_modules`, virtual
   environments, build output, or ignored paths.
6. **Use incremental identity before hashing.** Compare canonical path,
   modification time, and size; hash/reindex only new or changed candidates.
   Delete index rows for removed files in the same transaction.
7. **Lexical retrieval first; LSP for semantics.** Implement cross-language path
   and source retrieval in the index. Reuse the existing `LSP` tool for exact
   definitions/references/diagnostics. Do not block useful search when a language
   server is absent.
8. **All tool output is bounded and pageable.** Default to at most 20 hits and
   32 KiB rendered output. Return stable path/line references and a cursor when
   more data exists. Never dump whole large files into model context.
9. **Workers are scoped, not ambient.** Every worker/session remains bound to its
   canonical workspace root. Preserve the existing workspace-mismatch protection.
10. **Verification reports evidence and uncertainty.** Targeted-test selection
    returns reasons and confidence. Low confidence must fall back to the existing
    configured completion command, never silently claim coverage.
11. **No hardcoded `D:` paths in product code.** The path above describes this
    checkout only. Product paths must be derived from platform cache/config APIs.
12. **Keep build output out of this checkout while implementing.** Set
    `CARGO_TARGET_DIR` to a user cache directory before running Rust gates.

## Preserve the current working tree

This checkout is intentionally dirty and contains both tracked modifications and
untracked feature work. Do not run `git clean`, `git reset`, or checkout-based
reverts. Before each phase:

```powershell
git status --short --untracked-files=all
$env:CARGO_TARGET_DIR = "$env:LOCALAPPDATA\ClawCodex\cargo-target"
```

Touch only the files named by the active phase plus tests and minimal wiring.
Do not commit, push, or open a pull request unless the user explicitly requests it.

## Existing components to reuse

- `rust/crates/runtime/src/conversation.rs`: persistent native-tool loop,
  auto-compaction, tool feedback, completion verification.
- `rust/crates/runtime/src/session.rs`: persisted messages, workspace binding,
  compaction metadata, resume/fork behavior.
- `rust/crates/runtime/src/compact.rs`: compaction and resumable summary format.
- `rust/crates/runtime/src/lsp_client.rs`: stateful LSP registry.
- `rust/crates/tools/src/lib.rs`: built-in tool definitions, permissions, and
  execution dispatch.
- `rust/crates/rusty-claude-cli/src/main.rs`: `CliToolExecutor` and runtime wiring.
- `rust/crates/runtime/src/git_context.rs`: current Git context discovery.
- `rust/crates/runtime/src/worker_boot.rs`: workspace-bound worker boot and trust.
- `src/engine/project/repo_map.py`: prototype repository-summary vocabulary.
- `src/engine/state_model/*`: prototype symbols/call/test mapping; use as ideas,
  not as a dependency or correctness oracle.
- `src/engine/analysis/impact.py`: prototype impact-report vocabulary.

## Phase 0 - seal a measurable baseline

### Deliverables

1. Add `rust/crates/repo-intel/` with a minimal library and test fixture helpers.
2. Add `docs/LARGE_REPO_BENCHMARK.md` defining the benchmark corpus and metrics.
3. Add an ignored, opt-in benchmark binary; do not make a 100k-file fixture part
   of normal unit tests.
4. Record baseline behavior for:
   - cold inventory;
   - repeated search using grep/glob;
   - no-change refresh;
   - one-file refresh;
   - context consumed to locate a known symbol and its test.

### Required test corpora

- Unit fixture: 100-300 mixed Rust/Python/TypeScript files.
- Integration fixture: generated 5,000-file monorepo, opt-in/local.
- Scale fixture: generated 100,000-file tree with ignored build/vendor folders,
  opt-in only.
- At least one real public monorepo recorded by commit SHA for repeatable manual
  evaluation. Do not vendor it into this repository.

### Metrics

- files considered/indexed/skipped;
- cold-index wall time and peak resident memory;
- warm-refresh wall time for zero, one, and 100 changed files;
- SQLite size;
- retrieval precision for seeded queries;
- model-visible characters per tool response;
- number of model/tool rounds before first correct edit;
- targeted and full test outcomes.

### Exit gate

The harness runs without modifying the indexed repository and writes all generated
state outside it.

## Phase 1 - Rust repository index

### Files

- New: `rust/crates/repo-intel/Cargo.toml`
- New: `rust/crates/repo-intel/src/lib.rs`
- New modules under that crate: `cache.rs`, `inventory.rs`, `language.rs`,
  `schema.rs`, `index.rs`, `query.rs`, `overview.rs`, `test_select.rs`.
- Update: `rust/Cargo.toml`, `rust/Cargo.lock`.

### Recommended dependencies

- `ignore` for non-Git fallback walking;
- `rusqlite` with bundled SQLite and FTS5 support;
- `serde` / `serde_json`;
- the smallest existing hashing dependency already present in the workspace, or
  a small deterministic root/path hash implementation.

Do not add an embedding model, vector database, daemon, or network dependency in
this phase.

### Index schema behind a storage interface

Maintain a schema version and migrations. At minimum model:

```text
repository(root_id, canonical_root, schema_version, git_head, indexed_at)
files(path, language, size, mtime_ns, content_hash, line_count, is_test)
file_text(rowid, path, identifiers, content)  -- FTS5
manifests(path, kind)
test_edges(source_path, test_path, reason, confidence)
```

Do not expose raw SQL rows outside `repo-intel`.

### Inventory rules

- Canonicalize the workspace root once.
- Prefer tracked plus untracked/nonignored Git files.
- Skip binary files using NUL/content detection.
- Skip files larger than 1 MiB by default; record their metadata but not content.
- Support configurable extension allow/deny lists.
- Recognize at least Rust, Python, TypeScript/JavaScript, C/C++, C#, Java, Go,
  TOML, YAML, JSON, Markdown, shell, and PowerShell.
- Normalize stored paths to repository-relative forward-slash paths.
- Perform refresh mutations transactionally.
- A cancelled or failed refresh must leave the previous index readable.

### Query behavior

- Search path, filename, identifiers, and source text.
- Rank exact path/identifier matches above prose matches.
- Accept optional `path_prefix`, `language`, and `test_only` filters.
- Return path, line range, score, reason, and a short excerpt.
- Deterministic ordering for equal scores.
- Never return ignored, deleted, or out-of-root paths.

### Tests

- ignored and generated directories are absent;
- weird Unicode and Windows paths round-trip;
- a binary and oversized file are metadata-only;
- a no-change refresh performs zero content reindexes;
- create/modify/delete/rename updates are correct;
- failed refresh rolls back;
- two repositories with identical names get different cache roots;
- queries cannot escape the workspace;
- pagination is stable across repeated queries.

### Exit gate

On the 5,000-file fixture: no-change refresh is below 2 seconds on the local
Windows development machine, one-file refresh reparses one file, and seeded
identifier/path queries return the expected file in the top five.

## Phase 2 - native repository-intelligence tools

### Tool surface

Add these read-only native tools to `rust/crates/tools/src/lib.rs`:

1. `RepoOverview`
   - input: optional `path`, `depth`, `refresh`;
   - output: snapshot id, language counts, top directories, manifests, likely
     entry points/test roots, dirty/index status, and truncation metadata.
2. `RepoSearch`
   - input: `query`, optional filters, `limit`, `cursor`;
   - output: ranked bounded hits with evidence.
3. `RepoImpact`
   - input: changed paths and optional symbol names;
   - output: reverse-neighbor candidates, nearby manifests, likely tests,
     confidence, and reasons. It is advisory, never permission to skip tests.
4. `RepoTests`
   - input: changed paths;
   - output: proposed test files/commands, confidence, and fallback command.
5. `RepoIndexStatus`
   - input: optional `refresh`;
   - output: index age, snapshot, counts, stale paths, refresh timing.

### Wiring

- `CliToolExecutor` must own or share a `RepoIntelligence` instance constructed
  from `Session::workspace_root`, not `std::env::current_dir()` at call time.
- Add the tools through `GlobalToolRegistry` so schemas, permission rules,
  `--allowedTools`, and `ToolSearch` remain authoritative.
- All five tools require `PermissionMode::ReadOnly`.
- Index refresh may write only to the external cache directory.
- Subagents/workers receive an index handle for their bound workspace, never the
  parent workspace by accident.
- Preserve existing native provider tool-call serialization. Do not encode these
  tools as text conventions.

### Prompt changes

Update `rust/crates/runtime/src/prompt.rs` minimally:

- tell the model to call `RepoOverview` once when unfamiliar with a large repo;
- use `RepoSearch` before broad glob/read loops;
- use LSP after identifying likely files/symbols;
- read exact implementation slices before editing;
- never claim impact coverage solely from retrieval.

Do not inject a full repository map into every system prompt.

### Tests

- tool schemas reject unknown fields and out-of-range limits;
- output is under the configured byte limit;
- stale indexes refresh without blocking unrelated read tools;
- workspace A cannot query workspace B's cache;
- denied/filtered tools respect `--allowedTools`;
- tool search discovers the new deferred/native tools;
- an agent integration test uses overview -> search -> read -> edit -> targeted
  test without receiving the whole fixture in context.

### Exit gate

The model can locate and correctly modify a seeded implementation in the
5,000-file fixture using bounded tool responses, with no prompt containing a raw
repository dump.

## Phase 3 - task ledger that survives compaction and resume

### Model

Extend `rust/crates/runtime/src/session.rs` with a versioned persisted structure:

```rust
SessionTaskLedger {
    objective,
    constraints,
    decisions,
    relevant_paths,
    changed_paths,
    verification,
    next_steps,
    repo_snapshot_id,
}
```

Use bounded collections and deterministic deduplication. Existing sessions must
load with an empty/default ledger.

### Updates

- Add read-only `TaskLedgerRead` and workspace-write `TaskLedgerUpdate` tools, or
  extend an existing task tool only if its persisted semantics already match.
- Automatically record successful `write_file`/`edit_file` paths and completed
  verification commands. Let the model explicitly record decisions, constraints,
  and next steps.
- Do not infer that a command passed unless its exit result proves it.

### Compaction

Update `rust/crates/runtime/src/compact.rs` so the ledger is always represented
once in compacted context. Repeated compaction must replace the previous ledger
section, not duplicate it. Preserve the original user objective verbatim within
a reasonable bound.

### Tests

- save/load/fork/resume round-trip;
- migration from current session version;
- two rounds of compaction contain exactly one ledger;
- changed paths and failed/passed tests survive compaction;
- a resumed session continues from `next_steps` without rediscovering seeded
  architectural facts;
- no credentials or raw tool output are copied into the ledger automatically.

### Exit gate

A forced-compaction integration test finishes a multi-step edit after resume with
the same workspace, objective, decisions, changed paths, and pending verification.

## Phase 4 - large-task decomposition and worktree isolation

Do this only after Phases 1-3 are green. Retrieval and durable state must work
before adding concurrency.

### Planning rule

Stay single-agent by default. Decompose only when at least two tasks are
independent by files/subsystems and can be verified separately. Do not parallelize
work that edits shared manifests, shared generated files, or the same symbols.

### Add native coordination tools

- `WorktreeCreate`
- `WorktreeList`
- `WorktreeRemove`
- `WorktreeDiff`
- `WorktreeIntegrate` (initially dry-run/report only; require explicit approval
  before merge/cherry-pick)

Reuse existing worker boot, branch locks, trust receipts, and workspace mismatch
events. Do not use the Python worktree manager at runtime.

### Worker contract

Every worker receives:

```json
{
  "objective": "bounded change",
  "workspace_root": "canonical worktree",
  "allowed_paths": ["subsystem/**"],
  "read_context": ["shared/api/**"],
  "constraints": ["do not change public schema"],
  "acceptance": ["exact test command"],
  "expected_output": ["diff", "test evidence", "risks"]
}
```

Reject writes outside `allowed_paths` unless the orchestrating session explicitly
revises ownership. Detect overlapping worker ownership before launch.

### Integration

- Primary session reviews each worker diff.
- Re-index changed worktrees incrementally.
- Integrate only green, nonoverlapping patches.
- Run impacted tests after each integration and the configured completion gate at
  the end.
- Empty diffs cannot count as successful worker completion.

### Tests

- workspace/session mismatch is rejected;
- overlapping ownership is rejected;
- workers cannot write outside allowed paths;
- independent workers produce isolated diffs;
- failed integration leaves the primary worktree unchanged;
- stale branch/worktree state is reported before integration;
- empty-diff phantom completion is rejected.

### Exit gate

A synthetic cross-subsystem task is completed by two isolated workers, integrated
without overlapping writes, and verified in the primary worktree.

## Phase 5 - impact-based verification

### Selection evidence

Build `RepoTests` from multiple deterministic signals:

1. build/workspace manifests (`Cargo.toml`, package manifests, solution/project
   files, pytest configuration, Go modules, etc.);
2. same-module and conventional test paths;
3. indexed import/dependency neighbors where available;
4. LSP references when the server is healthy;
5. optional Git co-change history, bounded to recent commits;
6. explicit project instructions and configured completion command.

Return every selected test with its reason and confidence. Distinguish:

- `high`: direct configured/manifest or explicit mapping;
- `medium`: dependency/reference evidence;
- `low`: naming/proximity heuristic.

### Execution policy

- Run high/medium targeted tests during iteration.
- If no tests are selected, say so and use the configured project verification.
- Before final completion, run the existing completion verification command unless
  project configuration explicitly defines an equivalent integration gate.
- Feed failures back into the same `ConversationRuntime` loop, preserving current
  completion-verification behavior.

### Tests

- Rust workspace package -> package tests;
- Python module -> nearby and configured pytest targets;
- TypeScript package -> package-local test script;
- shared manifest/config change -> integration/full-suite recommendation;
- unknown ecosystem -> honest low-confidence fallback;
- targeted green plus full red cannot complete;
- command evidence is recorded in the task ledger.

### Exit gate

Seeded changes across Rust, Python, and TypeScript fixtures select the expected
targeted tests, and a deliberately failing integration test prevents completion.

## Phase 6 - scale hardening and benchmark report

### Required scenarios

- 100,000-file repository with 80% ignored/generated content;
- 10 concurrent read-only queries during refresh;
- interrupted refresh and recovery;
- repository moved to a different canonical path;
- branch switch changing thousands of files;
- Unicode, long Windows paths, symlinks/reparse points, inaccessible files;
- missing/broken language server;
- forced context compaction mid-task;
- two workers in separate worktrees.

### Performance targets

Treat these as local acceptance targets, not universal hardware guarantees:

- ignored/generated paths never enter the content index;
- no-change warm refresh: <= 2 seconds at 100k inventory entries;
- 100 changed files refresh: <= 10 seconds;
- top-20 query: <= 250 ms after warm-up;
- each model-visible tool result: <= 32 KiB;
- index refresh peak memory: <= 512 MiB;
- cache database is external, inspectable, versioned, and safely rebuildable;
- cancellation leaves the prior snapshot usable.

Write results to `docs/LARGE_REPO_BENCHMARK_RESULTS.md` with hardware, OS, repo
commit, commands, timings, memory, failures, and remaining caveats.

## Required verification commands

Use an external target directory so this checkout does not regain the 9.5 GiB
of build artifacts that were just cleaned:

```powershell
$env:CARGO_TARGET_DIR = "$env:LOCALAPPDATA\ClawCodex\cargo-target"
cd D:\ClawCodex\rust
cargo fmt --all --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
```

During development, run focused crate/tests first, then the full gates at the end
of every phase. Add Windows-specific tests for cache paths and workspace binding.

## Definition of done

The roadmap is complete only when all of the following are true:

- production behavior is Rust-native and connected to `ConversationRuntime`;
- no second coding-agent loop or Python runtime dependency was introduced;
- repository state is external, incremental, transactional, and workspace-bound;
- retrieval outputs are bounded, pageable, attributable, and deterministic;
- compaction/resume preserves the task ledger;
- workers are isolated by canonical worktree and ownership scope;
- targeted verification is evidence-based and cannot override a failing final gate;
- the full Rust format, clippy, and test gates pass;
- benchmark results demonstrate improvement over the Phase 0 baseline;
- the Git diff contains no generated index, target, dependency, credential, or
  benchmark-corpus artifacts.

## Recommended implementation order for GPT-5.3-Codex

Work phase by phase. At each boundary:

1. inspect the named source and current tests;
2. state the smallest intended delta;
3. implement production code and tests together;
4. run focused verification;
5. run the phase exit gate;
6. summarize changed files, evidence, and remaining risks;
7. stop if the phase is not green—do not stack later architecture on a failing
   foundation.

If context or time is limited, finish Phases 0-3 completely and leave Phases 4-6
untouched. A reliable single-agent indexed workflow with durable compaction state
is more valuable than partially working parallelism.
