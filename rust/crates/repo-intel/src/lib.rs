mod cache;
mod index;
mod inventory;
mod language;
mod overview;
mod query;
mod schema;
mod test_select;

use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

pub use crate::index::{RefreshOutcome, RefreshStats};
pub use crate::inventory::InventoryStats;
pub use crate::overview::RepoOverview;
pub use crate::query::{RepoSearchHit, RepoSearchInput, RepoSearchResult};
pub use crate::test_select::{RepoImpactResult, RepoTestsResult, SelectedTest};
use rusqlite::Connection;
use serde::Serialize;

const DEFAULT_MAX_OUTPUT_BYTES: usize = 32 * 1024;

#[derive(Debug, Clone, Serialize)]
pub struct RepoIndexStatus {
    pub workspace_root: String,
    pub snapshot_id: String,
    pub index_path: String,
    pub indexed_at_unix_ms: i64,
    pub age_seconds: u64,
    pub files_indexed: usize,
    pub refresh: Option<RefreshStats>,
}

#[derive(Debug, Clone)]
pub struct RepoIntelligence {
    workspace_root: PathBuf,
    index_path: PathBuf,
}

impl RepoIntelligence {
    pub fn new(workspace_root: impl AsRef<Path>) -> Result<Self, String> {
        let canonical_root = workspace_root
            .as_ref()
            .canonicalize()
            .map_err(|error| format!("failed to resolve workspace root: {error}"))?;
        let index_path = cache::index_path_for_workspace(&canonical_root)?;
        Ok(Self {
            workspace_root: canonical_root,
            index_path,
        })
    }

    pub fn refresh(&self) -> Result<RefreshStats, String> {
        let mut connection = self.open_connection()?;
        index::refresh_index(&mut connection, &self.workspace_root)
    }

    /// Refresh the index, polling `cancel` between preparation batches and
    /// before commit. A cancelled refresh leaves the previous snapshot intact.
    pub fn refresh_cancellable(&self, cancel: &dyn Fn() -> bool) -> Result<RefreshOutcome, String> {
        let mut connection = self.open_connection()?;
        index::refresh_index_cancellable(&mut connection, &self.workspace_root, cancel)
    }

    #[must_use]
    pub fn workspace_root(&self) -> &Path {
        &self.workspace_root
    }

    #[must_use]
    pub fn index_path(&self) -> &Path {
        &self.index_path
    }

    /// Delete the on-disk index (and its WAL/SHM sidecars) so the next refresh
    /// rebuilds from scratch. Used by the cold-index benchmark mode.
    pub fn clear_index(&self) -> Result<(), String> {
        for suffix in ["", "-wal", "-shm"] {
            let path = if suffix.is_empty() {
                self.index_path.clone()
            } else {
                let mut name = self.index_path.as_os_str().to_owned();
                name.push(suffix);
                PathBuf::from(name)
            };
            match std::fs::remove_file(&path) {
                Ok(()) => {}
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
                Err(error) => {
                    return Err(format!("failed clearing index file {path:?}: {error}"));
                }
            }
        }
        Ok(())
    }

    pub fn overview(
        &self,
        path: Option<&str>,
        depth: Option<usize>,
        refresh: bool,
    ) -> Result<RepoOverview, String> {
        let mut refresh_stats = None;
        if refresh {
            refresh_stats = Some(self.refresh()?);
        }
        let connection = self.open_connection()?;
        overview::build_overview(
            &connection,
            &self.workspace_root,
            path,
            depth.unwrap_or(3),
            refresh_stats,
        )
    }

    pub fn search(&self, input: RepoSearchInput) -> Result<RepoSearchResult, String> {
        let connection = self.open_connection()?;
        query::search_repo(&connection, &self.workspace_root, input)
    }

    pub fn impact(&self, changed_paths: Vec<String>) -> Result<RepoImpactResult, String> {
        let connection = self.open_connection()?;
        test_select::build_impact_report(&connection, changed_paths)
    }

    pub fn tests(&self, changed_paths: Vec<String>) -> Result<RepoTestsResult, String> {
        let connection = self.open_connection()?;
        test_select::select_tests(&connection, changed_paths)
    }

    pub fn status(&self, refresh: bool) -> Result<RepoIndexStatus, String> {
        let refresh_stats = if refresh { Some(self.refresh()?) } else { None };
        let connection = self.open_connection()?;
        let metadata = index::current_snapshot_metadata(&connection)?;
        let now_ms = unix_time_ms();
        let age_seconds = now_ms
            .saturating_sub(metadata.indexed_at_unix_ms)
            .checked_div(1_000)
            .unwrap_or(0)
            .try_into()
            .unwrap_or(u64::MAX);
        Ok(RepoIndexStatus {
            workspace_root: self.workspace_root.display().to_string(),
            snapshot_id: metadata.snapshot_id,
            index_path: self.index_path.display().to_string(),
            indexed_at_unix_ms: metadata.indexed_at_unix_ms,
            age_seconds,
            files_indexed: metadata.files_indexed,
            refresh: refresh_stats,
        })
    }

    fn open_connection(&self) -> Result<Connection, String> {
        let mut connection = Connection::open(&self.index_path)
            .map_err(|error| format!("failed to open repo index database: {error}"))?;
        schema::ensure_schema(&mut connection)?;
        Ok(connection)
    }
}

#[must_use]
pub fn truncate_for_model(mut text: String) -> String {
    if text.len() <= DEFAULT_MAX_OUTPUT_BYTES {
        return text;
    }
    text.truncate(DEFAULT_MAX_OUTPUT_BYTES.saturating_sub(64));
    text.push_str("\n\n... output truncated (use cursor for next page).");
    text
}

fn unix_time_ms() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| i64::try_from(duration.as_millis()).unwrap_or(i64::MAX))
        .unwrap_or_default()
}
