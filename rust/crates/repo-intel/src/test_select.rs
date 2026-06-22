use std::collections::{BTreeMap, BTreeSet};

use rusqlite::Connection;
use serde::Serialize;

#[derive(Debug, Clone, Serialize)]
pub struct RepoImpactResult {
    pub changed_paths: Vec<String>,
    pub related_paths: Vec<ImpactPath>,
    pub likely_tests: Vec<SelectedTest>,
    pub confidence: String,
    pub reasons: Vec<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct ImpactPath {
    pub path: String,
    pub reason: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct RepoTestsResult {
    pub changed_paths: Vec<String>,
    pub selected_tests: Vec<SelectedTest>,
    pub fallback_command: String,
    pub confidence: String,
    pub reasons: Vec<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct SelectedTest {
    pub path: String,
    pub reason: String,
    pub confidence: String,
}

pub fn build_impact_report(
    connection: &Connection,
    changed_paths: Vec<String>,
) -> Result<RepoImpactResult, String> {
    let related_paths = find_related_paths(connection, &changed_paths)?;
    let tests = select_tests(connection, changed_paths.clone())?;
    Ok(RepoImpactResult {
        changed_paths,
        related_paths,
        likely_tests: tests.selected_tests,
        confidence: tests.confidence,
        reasons: tests.reasons,
    })
}

pub fn select_tests(
    connection: &Connection,
    changed_paths: Vec<String>,
) -> Result<RepoTestsResult, String> {
    let mut selected: BTreeMap<String, SelectedTest> = BTreeMap::new();
    let mut reasons = Vec::new();
    for changed_path in &changed_paths {
        if is_test_path(changed_path) {
            upsert_selected_test(
                &mut selected,
                changed_path.clone(),
                "changed-file-is-test".to_string(),
                "high",
            );
            continue;
        }

        for test in select_by_explicit_edges(connection, changed_path)? {
            upsert_selected_test(&mut selected, test.path, test.reason, &test.confidence);
        }

        for test in select_by_same_module_patterns(connection, changed_path)? {
            upsert_selected_test(&mut selected, test.path, test.reason, &test.confidence);
        }

        for test in select_by_nearby_tests(connection, changed_path)? {
            upsert_selected_test(&mut selected, test.path, test.reason, &test.confidence);
        }

        for test in select_by_name_similarity(connection, changed_path)? {
            upsert_selected_test(&mut selected, test.path, test.reason, &test.confidence);
        }
    }

    let fallback_command = infer_fallback_command(connection)?;
    let tests = selected.into_values().collect::<Vec<_>>();
    let confidence = if tests.iter().any(|item| item.confidence == "high") {
        "high"
    } else if tests.iter().any(|item| item.confidence == "medium") {
        "medium"
    } else {
        "low"
    }
    .to_string();
    if tests.is_empty() {
        reasons.push("no direct tests found; use configured integration gate".to_string());
    } else {
        reasons.push(
            "selected tests using explicit edges, module patterns, and proximity".to_string(),
        );
    }
    Ok(RepoTestsResult {
        changed_paths,
        selected_tests: tests,
        fallback_command,
        confidence,
        reasons,
    })
}

fn find_related_paths(
    connection: &Connection,
    changed_paths: &[String],
) -> Result<Vec<ImpactPath>, String> {
    let mut out = Vec::new();
    let mut seen = BTreeSet::new();
    for changed_path in changed_paths {
        let prefix = changed_path
            .rsplit_once('/')
            .map(|(dir, _)| dir.to_string())
            .unwrap_or_default();
        let query = if prefix.is_empty() {
            "%".to_string()
        } else {
            format!("{prefix}/%")
        };
        let mut statement = connection
            .prepare("SELECT path FROM files WHERE path LIKE ?1 ORDER BY path ASC LIMIT 8")
            .map_err(|error| format!("failed preparing impact neighbor query: {error}"))?;
        let rows = statement
            .query_map([query], |row| row.get::<_, String>(0))
            .map_err(|error| format!("failed executing impact neighbor query: {error}"))?;
        for row in rows {
            let path =
                row.map_err(|error| format!("failed decoding impact neighbor row: {error}"))?;
            if path == *changed_path {
                continue;
            }
            if seen.insert(path.clone()) {
                out.push(ImpactPath {
                    path,
                    reason: format!("same-directory-as:{changed_path}"),
                });
            }
        }
    }
    Ok(out)
}

fn infer_fallback_command(connection: &Connection) -> Result<String, String> {
    let mut statement = connection
        .prepare(
            "SELECT path FROM files WHERE path = 'Cargo.toml' OR path LIKE '%/Cargo.toml' LIMIT 1",
        )
        .map_err(|error| format!("failed preparing Cargo fallback query: {error}"))?;
    let has_cargo = statement.exists([]).map_err(|error| error.to_string())?;
    if has_cargo {
        return Ok("cargo test --workspace".to_string());
    }
    let mut statement = connection
        .prepare("SELECT path FROM files WHERE path = 'package.json' OR path LIKE '%/package.json' LIMIT 1")
        .map_err(|error| format!("failed preparing npm fallback query: {error}"))?;
    let has_npm = statement.exists([]).map_err(|error| error.to_string())?;
    if has_npm {
        return Ok("npm test".to_string());
    }
    let mut statement = connection
        .prepare("SELECT path FROM files WHERE path = 'pyproject.toml' OR path LIKE '%/pyproject.toml' LIMIT 1")
        .map_err(|error| format!("failed preparing pytest fallback query: {error}"))?;
    let has_pytest = statement.exists([]).map_err(|error| error.to_string())?;
    if has_pytest {
        return Ok("pytest".to_string());
    }
    Ok("run configured completion verification command".to_string())
}

fn select_by_explicit_edges(
    connection: &Connection,
    changed_path: &str,
) -> Result<Vec<SelectedTest>, String> {
    let mut statement = connection
        .prepare(
            "SELECT test_path, reason, confidence
             FROM test_edges
             WHERE source_path = ?1
             ORDER BY confidence DESC, test_path ASC
             LIMIT 20",
        )
        .map_err(|error| format!("failed preparing explicit-edge query: {error}"))?;
    let rows = statement
        .query_map([changed_path], |row| {
            Ok(SelectedTest {
                path: row.get::<_, String>(0)?,
                reason: row.get::<_, String>(1)?,
                confidence: normalize_confidence(&row.get::<_, String>(2)?).to_string(),
            })
        })
        .map_err(|error| format!("failed executing explicit-edge query: {error}"))?;
    rows.into_iter()
        .map(|row| row.map_err(|error| format!("failed decoding explicit-edge row: {error}")))
        .collect()
}

fn select_by_same_module_patterns(
    connection: &Connection,
    changed_path: &str,
) -> Result<Vec<SelectedTest>, String> {
    let mut patterns = Vec::new();
    let prefix = changed_path
        .rsplit_once('/')
        .map(|(dir, _)| dir.to_string())
        .unwrap_or_default();

    if prefix.is_empty() {
        patterns.push("tests/%".to_string());
    } else {
        patterns.push(format!("{prefix}/tests/%"));
    }

    if let Some((left, right)) = changed_path.split_once("/src/") {
        patterns.push(format!("{left}/tests/{right}%"));
    }

    select_tests_by_patterns(
        connection,
        &patterns,
        changed_path,
        "same-module-pattern",
        "medium",
        12,
    )
}

fn select_by_nearby_tests(
    connection: &Connection,
    changed_path: &str,
) -> Result<Vec<SelectedTest>, String> {
    let prefix = changed_path
        .rsplit_once('/')
        .map(|(dir, _)| dir.to_string())
        .unwrap_or_default();
    let path_pattern = if prefix.is_empty() {
        "tests/%".to_string()
    } else {
        format!("{prefix}/tests/%")
    };
    select_tests_by_patterns(
        connection,
        &[path_pattern],
        changed_path,
        "nearby-test",
        "medium",
        8,
    )
}

fn select_by_name_similarity(
    connection: &Connection,
    changed_path: &str,
) -> Result<Vec<SelectedTest>, String> {
    let file_name = changed_path
        .rsplit_once('/')
        .map_or(changed_path, |(_, file)| file);
    let stem = file_name.split('.').next().unwrap_or(file_name);
    if stem.len() < 3 {
        return Ok(Vec::new());
    }
    let patterns = vec![format!("%{stem}%")];
    select_tests_by_patterns(
        connection,
        &patterns,
        changed_path,
        "name-similarity",
        "low",
        4,
    )
}

fn select_tests_by_patterns(
    connection: &Connection,
    patterns: &[String],
    changed_path: &str,
    reason_prefix: &str,
    confidence: &str,
    per_pattern_limit: usize,
) -> Result<Vec<SelectedTest>, String> {
    let mut tests = Vec::new();
    for pattern in patterns {
        let mut statement = connection
            .prepare(
                "SELECT path FROM files
                 WHERE is_test = 1 AND path LIKE ?1
                 ORDER BY path ASC
                 LIMIT ?2",
            )
            .map_err(|error| format!("failed preparing test-pattern query: {error}"))?;
        let limit = i64::try_from(per_pattern_limit).unwrap_or(i64::MAX);
        let rows = statement
            .query_map((pattern, limit), |row| row.get::<_, String>(0))
            .map_err(|error| format!("failed executing test-pattern query: {error}"))?;
        for row in rows {
            let path = row.map_err(|error| format!("failed decoding test-pattern row: {error}"))?;
            tests.push(SelectedTest {
                path,
                reason: format!("{reason_prefix}-for:{changed_path}"),
                confidence: confidence.to_string(),
            });
        }
    }
    Ok(tests)
}

fn upsert_selected_test(
    selected: &mut BTreeMap<String, SelectedTest>,
    path: String,
    reason: String,
    confidence: &str,
) {
    let normalized_confidence = normalize_confidence(confidence).to_string();
    match selected.get_mut(&path) {
        Some(existing) => {
            let incoming_rank = confidence_rank(&normalized_confidence);
            let existing_rank = confidence_rank(&existing.confidence);
            if incoming_rank > existing_rank {
                existing.confidence = normalized_confidence;
                existing.reason = reason;
            } else if incoming_rank == existing_rank && reason < existing.reason {
                existing.reason = reason;
            }
        }
        None => {
            selected.insert(
                path.clone(),
                SelectedTest {
                    path,
                    reason,
                    confidence: normalized_confidence,
                },
            );
        }
    }
}

fn normalize_confidence(value: &str) -> &str {
    match value.to_ascii_lowercase().as_str() {
        "high" => "high",
        "medium" => "medium",
        _ => "low",
    }
}

fn confidence_rank(value: &str) -> i8 {
    match normalize_confidence(value) {
        "high" => 3,
        "medium" => 2,
        _ => 1,
    }
}

fn is_test_path(path: &str) -> bool {
    let lower = path.to_ascii_lowercase();
    lower.starts_with("tests/")
        || lower.contains("/tests/")
        || lower.ends_with("_test.rs")
        || lower.ends_with("_test.py")
        || lower.ends_with("_test.ts")
        || lower.ends_with("_test.js")
        || lower.ends_with(".spec.ts")
        || lower.ends_with(".spec.js")
        || lower.ends_with(".test.ts")
        || lower.ends_with(".test.js")
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::schema::ensure_schema;

    fn in_memory_conn() -> Connection {
        let mut connection = Connection::open_in_memory().expect("in-memory sqlite");
        ensure_schema(&mut connection).expect("schema");
        connection
    }

    #[test]
    fn select_tests_prefers_explicit_edges_as_high_confidence() {
        let connection = in_memory_conn();
        connection
            .execute(
                "INSERT INTO files(path, language, size, mtime_ns, content_hash, line_count, is_test)
                 VALUES ('src/lib.rs','Rust',10,1,'a',1,0), ('tests/lib_test.rs','Rust',10,1,'b',1,1)",
                [],
            )
            .expect("seed files");
        connection
            .execute(
                "INSERT INTO test_edges(source_path, test_path, reason, confidence)
                 VALUES ('src/lib.rs','tests/lib_test.rs','manifest-mapping','high')",
                [],
            )
            .expect("seed edges");
        let result =
            select_tests(&connection, vec!["src/lib.rs".to_string()]).expect("select tests");
        assert_eq!(result.selected_tests.len(), 1);
        assert_eq!(result.selected_tests[0].path, "tests/lib_test.rs");
        assert_eq!(result.selected_tests[0].confidence, "high");
        assert_eq!(result.confidence, "high");
    }

    #[test]
    fn select_tests_returns_low_confidence_when_only_name_heuristic_matches() {
        let connection = in_memory_conn();
        connection
            .execute(
                "INSERT INTO files(path, language, size, mtime_ns, content_hash, line_count, is_test)
                 VALUES ('src/payments/payment_service.rs','Rust',10,1,'a',1,0), ('qa/payment_service_smoke.spec.ts','TypeScript',10,1,'b',1,1)",
                [],
            )
            .expect("seed files");
        let result = select_tests(
            &connection,
            vec!["src/payments/payment_service.rs".to_string()],
        )
        .expect("select tests");
        assert_eq!(result.selected_tests.len(), 1);
        assert_eq!(result.selected_tests[0].confidence, "low");
        assert_eq!(result.confidence, "low");
    }
}
