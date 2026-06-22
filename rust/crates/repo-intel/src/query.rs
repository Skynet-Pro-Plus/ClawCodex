use std::collections::BTreeMap;
use std::path::Path;

use rusqlite::{params, Connection};
use serde::{Deserialize, Serialize};

const MAX_PAGE_SIZE: usize = 20;
const MAX_CURSOR_OFFSET: usize = 100_000;
const MAX_EXCERPT_CHARS: usize = 600;

#[derive(Debug, Clone, Deserialize)]
pub struct RepoSearchInput {
    pub query: String,
    pub path_prefix: Option<String>,
    pub language: Option<String>,
    pub test_only: Option<bool>,
    pub limit: Option<usize>,
    pub cursor: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct RepoSearchResult {
    pub query: String,
    pub snapshot_id: String,
    pub limit: usize,
    pub cursor: Option<String>,
    pub next_cursor: Option<String>,
    pub hits: Vec<RepoSearchHit>,
}

#[derive(Debug, Clone, Serialize)]
pub struct RepoSearchHit {
    pub path: String,
    pub line_start: usize,
    pub line_end: usize,
    pub score: i64,
    pub reason: String,
    pub excerpt: String,
}

#[derive(Debug)]
struct CandidateHit {
    path: String,
    content: String,
    category: i64,
    rank: f64,
    reason: String,
}

pub fn search_repo(
    connection: &Connection,
    _workspace_root: &Path,
    input: RepoSearchInput,
) -> Result<RepoSearchResult, String> {
    let query = input.query.trim();
    if query.is_empty() {
        return Err("query must not be empty".to_string());
    }
    let snapshot_id = current_snapshot_id(connection)?;
    let offset = parse_cursor(input.cursor.as_deref(), &snapshot_id)?;
    let limit = input.limit.unwrap_or(MAX_PAGE_SIZE).clamp(1, MAX_PAGE_SIZE);
    let fetch_count = offset
        .saturating_add(limit)
        .saturating_add(1)
        .min(MAX_CURSOR_OFFSET);
    let test_only = input.test_only.map(i64::from);
    let mut candidates = BTreeMap::<String, CandidateHit>::new();

    collect_path_hits(
        connection,
        query,
        input.path_prefix.as_deref(),
        input.language.as_deref(),
        test_only,
        fetch_count,
        &mut candidates,
    )?;
    if let Some(expression) = build_fts_expression(query) {
        collect_fts_hits(
            connection,
            &expression,
            query,
            input.path_prefix.as_deref(),
            input.language.as_deref(),
            test_only,
            fetch_count,
            &mut candidates,
        )?;
    }

    let mut ordered = candidates.into_values().collect::<Vec<_>>();
    ordered.sort_by(|left, right| {
        right
            .category
            .cmp(&left.category)
            .then_with(|| left.rank.total_cmp(&right.rank))
            .then_with(|| left.path.cmp(&right.path))
    });
    let has_more = ordered.len() > offset.saturating_add(limit);
    let hits = ordered
        .into_iter()
        .skip(offset)
        .take(limit)
        .enumerate()
        .map(|(index, candidate)| candidate.into_search_hit(index, query))
        .collect::<Vec<_>>();
    let next_cursor = has_more.then(|| format_cursor(&snapshot_id, offset + limit));

    Ok(RepoSearchResult {
        query: query.to_string(),
        snapshot_id,
        limit,
        cursor: input.cursor,
        next_cursor,
        hits,
    })
}

#[allow(clippy::too_many_arguments)]
fn collect_path_hits(
    connection: &Connection,
    query: &str,
    path_prefix: Option<&str>,
    language: Option<&str>,
    test_only: Option<i64>,
    fetch_count: usize,
    candidates: &mut BTreeMap<String, CandidateHit>,
) -> Result<(), String> {
    let fetch_count = i64::try_from(fetch_count).map_err(|_| "search limit overflow")?;
    let mut statement = connection
        .prepare(
            "SELECT f.path, COALESCE(substr(t.content, 1, 4096), '')
             FROM files f
             LEFT JOIN file_text t ON t.path = f.path
             WHERE (?1 IS NULL OR f.path LIKE ?1 || '%')
               AND (?2 IS NULL OR f.language = ?2)
               AND (?3 IS NULL OR f.is_test = ?3)
               AND lower(f.path) LIKE '%' || lower(?4) || '%'
             ORDER BY CASE WHEN lower(f.path) = lower(?4) THEN 0 ELSE 1 END, f.path
             LIMIT ?5",
        )
        .map_err(|error| format!("failed preparing path search query: {error}"))?;
    let rows = statement
        .query_map(
            params![path_prefix, language, test_only, query, fetch_count],
            |row| Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?)),
        )
        .map_err(|error| format!("failed executing path search query: {error}"))?;
    for row in rows {
        let (path, content) =
            row.map_err(|error| format!("failed decoding path search result: {error}"))?;
        let exact = path.eq_ignore_ascii_case(query);
        candidates.insert(
            path.clone(),
            CandidateHit {
                path,
                content,
                category: if exact { 1_000 } else { 900 },
                rank: 0.0,
                reason: if exact { "exact-path" } else { "path" }.to_string(),
            },
        );
    }
    Ok(())
}

#[allow(clippy::too_many_arguments)]
fn collect_fts_hits(
    connection: &Connection,
    expression: &str,
    raw_query: &str,
    path_prefix: Option<&str>,
    language: Option<&str>,
    test_only: Option<i64>,
    fetch_count: usize,
    candidates: &mut BTreeMap<String, CandidateHit>,
) -> Result<(), String> {
    let fetch_count = i64::try_from(fetch_count).map_err(|_| "search limit overflow")?;
    let mut statement = connection
        .prepare(
            "SELECT f.path, file_text.identifiers, file_text.content,
                    bm25(file_text, 0.0, 5.0, 1.0) AS relevance
             FROM file_text
             JOIN files f ON f.path = file_text.path
             WHERE file_text MATCH ?1
               AND (?2 IS NULL OR f.path LIKE ?2 || '%')
               AND (?3 IS NULL OR f.language = ?3)
               AND (?4 IS NULL OR f.is_test = ?4)
             ORDER BY relevance, f.path
             LIMIT ?5",
        )
        .map_err(|error| format!("failed preparing FTS search query: {error}"))?;
    let rows = statement
        .query_map(
            params![expression, path_prefix, language, test_only, fetch_count],
            |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, String>(1)?,
                    row.get::<_, String>(2)?,
                    row.get::<_, f64>(3)?,
                ))
            },
        )
        .map_err(|error| format!("failed executing FTS search query: {error}"))?;
    let normalized_query = raw_query.to_lowercase();
    for row in rows {
        let (path, identifiers, content, rank) =
            row.map_err(|error| format!("failed decoding FTS search result: {error}"))?;
        let identifier_match = identifiers.to_lowercase().contains(&normalized_query);
        let candidate = CandidateHit {
            path: path.clone(),
            content,
            category: if identifier_match { 800 } else { 700 },
            rank,
            reason: if identifier_match {
                "identifier"
            } else {
                "source"
            }
            .to_string(),
        };
        let replace = candidates
            .get(&path)
            .is_none_or(|existing| candidate.category > existing.category);
        if replace {
            candidates.insert(path, candidate);
        }
    }
    Ok(())
}

impl CandidateHit {
    fn into_search_hit(self, index: usize, query: &str) -> RepoSearchHit {
        let (line_start, line_end, excerpt) = locate_excerpt(&self.content, query);
        let position = i64::try_from(index).unwrap_or(i64::MAX).min(99);
        RepoSearchHit {
            path: self.path,
            line_start,
            line_end,
            score: self.category.saturating_sub(position),
            reason: self.reason,
            excerpt,
        }
    }
}

fn current_snapshot_id(connection: &Connection) -> Result<String, String> {
    connection
        .query_row(
            "SELECT snapshot_id FROM repository ORDER BY indexed_at DESC LIMIT 1",
            [],
            |row| row.get(0),
        )
        .map_err(|error| format!("repository index has no current snapshot: {error}"))
}

fn parse_cursor(cursor: Option<&str>, snapshot_id: &str) -> Result<usize, String> {
    let Some(cursor) = cursor else {
        return Ok(0);
    };
    let (cursor_snapshot, raw_offset) = cursor
        .rsplit_once(':')
        .ok_or_else(|| "invalid cursor; restart search without a cursor".to_string())?;
    if cursor_snapshot != snapshot_id {
        return Err("stale cursor; repository snapshot changed, restart search".to_string());
    }
    let offset = raw_offset
        .parse::<usize>()
        .map_err(|error| format!("invalid cursor offset: {error}"))?;
    if offset > MAX_CURSOR_OFFSET {
        return Err("cursor offset exceeds search limit".to_string());
    }
    Ok(offset)
}

fn format_cursor(snapshot_id: &str, offset: usize) -> String {
    format!("{snapshot_id}:{offset}")
}

fn build_fts_expression(query: &str) -> Option<String> {
    let tokens = query
        .split(|character: char| !(character.is_alphanumeric() || character == '_'))
        .filter(|token| !token.is_empty())
        .map(|token| format!("\"{token}\"*"))
        .collect::<Vec<_>>();
    (!tokens.is_empty()).then(|| tokens.join(" AND "))
}

fn locate_excerpt(content: &str, query: &str) -> (usize, usize, String) {
    if content.is_empty() {
        return (1, 1, String::new());
    }
    let query_token = query
        .split_whitespace()
        .find(|token| content.to_lowercase().contains(&token.to_lowercase()))
        .unwrap_or(query);
    let lower_content = content.to_lowercase();
    let lower_query = query_token.to_lowercase();
    if let Some(index) = lower_content.find(&lower_query) {
        let line_start = content[..index]
            .bytes()
            .filter(|byte| *byte == b'\n')
            .count()
            + 1;
        let line_end = line_start + 4;
        let excerpt = content
            .lines()
            .skip(line_start.saturating_sub(1))
            .take(5)
            .collect::<Vec<_>>()
            .join("\n");
        return (line_start, line_end, bound_excerpt(excerpt));
    }
    let excerpt = content.lines().take(5).collect::<Vec<_>>().join("\n");
    (1, 5, bound_excerpt(excerpt))
}

fn bound_excerpt(excerpt: String) -> String {
    if excerpt.chars().count() <= MAX_EXCERPT_CHARS {
        return excerpt;
    }
    let mut bounded = excerpt
        .chars()
        .take(MAX_EXCERPT_CHARS.saturating_sub(24))
        .collect::<String>();
    bounded.push_str("\n... excerpt truncated");
    bounded
}

#[cfg(test)]
mod tests {
    use rusqlite::Connection;

    use crate::schema::ensure_schema;

    use super::{search_repo, RepoSearchInput, MAX_EXCERPT_CHARS};

    fn setup() -> Connection {
        let mut connection = Connection::open_in_memory().expect("in-memory db");
        ensure_schema(&mut connection).expect("schema");
        connection
            .execute(
                "INSERT INTO repository(root_id, canonical_root, schema_version, git_head, indexed_at, snapshot_id)
                 VALUES ('root', '.', 1, 'head', 1, 'snapshot-test')",
                [],
            )
            .expect("insert repository");
        insert_file(
            &connection,
            "src/main.rs",
            false,
            "main execute unique_identifier",
            "fn main() {\n  execute();\n}\n",
        );
        insert_file(
            &connection,
            "tests/main_test.rs",
            true,
            "main test",
            "#[test]\nfn test_main(){}\n",
        );
        connection
    }

    fn insert_file(
        connection: &Connection,
        path: &str,
        is_test: bool,
        identifiers: &str,
        content: &str,
    ) {
        connection
            .execute(
                "INSERT INTO files(path, language, size, mtime_ns, content_hash, line_count, is_test)
                 VALUES (?1, 'rust', 10, 1, 'h', 1, ?2)",
                (path, i64::from(is_test)),
            )
            .expect("insert file");
        connection
            .execute(
                "INSERT INTO file_text(path, identifiers, content) VALUES (?1, ?2, ?3)",
                (path, identifiers, content),
            )
            .expect("insert text");
    }

    fn input(query: &str) -> RepoSearchInput {
        RepoSearchInput {
            query: query.to_string(),
            path_prefix: None,
            language: None,
            test_only: None,
            limit: Some(20),
            cursor: None,
        }
    }

    #[test]
    fn exact_path_outranks_fts_matches() {
        let connection = setup();
        let result = search_repo(&connection, std::path::Path::new("."), input("src/main.rs"))
            .expect("search should succeed");
        assert_eq!(result.hits[0].path, "src/main.rs");
        assert_eq!(result.hits[0].reason, "exact-path");
    }

    #[test]
    fn fts_identifier_search_returns_expected_file() {
        let connection = setup();
        let result = search_repo(
            &connection,
            std::path::Path::new("."),
            input("unique_identifier"),
        )
        .expect("FTS search should succeed");
        assert_eq!(result.hits[0].path, "src/main.rs");
        assert_eq!(result.hits[0].reason, "identifier");
    }

    #[test]
    fn punctuation_is_safely_tokenized_for_fts() {
        let connection = setup();
        let result = search_repo(
            &connection,
            std::path::Path::new("."),
            input("main::execute"),
        )
        .expect("punctuated search should succeed");
        assert!(result.hits.iter().any(|hit| hit.path == "src/main.rs"));
    }

    #[test]
    fn cursor_is_snapshot_bound_and_paginates() {
        let connection = setup();
        let mut first_input = input("main");
        first_input.limit = Some(1);
        let first = search_repo(&connection, std::path::Path::new("."), first_input)
            .expect("first page should succeed");
        assert_eq!(first.hits.len(), 1);
        let cursor = first.next_cursor.clone().expect("next cursor");
        let second = search_repo(
            &connection,
            std::path::Path::new("."),
            RepoSearchInput {
                cursor: Some(cursor.clone()),
                limit: Some(1),
                ..input("main")
            },
        )
        .expect("second page should succeed");
        assert_eq!(second.hits.len(), 1);

        connection
            .execute(
                "UPDATE repository SET snapshot_id = 'snapshot-new', indexed_at = 2",
                [],
            )
            .expect("update snapshot");
        let stale = search_repo(
            &connection,
            std::path::Path::new("."),
            RepoSearchInput {
                cursor: Some(cursor),
                ..input("main")
            },
        )
        .expect_err("stale cursor should fail");
        assert!(stale.contains("stale cursor"));
    }

    #[test]
    fn minified_single_line_assets_have_bounded_excerpts() {
        let connection = setup();
        let huge_svg = format!("<svg>{}</svg>", "x".repeat(20_000));
        insert_file(
            &connection,
            "frontend/public/huge.svg",
            false,
            "frontend huge svg",
            &huge_svg,
        );

        let result = search_repo(&connection, std::path::Path::new("."), input("frontend"))
            .expect("path search should succeed");
        let hit = result
            .hits
            .iter()
            .find(|hit| hit.path.ends_with("huge.svg"))
            .expect("asset hit");
        assert!(hit.excerpt.chars().count() <= MAX_EXCERPT_CHARS);
        assert!(hit.excerpt.ends_with("... excerpt truncated"));
    }
}
