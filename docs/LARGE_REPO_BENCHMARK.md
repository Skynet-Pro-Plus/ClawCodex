# Large Repo Benchmark Harness

This document defines the benchmark corpus and measurements for large-repository
indexing and retrieval in ClawCodex.

## Corpus

- Unit fixture: 100-300 mixed Rust/Python/TypeScript files.
- Integration fixture: generated 5,000-file monorepo (opt-in).
- Scale fixture: generated 100,000-file tree with ignored build/vendor folders (opt-in).
- At least one real public monorepo by commit SHA (manual evaluation; not vendored).

## Metrics

- files considered / indexed / skipped (binary, oversized, ignored);
- cold-index wall time and peak memory;
- warm-refresh wall time for zero, one, and 100 changed files;
- SQLite index size on disk;
- retrieval precision for seeded path/symbol queries;
- model-visible characters per tool response;
- tool rounds before first correct edit;
- targeted and full test outcomes.

## Harness Constraints

- Index writes must go to external cache, never inside the repository.
- Harness must not mutate indexed repository content.
- Fixture generation and heavy benchmarks are opt-in.

## Baseline Collection Procedure

1. Set external Cargo target directory:
   - `$env:CARGO_TARGET_DIR = "$env:LOCALAPPDATA\ClawCodex\cargo-target"`
2. Run cold index on benchmark fixture.
3. Run repeated lexical retrieval baseline (`glob_search` / `grep_search`) for seeded queries.
4. Run no-change refresh, one-file refresh, and 100-file refresh.
5. Record timings and memory.

## Reporting

Write measured outputs to `docs/LARGE_REPO_BENCHMARK_RESULTS.md` with hardware,
OS, commit SHA, commands, timings, memory, and caveats.
