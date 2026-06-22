//! Repository-intelligence benchmark harness.
//!
//! Usage:
//!   repo-intel-bench <workspace> [mode] [query]
//!
//! Modes (default `all`):
//!   all            cold -> no-change -> one-file -> hundred-files -> search
//!   cold           clear the index, then full rebuild
//!   warm           refresh again with no changes
//!   one-file       touch a single file, then refresh
//!   hundred-files  touch up to 100 files, then refresh
//!   search         run repeated top-20 queries
//!
//! Peak working set is not captured in-process (the workspace forbids `unsafe`,
//! so the Win32 process-memory APIs are unavailable). Measure it externally,
//! e.g. with `Measure-Command` / Task Manager, or via the on-disk index size
//! reported here as `index_db_bytes`.

use std::path::{Path, PathBuf};
use std::time::Instant;

use ignore::WalkBuilder;
use repo_intel::{RepoIntelligence, RepoSearchInput};

const TOUCH_BATCH: usize = 100;
const SEARCH_ITERATIONS: usize = 20;

fn main() {
    let args = std::env::args().skip(1).collect::<Vec<_>>();
    let workspace = args
        .first()
        .map_or_else(|| std::env::current_dir().expect("cwd"), PathBuf::from);
    let mode = args.get(1).map_or("all", String::as_str).to_string();
    let query = args.get(2).cloned().unwrap_or_else(|| "main".to_string());

    let intel = RepoIntelligence::new(&workspace).expect("repo intel should initialize");
    let workspace_root = intel.workspace_root().to_path_buf();

    let mut report = serde_json::Map::new();
    report.insert(
        "workspace".to_string(),
        serde_json::json!(workspace_root.display().to_string()),
    );
    report.insert("mode".to_string(), serde_json::json!(mode));
    report.insert("query".to_string(), serde_json::json!(query));

    match mode.as_str() {
        "cold" => {
            report.insert("cold".to_string(), run_cold(&intel));
        }
        "warm" => {
            report.insert("no_change".to_string(), run_no_change(&intel));
        }
        "one-file" => {
            report.insert(
                "one_file".to_string(),
                run_touch(&intel, &workspace_root, 1),
            );
        }
        "hundred-files" => {
            report.insert(
                "hundred_files".to_string(),
                run_touch(&intel, &workspace_root, TOUCH_BATCH),
            );
        }
        "search" => {
            report.insert("search".to_string(), run_search(&intel, &query));
        }
        _ => {
            report.insert("cold".to_string(), run_cold(&intel));
            report.insert("no_change".to_string(), run_no_change(&intel));
            report.insert(
                "one_file".to_string(),
                run_touch(&intel, &workspace_root, 1),
            );
            report.insert(
                "hundred_files".to_string(),
                run_touch(&intel, &workspace_root, TOUCH_BATCH),
            );
            report.insert("search".to_string(), run_search(&intel, &query));
        }
    }

    report.insert(
        "index_db_bytes".to_string(),
        serde_json::json!(index_db_bytes(&intel)),
    );

    println!(
        "{}",
        serde_json::to_string(&serde_json::Value::Object(report)).expect("serialize report")
    );
}

fn run_cold(intel: &RepoIntelligence) -> serde_json::Value {
    intel.clear_index().expect("clear index");
    let start = Instant::now();
    let stats = intel.refresh().expect("cold refresh should succeed");
    serde_json::json!({
        "elapsed_ms": start.elapsed().as_millis(),
        "stats": stats,
    })
}

fn run_no_change(intel: &RepoIntelligence) -> serde_json::Value {
    let start = Instant::now();
    let stats = intel.refresh().expect("no-change refresh should succeed");
    serde_json::json!({
        "elapsed_ms": start.elapsed().as_millis(),
        "stats": stats,
    })
}

fn run_touch(intel: &RepoIntelligence, workspace_root: &Path, count: usize) -> serde_json::Value {
    let touched = touch_text_files(workspace_root, count);
    let start = Instant::now();
    let stats = intel.refresh().expect("incremental refresh should succeed");
    serde_json::json!({
        "requested": count,
        "touched": touched,
        "elapsed_ms": start.elapsed().as_millis(),
        "stats": stats,
    })
}

fn run_search(intel: &RepoIntelligence, query: &str) -> serde_json::Value {
    // Prime the snapshot so the first measured query is warm.
    intel.refresh().expect("refresh before search");
    let mut hit_count = 0usize;
    let start = Instant::now();
    for _ in 0..SEARCH_ITERATIONS {
        let result = intel
            .search(RepoSearchInput {
                query: query.to_string(),
                path_prefix: None,
                language: None,
                test_only: None,
                limit: Some(20),
                cursor: None,
            })
            .expect("search should succeed");
        hit_count = result.hits.len();
    }
    let total = start.elapsed();
    let iterations = u32::try_from(SEARCH_ITERATIONS).unwrap_or(1);
    serde_json::json!({
        "iterations": SEARCH_ITERATIONS,
        "total_ms": total.as_millis(),
        "avg_us": (total / iterations).as_micros(),
        "hit_count": hit_count,
    })
}

/// Append a unique marker line to up to `count` text files so the next refresh
/// must re-read them. Returns the number actually modified.
fn touch_text_files(workspace_root: &Path, count: usize) -> usize {
    let marker = format!(
        "\n// repo-intel-bench touch {}\n",
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map_or(0, |value| value.as_nanos())
    );
    let mut modified = 0usize;
    for path in collect_text_files(workspace_root, count) {
        if let Ok(mut contents) = std::fs::read(&path) {
            contents.extend_from_slice(marker.as_bytes());
            if std::fs::write(&path, &contents).is_ok() {
                modified += 1;
            }
        }
    }
    modified
}

fn collect_text_files(workspace_root: &Path, limit: usize) -> Vec<PathBuf> {
    let mut builder = WalkBuilder::new(workspace_root);
    builder.standard_filters(true);
    builder.hidden(false);
    builder.filter_entry(|entry| {
        let path = entry.path().to_string_lossy().to_ascii_lowercase();
        !path.contains("\\.git\\")
            && !path.contains("/.git/")
            && !path.contains("\\target\\")
            && !path.contains("/target/")
            && !path.contains("\\node_modules\\")
            && !path.contains("/node_modules/")
    });
    let mut out = Vec::new();
    for entry in builder.build() {
        if out.len() >= limit {
            break;
        }
        let Ok(entry) = entry else {
            continue;
        };
        if !entry.file_type().is_some_and(|kind| kind.is_file()) {
            continue;
        }
        if is_text_file(entry.path()) {
            out.push(entry.path().to_path_buf());
        }
    }
    out
}

fn is_text_file(path: &Path) -> bool {
    use std::io::Read as _;
    let Ok(mut file) = std::fs::File::open(path) else {
        return false;
    };
    let mut buffer = [0_u8; 512];
    let Ok(read) = file.read(&mut buffer) else {
        return false;
    };
    !buffer[..read].contains(&0)
}

fn index_db_bytes(intel: &RepoIntelligence) -> u64 {
    let base = intel.index_path();
    let mut total = 0u64;
    for suffix in ["", "-wal", "-shm"] {
        let path = if suffix.is_empty() {
            base.to_path_buf()
        } else {
            let mut name = base.as_os_str().to_owned();
            name.push(suffix);
            PathBuf::from(name)
        };
        if let Ok(metadata) = std::fs::metadata(&path) {
            total = total.saturating_add(metadata.len());
        }
    }
    total
}
