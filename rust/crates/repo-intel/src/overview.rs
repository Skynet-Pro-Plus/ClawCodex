use std::collections::BTreeMap;
use std::path::Path;

use rusqlite::Connection;
use serde::Serialize;

use crate::index::RefreshStats;

#[derive(Debug, Clone, Serialize)]
pub struct RepoOverview {
    pub snapshot_id: String,
    pub workspace_root: String,
    pub indexed_files: usize,
    pub language_counts: BTreeMap<String, usize>,
    pub top_directories: Vec<DirectoryCount>,
    pub manifests: Vec<String>,
    pub likely_entry_points: Vec<String>,
    pub likely_test_roots: Vec<String>,
    pub refresh: Option<RefreshStats>,
}

#[derive(Debug, Clone, Serialize)]
pub struct DirectoryCount {
    pub path: String,
    pub files: usize,
}

pub fn build_overview(
    connection: &Connection,
    workspace_root: &Path,
    path_filter: Option<&str>,
    depth: usize,
    refresh: Option<RefreshStats>,
) -> Result<RepoOverview, String> {
    let (snapshot_id, indexed_files) = read_snapshot(connection)?;
    let language_counts = read_language_counts(connection, path_filter)?;
    let top_directories = read_top_directories(connection, path_filter, depth)?;
    let manifests = read_manifests(connection)?;
    let likely_entry_points = detect_likely_entry_points(connection)?;
    let likely_test_roots = detect_likely_test_roots(connection)?;
    Ok(RepoOverview {
        snapshot_id,
        workspace_root: workspace_root.display().to_string(),
        indexed_files,
        language_counts,
        top_directories,
        manifests,
        likely_entry_points,
        likely_test_roots,
        refresh,
    })
}

fn read_snapshot(connection: &Connection) -> Result<(String, usize), String> {
    let mut statement = connection
        .prepare(
            "SELECT snapshot_id, (SELECT COUNT(*) FROM files)
             FROM repository
             ORDER BY indexed_at DESC
             LIMIT 1",
        )
        .map_err(|error| format!("failed preparing overview snapshot query: {error}"))?;
    let (snapshot_id, count) = statement
        .query_row([], |row| {
            Ok((row.get::<_, String>(0)?, row.get::<_, i64>(1)?))
        })
        .map_err(|error| format!("failed reading overview snapshot metadata: {error}"))?;
    let count = usize::try_from(count)
        .map_err(|_| "repository contains an invalid file count".to_string())?;
    Ok((snapshot_id, count))
}

fn read_language_counts(
    connection: &Connection,
    path_filter: Option<&str>,
) -> Result<BTreeMap<String, usize>, String> {
    let mut statement = connection
        .prepare(
            "SELECT language, COUNT(*) FROM files
             WHERE (?1 IS NULL OR path LIKE ?1 || '%')
             GROUP BY language
             ORDER BY COUNT(*) DESC, language ASC",
        )
        .map_err(|error| format!("failed preparing overview language query: {error}"))?;
    let rows = statement
        .query_map([path_filter], |row| {
            Ok((row.get::<_, String>(0)?, row.get::<_, i64>(1)?))
        })
        .map_err(|error| format!("failed executing overview language query: {error}"))?;
    let mut map = BTreeMap::new();
    for row in rows {
        let (language, count) =
            row.map_err(|error| format!("failed decoding overview language row: {error}"))?;
        let count = usize::try_from(count)
            .map_err(|_| format!("repository contains an invalid count for `{language}`"))?;
        map.insert(language, count);
    }
    Ok(map)
}

fn read_top_directories(
    connection: &Connection,
    path_filter: Option<&str>,
    depth: usize,
) -> Result<Vec<DirectoryCount>, String> {
    let mut statement = connection
        .prepare("SELECT path FROM files WHERE (?1 IS NULL OR path LIKE ?1 || '%')")
        .map_err(|error| format!("failed preparing overview directory query: {error}"))?;
    let rows = statement
        .query_map([path_filter], |row| row.get::<_, String>(0))
        .map_err(|error| format!("failed executing overview directory query: {error}"))?;
    let mut counts = BTreeMap::new();
    for row in rows {
        let path =
            row.map_err(|error| format!("failed decoding overview directory row: {error}"))?;
        let mut parts = path.split('/');
        let dir = (0..depth)
            .filter_map(|_| parts.next())
            .collect::<Vec<_>>()
            .join("/");
        let key = if dir.is_empty() { ".".to_string() } else { dir };
        *counts.entry(key).or_insert(0usize) += 1;
    }
    let mut entries = counts
        .into_iter()
        .map(|(path, files)| DirectoryCount { path, files })
        .collect::<Vec<_>>();
    entries.sort_by(|left, right| {
        right
            .files
            .cmp(&left.files)
            .then(left.path.cmp(&right.path))
    });
    entries.truncate(20);
    Ok(entries)
}

fn read_manifests(connection: &Connection) -> Result<Vec<String>, String> {
    let mut statement = connection
        .prepare(
            "SELECT path FROM files
             WHERE path LIKE '%/Cargo.toml'
                OR path LIKE '%/package.json'
                OR path LIKE '%/pyproject.toml'
                OR path LIKE '%/go.mod'
                OR path LIKE '%/pom.xml'
                OR path = 'Cargo.toml'
                OR path = 'package.json'
                OR path = 'pyproject.toml'
                OR path = 'go.mod'
                OR path = 'pom.xml'
             ORDER BY path ASC
             LIMIT 50",
        )
        .map_err(|error| format!("failed preparing manifest query: {error}"))?;
    let rows = statement
        .query_map([], |row| row.get::<_, String>(0))
        .map_err(|error| format!("failed executing manifest query: {error}"))?;
    let mut out = Vec::new();
    for row in rows {
        out.push(row.map_err(|error| format!("failed decoding manifest row: {error}"))?);
    }
    Ok(out)
}

fn detect_likely_entry_points(connection: &Connection) -> Result<Vec<String>, String> {
    let mut statement = connection
        .prepare(
            "SELECT path FROM files
             WHERE path IN (
                'src/main.rs', 'main.rs', 'src/main.py', 'main.py',
                'src/index.ts', 'src/index.js', 'index.ts', 'index.js',
                'cmd/main.go'
             )
                OR path LIKE '%/src/main.rs'
                OR path LIKE '%/src/main.py'
             ORDER BY path ASC
             LIMIT 20",
        )
        .map_err(|error| format!("failed preparing entry point query: {error}"))?;
    let rows = statement
        .query_map([], |row| row.get::<_, String>(0))
        .map_err(|error| format!("failed executing entry point query: {error}"))?;
    let mut out = Vec::new();
    for row in rows {
        out.push(row.map_err(|error| format!("failed decoding entry point row: {error}"))?);
    }
    Ok(out)
}

fn detect_likely_test_roots(connection: &Connection) -> Result<Vec<String>, String> {
    let mut statement = connection
        .prepare("SELECT path FROM files WHERE is_test = 1 ORDER BY path ASC LIMIT 200")
        .map_err(|error| format!("failed preparing test root query: {error}"))?;
    let rows = statement
        .query_map([], |row| row.get::<_, String>(0))
        .map_err(|error| format!("failed executing test root query: {error}"))?;
    let mut counts = BTreeMap::new();
    for row in rows {
        let path = row.map_err(|error| format!("failed decoding test path row: {error}"))?;
        let root = path
            .split('/')
            .take_while(|segment| *segment != "tests")
            .collect::<Vec<_>>()
            .join("/");
        let key = if root.is_empty() {
            "tests".to_string()
        } else {
            format!("{root}/tests")
        };
        *counts.entry(key).or_insert(0usize) += 1;
    }
    let mut out = counts.into_iter().collect::<Vec<_>>();
    out.sort_by(|left, right| right.1.cmp(&left.1).then(left.0.cmp(&right.0)));
    Ok(out.into_iter().map(|(path, _)| path).take(20).collect())
}
