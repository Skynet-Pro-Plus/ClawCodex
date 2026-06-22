use rusqlite::Connection;

pub const SCHEMA_VERSION: i64 = 2;

pub fn ensure_schema(connection: &mut Connection) -> Result<(), String> {
    let current_version = connection
        .query_row("PRAGMA user_version", [], |row| row.get::<_, i64>(0))
        .map_err(|error| format!("failed to read schema version: {error}"))?;
    if current_version > SCHEMA_VERSION {
        return Err(format!(
            "repo index schema {current_version} is newer than supported {SCHEMA_VERSION}"
        ));
    }
    connection
        .execute_batch(
            r"
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS repository (
    root_id TEXT PRIMARY KEY,
    canonical_root TEXT NOT NULL,
    schema_version INTEGER NOT NULL,
    git_head TEXT,
    indexed_at INTEGER NOT NULL,
    snapshot_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS files (
    path TEXT PRIMARY KEY,
    language TEXT NOT NULL,
    size INTEGER NOT NULL,
    mtime_ns INTEGER NOT NULL,
    content_hash TEXT,
    line_count INTEGER NOT NULL,
    is_test INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS manifests (
    path TEXT PRIMARY KEY,
    kind TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS test_edges (
    source_path TEXT NOT NULL,
    test_path TEXT NOT NULL,
    reason TEXT NOT NULL,
    confidence REAL NOT NULL,
    PRIMARY KEY(source_path, test_path)
);

CREATE VIRTUAL TABLE IF NOT EXISTS file_text USING fts5(
    path UNINDEXED,
    identifiers,
    content
);
",
        )
        .map_err(|error| format!("failed to initialize schema: {error}"))?;
    connection
        .pragma_update(None, "user_version", SCHEMA_VERSION)
        .map_err(|error| format!("failed to update schema version: {error}"))?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use rusqlite::Connection;

    use super::{ensure_schema, SCHEMA_VERSION};

    #[test]
    fn upgrades_existing_v1_database_in_place() {
        let mut connection = Connection::open_in_memory().expect("database");
        connection
            .execute_batch("PRAGMA user_version = 1;")
            .expect("seed v1");
        ensure_schema(&mut connection).expect("migrate schema");
        let version = connection
            .query_row("PRAGMA user_version", [], |row| row.get::<_, i64>(0))
            .expect("read version");
        assert_eq!(version, SCHEMA_VERSION);
    }

    #[test]
    fn rejects_newer_unknown_schema() {
        let mut connection = Connection::open_in_memory().expect("database");
        connection
            .execute_batch("PRAGMA user_version = 999;")
            .expect("seed future schema");
        let error = ensure_schema(&mut connection).expect_err("future schema must fail");
        assert!(error.contains("newer than supported"));
    }
}
