use std::fmt::Write as _;
use std::path::{Path, PathBuf};

use sha2::{Digest, Sha256};

pub fn index_path_for_workspace(workspace_root: &Path) -> Result<PathBuf, String> {
    let cache_root = platform_cache_root()?;
    let root_hash = stable_hash_hex(&workspace_root.display().to_string());
    let index_dir = cache_root.join("repo-index").join(root_hash);
    std::fs::create_dir_all(&index_dir)
        .map_err(|error| format!("failed to create repo index cache directory: {error}"))?;
    Ok(index_dir.join("index.sqlite"))
}

fn platform_cache_root() -> Result<PathBuf, String> {
    #[cfg(windows)]
    {
        if let Some(local_app_data) = std::env::var_os("LOCALAPPDATA") {
            return Ok(PathBuf::from(local_app_data).join("ClawCodex"));
        }
    }

    if let Some(xdg_cache) = std::env::var_os("XDG_CACHE_HOME") {
        return Ok(PathBuf::from(xdg_cache).join("clawcodex"));
    }
    if let Some(home) = std::env::var_os("HOME") {
        return Ok(PathBuf::from(home).join(".cache").join("clawcodex"));
    }
    Err("could not resolve user cache directory for repository index".to_string())
}

fn stable_hash_hex(input: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(input.as_bytes());
    let digest = hasher.finalize();
    let mut out = String::with_capacity(digest.len() * 2);
    for byte in digest {
        write!(out, "{byte:02x}").expect("writing to a String cannot fail");
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn different_workspaces_use_external_distinct_indexes() {
        let left = std::env::temp_dir().join("clawcodex-cache-left");
        let right = std::env::temp_dir().join("clawcodex-cache-right");
        let left_index = index_path_for_workspace(&left).expect("left index path");
        let right_index = index_path_for_workspace(&right).expect("right index path");

        assert_ne!(left_index, right_index);
        assert!(!left_index.starts_with(&left));
        assert!(!right_index.starts_with(&right));
        assert_eq!(
            left_index.file_name().and_then(|value| value.to_str()),
            Some("index.sqlite")
        );
    }
}
