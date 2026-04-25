-- Software State Model Database Schema
-- SQLite storage for code intelligence

-- Snapshots track different states of the codebase
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id TEXT UNIQUE NOT NULL,
    repo_path TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    file_count INTEGER DEFAULT 0,
    symbol_count INTEGER DEFAULT 0,
    import_count INTEGER DEFAULT 0,
    call_edge_count INTEGER DEFAULT 0,
    test_mapping_count INTEGER DEFAULT 0,
    
    languages TEXT,
    is_current BOOLEAN DEFAULT 1,
    parent_snapshot_id TEXT,
    
    FOREIGN KEY (parent_snapshot_id) REFERENCES snapshots(snapshot_id)
);

CREATE INDEX IF NOT EXISTS idx_snapshots_repo ON snapshots(repo_path);
CREATE INDEX IF NOT EXISTS idx_snapshots_current ON snapshots(is_current, repo_path);

-- Files table
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_snapshot_id TEXT NOT NULL,
    path TEXT NOT NULL,
    hash TEXT NOT NULL,
    language TEXT,
    line_count INTEGER DEFAULT 0,
    last_modified TIMESTAMP,
    size_bytes INTEGER DEFAULT 0,
    
    imports TEXT,
    exports TEXT,
    symbols TEXT,
    
    FOREIGN KEY (repo_snapshot_id) REFERENCES snapshots(snapshot_id)
);

CREATE INDEX IF NOT EXISTS idx_files_snapshot ON files(repo_snapshot_id);
CREATE INDEX IF NOT EXISTS idx_files_path ON files(path);
CREATE INDEX IF NOT EXISTS idx_files_language ON files(language);

-- Symbols table
CREATE TABLE IF NOT EXISTS symbols (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_snapshot_id TEXT NOT NULL,
    file_id INTEGER NOT NULL,
    
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    visibility TEXT DEFAULT 'public',
    
    file_path TEXT NOT NULL,
    line_start INTEGER,
    line_end INTEGER,
    
    signature TEXT,
    docstring TEXT,
    
    bases TEXT,
    decorators TEXT,
    module_path TEXT,
    qualified_name TEXT,
    
    is_async BOOLEAN DEFAULT 0,
    is_override BOOLEAN DEFAULT 0,
    is_test BOOLEAN DEFAULT 0,
    
    FOREIGN KEY (repo_snapshot_id) REFERENCES snapshots(snapshot_id),
    FOREIGN KEY (file_id) REFERENCES files(id)
);

CREATE INDEX IF NOT EXISTS idx_symbols_snapshot ON symbols(repo_snapshot_id);
CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);
CREATE INDEX IF NOT EXISTS idx_symbols_qualified ON symbols(qualified_name);
CREATE INDEX IF NOT EXISTS idx_symbols_file ON symbols(file_path);
CREATE INDEX IF NOT EXISTS idx_symbols_kind ON symbols(kind);

-- Imports table
CREATE TABLE IF NOT EXISTS imports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_snapshot_id TEXT NOT NULL,
    file_id INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    
    module_path TEXT NOT NULL,
    imported_names TEXT,
    alias TEXT,
    
    is_wildcard BOOLEAN DEFAULT 0,
    is_relative BOOLEAN DEFAULT 0,
    level INTEGER DEFAULT 0,
    
    line INTEGER,
    
    FOREIGN KEY (repo_snapshot_id) REFERENCES snapshots(snapshot_id),
    FOREIGN KEY (file_id) REFERENCES files(id)
);

CREATE INDEX IF NOT EXISTS idx_imports_snapshot ON imports(repo_snapshot_id);
CREATE INDEX IF NOT EXISTS idx_imports_module ON imports(module_path);
CREATE INDEX IF NOT EXISTS idx_imports_file ON imports(file_path);

-- Call graph edges
CREATE TABLE IF NOT EXISTS calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_snapshot_id TEXT NOT NULL,
    
    caller_id INTEGER NOT NULL,
    caller_name TEXT NOT NULL,
    caller_path TEXT NOT NULL,
    
    callee_id INTEGER NOT NULL,
    callee_name TEXT NOT NULL,
    callee_path TEXT NOT NULL,
    
    call_type TEXT DEFAULT 'direct',
    line INTEGER,
    
    FOREIGN KEY (repo_snapshot_id) REFERENCES snapshots(snapshot_id)
);

CREATE INDEX IF NOT EXISTS idx_calls_snapshot ON calls(repo_snapshot_id);
CREATE INDEX IF NOT EXISTS idx_calls_caller ON calls(caller_name, caller_path);
CREATE INDEX IF NOT EXISTS idx_calls_callee ON calls(callee_name, callee_path);

-- Test mappings
CREATE TABLE IF NOT EXISTS test_mappings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_snapshot_id TEXT NOT NULL,
    
    test_file_path TEXT NOT NULL,
    test_name TEXT NOT NULL,
    
    target_symbol_id INTEGER,
    target_symbol_name TEXT,
    target_file_path TEXT,
    
    mapping_method TEXT DEFAULT 'naming',
    confidence REAL DEFAULT 0.0,
    
    related_symbols TEXT,
    
    FOREIGN KEY (repo_snapshot_id) REFERENCES snapshots(snapshot_id)
);

CREATE INDEX IF NOT EXISTS idx_tests_snapshot ON test_mappings(repo_snapshot_id);
CREATE INDEX IF NOT EXISTS idx_tests_target ON test_mappings(target_symbol_name, target_file_path);
CREATE INDEX IF NOT EXISTS idx_tests_test ON test_mappings(test_name, test_file_path);

-- Dependencies
CREATE TABLE IF NOT EXISTS dependencies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_snapshot_id TEXT NOT NULL,
    
    package_manager TEXT NOT NULL,
    package_name TEXT NOT NULL,
    version_spec TEXT,
    installed_version TEXT,
    latest_version TEXT,
    
    is_dev BOOLEAN DEFAULT 0,
    is_optional BOOLEAN DEFAULT 0,
    
    file_path TEXT,
    
    has_vulnerabilities BOOLEAN DEFAULT 0,
    vulnerabilities TEXT,
    
    FOREIGN KEY (repo_snapshot_id) REFERENCES snapshots(snapshot_id)
);

CREATE INDEX IF NOT EXISTS idx_deps_snapshot ON dependencies(repo_snapshot_id);
CREATE INDEX IF NOT EXISTS idx_deps_name ON dependencies(package_name);
