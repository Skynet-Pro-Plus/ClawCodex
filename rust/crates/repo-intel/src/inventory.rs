use std::collections::HashMap;
use std::fmt::Write as _;
use std::path::Path;
use std::process::Command;

use ignore::WalkBuilder;
use rayon::prelude::*;
use serde::Serialize;
use sha2::{Digest, Sha256};

use crate::language::{detect_language, is_test_path};

pub const MAX_INDEXED_FILE_BYTES: u64 = 1_048_576;
const BINARY_SNIFF_BYTES: usize = 8192;

#[derive(Debug, Clone, Copy)]
pub struct PrepareOptions {
    pub max_file_bytes: u64,
}

impl Default for PrepareOptions {
    fn default() -> Self {
        Self {
            max_file_bytes: MAX_INDEXED_FILE_BYTES,
        }
    }
}

/// Read-only view of the previously indexed state for a single path. Used to
/// decide whether a file can be skipped without reading its contents.
#[derive(Debug, Clone, Copy)]
pub struct ExistingEntry {
    pub size: u64,
    pub mtime_ns: i64,
    pub has_content: bool,
}

pub type ExistingIndex = HashMap<String, ExistingEntry>;

#[derive(Debug, Clone, Default, Serialize)]
pub struct InventoryStats {
    pub considered: usize,
    pub indexed_candidates: usize,
    pub skipped_binary: usize,
    pub skipped_oversized: usize,
}

/// A file whose filesystem state and (when required) contents have been
/// prepared off the database-writer thread.
#[derive(Debug, Clone)]
pub struct PreparedFile {
    pub relative_path: String,
    pub language: String,
    pub size: u64,
    pub mtime_ns: i64,
    pub is_test: bool,
    pub kind: PreparedKind,
}

/// What, if anything, the database writer must do for a [`PreparedFile`].
#[derive(Debug, Clone)]
pub enum PreparedKind {
    /// Size and mtime match the existing index; no content work was performed.
    Unchanged { binary: bool, oversized: bool },
    /// Changed or new, but larger than the indexing limit.
    Oversized,
    /// Changed or new, but detected as binary (NUL byte or non-UTF-8).
    Binary,
    /// Changed or new UTF-8 text file with extracted content.
    Text {
        content: String,
        content_hash: String,
        line_count: i64,
        identifiers: String,
    },
}

impl PreparedFile {
    #[must_use]
    pub fn is_oversized(&self) -> bool {
        matches!(
            self.kind,
            PreparedKind::Oversized
                | PreparedKind::Unchanged {
                    oversized: true,
                    ..
                }
        )
    }

    #[must_use]
    pub fn is_binary(&self) -> bool {
        matches!(
            self.kind,
            PreparedKind::Binary | PreparedKind::Unchanged { binary: true, .. }
        )
    }

    #[must_use]
    pub fn is_indexable_text(&self) -> bool {
        !self.is_binary() && !self.is_oversized()
    }
}

/// Discover candidate files in a stable, deduplicated, normalized order.
///
/// Prefers `git ls-files` (respecting `.gitignore`) and falls back to a
/// filtered filesystem walk for non-Git workspaces.
#[must_use]
pub fn discover_paths(workspace_root: &Path) -> Vec<String> {
    let mut paths = git_inventory(workspace_root).unwrap_or_else(|| walk_inventory(workspace_root));
    paths.sort_unstable();
    paths.dedup();
    paths
}

/// Prepare a batch of candidate paths in parallel.
///
/// Each path is stat-ed and, only when it has changed since the previous
/// snapshot, read exactly once for binary detection and content extraction.
/// Output order follows the input slice so the database writer commits in a
/// deterministic order.
#[must_use]
pub fn prepare_batch(
    workspace_root: &Path,
    paths: &[String],
    existing: &ExistingIndex,
    options: PrepareOptions,
) -> Vec<PreparedFile> {
    paths
        .par_iter()
        .filter_map(|relative_path| prepare_one(workspace_root, relative_path, existing, options))
        .collect()
}

fn prepare_one(
    workspace_root: &Path,
    relative_path: &str,
    existing: &ExistingIndex,
    options: PrepareOptions,
) -> Option<PreparedFile> {
    let absolute_path = workspace_root.join(relative_path);
    let metadata = match std::fs::metadata(&absolute_path) {
        Ok(metadata) if metadata.is_file() => metadata,
        // A vanished or unreadable entry is treated as absent; if it was
        // indexed before it will be reaped as a removal this pass.
        _ => return None,
    };
    let size = metadata.len();
    let mtime_ns = metadata
        .modified()
        .ok()
        .and_then(|value| value.duration_since(std::time::UNIX_EPOCH).ok())
        .map(|duration| i64::try_from(duration.as_nanos()).unwrap_or(i64::MAX))
        .unwrap_or_default();
    let language = detect_language(relative_path).to_string();
    let is_test = is_test_path(relative_path);
    let oversized = size > options.max_file_bytes;

    if let Some(previous) = existing.get(relative_path) {
        if previous.size == size && previous.mtime_ns == mtime_ns {
            return Some(PreparedFile {
                relative_path: relative_path.to_string(),
                language,
                size,
                mtime_ns,
                is_test,
                kind: PreparedKind::Unchanged {
                    binary: !previous.has_content && !oversized,
                    oversized,
                },
            });
        }
    }

    let kind = if oversized {
        PreparedKind::Oversized
    } else {
        match std::fs::read(&absolute_path) {
            Ok(bytes) => classify_bytes(bytes),
            // Transiently unreadable (e.g. a Windows lock); skip this pass.
            Err(_) => return None,
        }
    };

    Some(PreparedFile {
        relative_path: relative_path.to_string(),
        language,
        size,
        mtime_ns,
        is_test,
        kind,
    })
}

fn classify_bytes(bytes: Vec<u8>) -> PreparedKind {
    let sniff = bytes.len().min(BINARY_SNIFF_BYTES);
    if bytes[..sniff].contains(&0) {
        return PreparedKind::Binary;
    }
    match String::from_utf8(bytes) {
        Ok(content) => {
            let content_hash = content_hash(&content);
            let line_count = i64::try_from(content.lines().count()).unwrap_or(i64::MAX);
            let identifiers = extract_identifiers(&content);
            PreparedKind::Text {
                content,
                content_hash,
                line_count,
                identifiers,
            }
        }
        Err(_) => PreparedKind::Binary,
    }
}

#[must_use]
pub(crate) fn content_hash(content: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(content.as_bytes());
    let digest = hasher.finalize();
    let mut out = String::with_capacity(digest.len() * 2);
    for byte in digest {
        write!(out, "{byte:02x}").expect("writing to a String cannot fail");
    }
    out
}

fn extract_identifiers(content: &str) -> String {
    let mut out = Vec::new();
    let mut token = String::new();
    for ch in content.chars() {
        if ch.is_ascii_alphanumeric() || ch == '_' {
            token.push(ch);
        } else if token.len() >= 3 {
            out.push(std::mem::take(&mut token));
        } else {
            token.clear();
        }
    }
    if token.len() >= 3 {
        out.push(token);
    }
    out.sort();
    out.dedup();
    out.join(" ")
}

fn git_inventory(workspace_root: &Path) -> Option<Vec<String>> {
    let output = Command::new("git")
        .args(["ls-files", "-co", "--exclude-standard"])
        .current_dir(workspace_root)
        .output()
        .ok()?;
    if !output.status.success() {
        return None;
    }
    let text = String::from_utf8(output.stdout).ok()?;
    Some(
        text.lines()
            .map(str::trim)
            .filter(|line| !line.is_empty())
            .map(|line| line.replace('\\', "/"))
            .collect(),
    )
}

fn walk_inventory(workspace_root: &Path) -> Vec<String> {
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
            && !path.contains("\\.venv\\")
            && !path.contains("/.venv/")
            && !path.contains("\\venv\\")
            && !path.contains("/venv/")
    });
    let mut out = Vec::new();
    for entry in builder.build() {
        let Ok(entry) = entry else {
            continue;
        };
        if !entry.file_type().is_some_and(|kind| kind.is_file()) {
            continue;
        }
        let Ok(relative) = entry.path().strip_prefix(workspace_root) else {
            continue;
        };
        out.push(relative.to_string_lossy().replace('\\', "/"));
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temp_root(label: &str) -> std::path::PathBuf {
        let unique = format!(
            "clawcodex-{label}-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .expect("clock")
                .as_nanos()
        );
        let root = std::env::temp_dir().join(unique);
        std::fs::create_dir_all(&root).expect("temporary root");
        root
    }

    fn stats(files: &[PreparedFile]) -> InventoryStats {
        let mut stats = InventoryStats::default();
        for file in files {
            stats.considered += 1;
            if file.is_oversized() {
                stats.skipped_oversized += 1;
            }
            if file.is_binary() {
                stats.skipped_binary += 1;
            }
            if file.is_indexable_text() {
                stats.indexed_candidates += 1;
            }
        }
        stats
    }

    #[test]
    fn inventory_honors_ignores_and_classifies_unindexable_files() {
        let root = temp_root("inventory");
        std::fs::create_dir_all(root.join("src")).expect("src");
        std::fs::create_dir_all(root.join("target")).expect("target");
        std::fs::write(root.join("src/main.rs"), "fn main() {}\n").expect("source");
        std::fs::write(root.join("target/generated.rs"), "ignored\n").expect("ignored");
        std::fs::write(root.join("asset.bin"), [0_u8, 1, 2]).expect("binary");
        std::fs::write(root.join("large.txt"), "012345678901234567890123456789").expect("large");

        let paths = discover_paths(&root);
        let existing = ExistingIndex::new();
        let files = prepare_batch(
            &root,
            &paths,
            &existing,
            PrepareOptions { max_file_bytes: 20 },
        );
        let paths = files
            .iter()
            .map(|candidate| candidate.relative_path.as_str())
            .collect::<Vec<_>>();
        assert!(paths.contains(&"src/main.rs"));
        assert!(paths.contains(&"asset.bin"));
        assert!(paths.contains(&"large.txt"));
        assert!(!paths.contains(&"target/generated.rs"));

        let stats = stats(&files);
        assert_eq!(stats.skipped_binary, 1);
        assert_eq!(stats.skipped_oversized, 1);

        std::fs::remove_dir_all(root).expect("cleanup");
    }

    #[test]
    fn unchanged_files_are_not_reread() {
        let root = temp_root("inventory-unchanged");
        std::fs::create_dir_all(root.join("src")).expect("src");
        let source = root.join("src/lib.rs");
        std::fs::write(&source, "pub fn alpha() {}\n").expect("source");

        let paths = discover_paths(&root);
        let cold = prepare_batch(
            &root,
            &paths,
            &ExistingIndex::new(),
            PrepareOptions::default(),
        );
        let prepared = cold
            .iter()
            .find(|file| file.relative_path == "src/lib.rs")
            .expect("source prepared");
        let (size, mtime_ns) = (prepared.size, prepared.mtime_ns);
        assert!(matches!(prepared.kind, PreparedKind::Text { .. }));

        // Re-running against an existing snapshot with matching size/mtime must
        // classify the file as Unchanged without reading its contents.
        let mut existing = ExistingIndex::new();
        existing.insert(
            "src/lib.rs".to_string(),
            ExistingEntry {
                size,
                mtime_ns,
                has_content: true,
            },
        );
        let warm = prepare_batch(&root, &paths, &existing, PrepareOptions::default());
        let warm = warm
            .iter()
            .find(|file| file.relative_path == "src/lib.rs")
            .expect("source re-prepared");
        assert!(matches!(warm.kind, PreparedKind::Unchanged { .. }));
        assert!(warm.is_indexable_text());

        std::fs::remove_dir_all(root).expect("cleanup");
    }
}
