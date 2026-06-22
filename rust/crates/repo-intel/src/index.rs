use std::collections::HashSet;
use std::path::Path;
use std::time::{Instant, SystemTime, UNIX_EPOCH};

use rusqlite::{params, Connection, Statement};
use serde::Serialize;

use crate::inventory::{
    self, content_hash, ExistingEntry, ExistingIndex, InventoryStats, PrepareOptions, PreparedFile,
    PreparedKind,
};
use crate::schema::SCHEMA_VERSION;

/// Number of paths prepared (off the writer thread) before each batch is
/// committed to the open transaction. Bounds peak in-memory file content while
/// keeping the whole refresh inside a single atomic transaction.
const PREPARE_BATCH: usize = 512;

#[derive(Debug, Clone, Serialize)]
pub struct RefreshStats {
    pub snapshot_id: String,
    pub considered: usize,
    pub indexed_candidates: usize,
    pub reindexed_content: usize,
    pub metadata_only_updates: usize,
    pub removed: usize,
    pub skipped_binary: usize,
    pub skipped_oversized: usize,
    pub duration_ms: u128,
}

/// Result of a cancellable refresh. A cancelled refresh leaves the previous
/// snapshot fully intact (the transaction is rolled back on drop).
#[derive(Debug, Clone)]
pub enum RefreshOutcome {
    Completed(RefreshStats),
    Cancelled,
}

#[derive(Debug, Clone)]
pub struct SnapshotMetadata {
    pub snapshot_id: String,
    pub indexed_at_unix_ms: i64,
    pub files_indexed: usize,
}

pub fn refresh_index(
    connection: &mut Connection,
    workspace_root: &Path,
) -> Result<RefreshStats, String> {
    match refresh_index_cancellable(connection, workspace_root, &|| false)? {
        RefreshOutcome::Completed(stats) => Ok(stats),
        // The never-cancel closure above can never produce this branch.
        RefreshOutcome::Cancelled => Err("refresh was cancelled".to_string()),
    }
}

/// Refresh the index, polling `cancel` between preparation batches and again
/// immediately before the commit. When `cancel` returns `true` the transaction
/// is dropped without committing, preserving the previous snapshot.
pub fn refresh_index_cancellable(
    connection: &mut Connection,
    workspace_root: &Path,
    cancel: &dyn Fn() -> bool,
) -> Result<RefreshOutcome, String> {
    let started = Instant::now();
    let paths = inventory::discover_paths(workspace_root);
    if cancel() {
        return Ok(RefreshOutcome::Cancelled);
    }
    apply_refresh(connection, workspace_root, &paths, started, cancel)
}

pub fn current_snapshot_metadata(connection: &Connection) -> Result<SnapshotMetadata, String> {
    let mut statement = connection
        .prepare(
            "SELECT snapshot_id, indexed_at, (SELECT COUNT(*) FROM files) AS files_indexed
             FROM repository
             ORDER BY indexed_at DESC
             LIMIT 1",
        )
        .map_err(|error| format!("failed to query repository metadata: {error}"))?;
    let (snapshot_id, indexed_at_unix_ms, files_indexed) = statement
        .query_row([], |row| {
            Ok((row.get(0)?, row.get(1)?, row.get::<_, i64>(2)?))
        })
        .map_err(|error| format!("failed to read snapshot metadata: {error}"))?;
    Ok(SnapshotMetadata {
        snapshot_id,
        indexed_at_unix_ms,
        files_indexed: usize::try_from(files_indexed)
            .map_err(|_| "repository contains an invalid file count".to_string())?,
    })
}

fn load_existing(tx: &rusqlite::Transaction<'_>) -> Result<ExistingIndex, String> {
    let mut statement = tx
        .prepare("SELECT path, size, mtime_ns, content_hash FROM files")
        .map_err(|error| format!("failed to load existing files: {error}"))?;
    let rows = statement
        .query_map([], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, i64>(1)?,
                row.get::<_, i64>(2)?,
                row.get::<_, Option<String>>(3)?,
            ))
        })
        .map_err(|error| format!("failed to iterate existing files: {error}"))?;
    let mut existing = ExistingIndex::new();
    for row in rows {
        let (path, size, mtime_ns, content_hash) =
            row.map_err(|error| format!("failed to decode existing file row: {error}"))?;
        let size = u64::try_from(size)
            .map_err(|_| format!("index contains a negative size for `{path}`"))?;
        existing.insert(
            path,
            ExistingEntry {
                size,
                mtime_ns,
                has_content: content_hash.is_some(),
            },
        );
    }
    Ok(existing)
}

/// Accumulators that survive across preparation batches.
#[derive(Default)]
struct RefreshTally {
    stats: InventoryStats,
    reindexed_content: usize,
    metadata_only_updates: usize,
    seen: HashSet<String>,
}

fn apply_refresh(
    connection: &mut Connection,
    workspace_root: &Path,
    paths: &[String],
    started: Instant,
    cancel: &dyn Fn() -> bool,
) -> Result<RefreshOutcome, String> {
    let tx = connection
        .transaction()
        .map_err(|error| format!("failed to start refresh transaction: {error}"))?;

    let existing = load_existing(&tx)?;
    let options = PrepareOptions::default();
    let pool = build_prepare_pool()?;
    let mut tally = RefreshTally::default();

    {
        let mut upsert_files = tx
            .prepare(
                "INSERT OR REPLACE INTO files(path, language, size, mtime_ns, content_hash, line_count, is_test)
                 VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)",
            )
            .map_err(|error| format!("failed preparing file upsert: {error}"))?;
        let mut delete_text = tx
            .prepare("DELETE FROM file_text WHERE path = ?1")
            .map_err(|error| format!("failed preparing text delete: {error}"))?;
        let mut insert_text = tx
            .prepare("INSERT INTO file_text(path, identifiers, content) VALUES (?1, ?2, ?3)")
            .map_err(|error| format!("failed preparing text insert: {error}"))?;

        for batch in paths.chunks(PREPARE_BATCH) {
            if cancel() {
                return Ok(RefreshOutcome::Cancelled);
            }
            let prepared = pool
                .install(|| inventory::prepare_batch(workspace_root, batch, &existing, options));
            for record in &prepared {
                // A stale `file_text` row exists only when the path was already
                // indexed as text. `path` is UNINDEXED in the FTS5 table, so an
                // unconditional `DELETE ... WHERE path = ?` would full-scan the
                // table for every file (quadratic on a cold index).
                let had_text = existing
                    .get(&record.relative_path)
                    .is_some_and(|entry| entry.has_content);
                write_record(
                    record,
                    had_text,
                    &mut tally,
                    &mut upsert_files,
                    &mut delete_text,
                    &mut insert_text,
                )?;
            }
        }
    }

    if cancel() {
        return Ok(RefreshOutcome::Cancelled);
    }

    let removed = reap_removed(&tx, &existing, &tally.seen)?;
    write_repository_metadata(&tx, workspace_root)?;
    let snapshot_id = current_snapshot_id(&tx)?;
    tx.commit()
        .map_err(|error| format!("failed committing refresh transaction: {error}"))?;

    Ok(RefreshOutcome::Completed(RefreshStats {
        snapshot_id,
        considered: tally.stats.considered,
        indexed_candidates: tally.stats.indexed_candidates,
        reindexed_content: tally.reindexed_content,
        metadata_only_updates: tally.metadata_only_updates,
        removed,
        skipped_binary: tally.stats.skipped_binary,
        skipped_oversized: tally.stats.skipped_oversized,
        duration_ms: started.elapsed().as_millis(),
    }))
}

fn write_record(
    record: &PreparedFile,
    had_text: bool,
    tally: &mut RefreshTally,
    upsert_files: &mut Statement<'_>,
    delete_text: &mut Statement<'_>,
    insert_text: &mut Statement<'_>,
) -> Result<(), String> {
    tally.seen.insert(record.relative_path.clone());
    tally.stats.considered += 1;
    if record.is_oversized() {
        tally.stats.skipped_oversized += 1;
    }
    if record.is_binary() {
        tally.stats.skipped_binary += 1;
    }
    if record.is_indexable_text() {
        tally.stats.indexed_candidates += 1;
    }

    match &record.kind {
        PreparedKind::Unchanged { .. } => {}
        PreparedKind::Oversized | PreparedKind::Binary => {
            upsert_metadata(upsert_files, record, None, 0)?;
            if had_text {
                delete_text
                    .execute(params![record.relative_path])
                    .map_err(|error| format!("failed clearing stale indexed text: {error}"))?;
            }
            tally.metadata_only_updates += 1;
        }
        PreparedKind::Text {
            content,
            content_hash,
            line_count,
            identifiers,
        } => {
            upsert_metadata(upsert_files, record, Some(content_hash), *line_count)?;
            if had_text {
                delete_text
                    .execute(params![record.relative_path])
                    .map_err(|error| format!("failed deleting prior indexed text: {error}"))?;
            }
            insert_text
                .execute(params![record.relative_path, identifiers, content])
                .map_err(|error| format!("failed inserting indexed text: {error}"))?;
            tally.reindexed_content += 1;
        }
    }
    Ok(())
}

fn upsert_metadata(
    statement: &mut Statement<'_>,
    record: &PreparedFile,
    content_hash: Option<&str>,
    line_count: i64,
) -> Result<(), String> {
    statement
        .execute(params![
            record.relative_path,
            record.language,
            i64::try_from(record.size).unwrap_or(i64::MAX),
            record.mtime_ns,
            content_hash,
            line_count,
            i64::from(record.is_test),
        ])
        .map_err(|error| format!("failed writing file metadata: {error}"))?;
    Ok(())
}

fn reap_removed(
    tx: &rusqlite::Transaction<'_>,
    existing: &ExistingIndex,
    seen: &HashSet<String>,
) -> Result<usize, String> {
    let removed_paths = existing
        .keys()
        .filter(|path| !seen.contains(*path))
        .cloned()
        .collect::<Vec<_>>();
    for path in &removed_paths {
        tx.execute("DELETE FROM files WHERE path = ?1", params![path])
            .map_err(|error| format!("failed removing deleted file metadata: {error}"))?;
        tx.execute("DELETE FROM file_text WHERE path = ?1", params![path])
            .map_err(|error| format!("failed removing deleted file text: {error}"))?;
    }
    Ok(removed_paths.len())
}

fn write_repository_metadata(
    tx: &rusqlite::Transaction<'_>,
    workspace_root: &Path,
) -> Result<(), String> {
    let now_ms = unix_time_ms();
    let snapshot_id = format!("snapshot-{now_ms}");
    let root_id = content_hash(&workspace_root.display().to_string());
    let git_head = git_head(workspace_root).unwrap_or_else(|| "unknown".to_string());
    tx.execute(
        "INSERT OR REPLACE INTO repository(root_id, canonical_root, schema_version, git_head, indexed_at, snapshot_id)
         VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
        params![
            root_id,
            workspace_root.display().to_string(),
            SCHEMA_VERSION,
            git_head,
            now_ms,
            snapshot_id
        ],
    )
    .map_err(|error| format!("failed writing repository metadata: {error}"))?;
    Ok(())
}

fn current_snapshot_id(tx: &rusqlite::Transaction<'_>) -> Result<String, String> {
    tx.query_row(
        "SELECT snapshot_id FROM repository ORDER BY indexed_at DESC LIMIT 1",
        [],
        |row| row.get(0),
    )
    .map_err(|error| format!("failed reading snapshot id: {error}"))
}

/// A bounded worker pool for preparation. Cold indexing on Windows is dominated
/// by per-file opens and security scanning, so the pool is oversubscribed
/// relative to core count to keep more I/O in flight.
fn build_prepare_pool() -> Result<rayon::ThreadPool, String> {
    let cores = std::thread::available_parallelism()
        .map(std::num::NonZeroUsize::get)
        .unwrap_or(4);
    let threads = cores.saturating_mul(2).clamp(4, 64);
    rayon::ThreadPoolBuilder::new()
        .num_threads(threads)
        .thread_name(|index| format!("repo-intel-prep-{index}"))
        .build()
        .map_err(|error| format!("failed building preparation thread pool: {error}"))
}

fn git_head(workspace_root: &Path) -> Option<String> {
    let output = std::process::Command::new("git")
        .args(["rev-parse", "HEAD"])
        .current_dir(workspace_root)
        .output()
        .ok()?;
    if !output.status.success() {
        return None;
    }
    Some(String::from_utf8(output.stdout).ok()?.trim().to_string())
}

fn unix_time_ms() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| i64::try_from(duration.as_millis()).unwrap_or(i64::MAX))
        .unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::schema::ensure_schema;
    use std::sync::atomic::{AtomicUsize, Ordering};

    fn temp_root(label: &str) -> std::path::PathBuf {
        let unique = format!(
            "clawcodex-{label}-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("clock")
                .as_nanos()
        );
        let root = std::env::temp_dir().join(unique);
        std::fs::create_dir_all(root.join("src")).expect("temporary root");
        root
    }

    fn connection() -> Connection {
        let mut connection = Connection::open_in_memory().expect("in-memory database");
        ensure_schema(&mut connection).expect("schema");
        connection
    }

    #[test]
    fn refresh_tracks_create_modify_and_delete() {
        let root = temp_root("index-lifecycle");
        let source = root.join("src/lib.rs");
        std::fs::write(&source, "pub fn alpha() {}\n").expect("initial source");
        let mut database = connection();

        let created = refresh_index(&mut database, &root).expect("initial refresh");
        assert_eq!(created.reindexed_content, 1);

        std::fs::write(&source, "pub fn beta_with_longer_name() {}\n").expect("modified source");
        let modified = refresh_index(&mut database, &root).expect("modified refresh");
        assert_eq!(modified.reindexed_content, 1);
        let content: String = database
            .query_row(
                "SELECT content FROM file_text WHERE path = 'src/lib.rs'",
                [],
                |row| row.get(0),
            )
            .expect("indexed content");
        assert!(content.contains("beta_with_longer_name"));

        std::fs::remove_file(source).expect("delete source");
        let deleted = refresh_index(&mut database, &root).expect("deleted refresh");
        assert_eq!(deleted.removed, 1);
        let count: i64 = database
            .query_row("SELECT COUNT(*) FROM files", [], |row| row.get(0))
            .expect("file count");
        assert_eq!(count, 0);

        std::fs::remove_dir_all(root).expect("cleanup");
    }

    #[test]
    fn warm_refresh_reports_no_reindexed_content() {
        let root = temp_root("index-warm");
        std::fs::write(root.join("src/lib.rs"), "pub fn alpha() {}\n").expect("source");
        let mut database = connection();
        refresh_index(&mut database, &root).expect("initial refresh");

        let warm = refresh_index(&mut database, &root).expect("warm refresh");
        assert_eq!(warm.reindexed_content, 0);
        assert_eq!(warm.metadata_only_updates, 0);
        assert_eq!(warm.removed, 0);
        assert_eq!(warm.indexed_candidates, 1);

        std::fs::remove_dir_all(root).expect("cleanup");
    }

    #[test]
    fn cancellation_before_commit_preserves_previous_snapshot() {
        let root = temp_root("index-cancel");
        let source = root.join("src/lib.rs");
        std::fs::write(&source, "pub fn stable() {}\n").expect("source");
        let mut database = connection();
        refresh_index(&mut database, &root).expect("initial refresh");
        let before: String = database
            .query_row("SELECT snapshot_id FROM repository LIMIT 1", [], |row| {
                row.get(0)
            })
            .expect("snapshot");
        let before_count: i64 = database
            .query_row("SELECT COUNT(*) FROM files", [], |row| row.get(0))
            .expect("file count");

        // Change the file so a non-cancelled refresh would re-index it, then add
        // a brand new file. Cancel only after at least one record is prepared
        // (the writer scope runs to completion) but before the commit point.
        std::fs::write(&source, "pub fn stable_but_renamed() {}\n").expect("modify source");
        std::fs::write(root.join("src/extra.rs"), "pub fn extra() {}\n").expect("new source");

        // Checkpoints in order: after discovery (poll 0), before the single
        // preparation batch (poll 1), then immediately before commit (poll 2).
        // Returning true only at the pre-commit checkpoint guarantees the batch
        // is fully prepared and written to the transaction before cancellation.
        let polls = AtomicUsize::new(0);
        let outcome = refresh_index_cancellable(&mut database, &root, &|| {
            polls.fetch_add(1, Ordering::SeqCst) >= 2
        })
        .expect("cancellable refresh");
        assert!(matches!(outcome, RefreshOutcome::Cancelled));

        // The previous snapshot, file rows, and FTS rows must be untouched.
        let after: String = database
            .query_row("SELECT snapshot_id FROM repository LIMIT 1", [], |row| {
                row.get(0)
            })
            .expect("snapshot after cancellation");
        assert_eq!(before, after);
        let after_count: i64 = database
            .query_row("SELECT COUNT(*) FROM files", [], |row| row.get(0))
            .expect("file count after cancellation");
        assert_eq!(before_count, after_count);
        let stable_content: String = database
            .query_row(
                "SELECT content FROM file_text WHERE path = 'src/lib.rs'",
                [],
                |row| row.get(0),
            )
            .expect("original indexed content");
        assert!(stable_content.contains("stable"));
        assert!(!stable_content.contains("renamed"));
        let extra: i64 = database
            .query_row(
                "SELECT COUNT(*) FROM files WHERE path = 'src/extra.rs'",
                [],
                |row| row.get(0),
            )
            .expect("extra lookup");
        assert_eq!(extra, 0);

        std::fs::remove_dir_all(root).expect("cleanup");
    }

    #[test]
    fn refresh_skips_binary_and_oversized_without_indexing_content() {
        let root = temp_root("index-classify");
        std::fs::write(root.join("src/lib.rs"), "pub fn alpha() {}\n").expect("text source");
        std::fs::write(root.join("blob.bin"), [0_u8, 1, 2, 3]).expect("binary");
        let mut database = connection();

        let stats = refresh_index(&mut database, &root).expect("refresh");
        assert_eq!(stats.skipped_binary, 1);
        assert_eq!(stats.reindexed_content, 1);
        let text_rows: i64 = database
            .query_row("SELECT COUNT(*) FROM file_text", [], |row| row.get(0))
            .expect("text rows");
        assert_eq!(text_rows, 1);
        let binary_hash: Option<String> = database
            .query_row(
                "SELECT content_hash FROM files WHERE path = 'blob.bin'",
                [],
                |row| row.get(0),
            )
            .expect("binary row");
        assert!(binary_hash.is_none());

        std::fs::remove_dir_all(root).expect("cleanup");
    }
}
