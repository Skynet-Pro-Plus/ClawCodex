pub fn detect_language(path: &str) -> &'static str {
    let extension = std::path::Path::new(path)
        .extension()
        .map(|value| value.to_string_lossy().to_ascii_lowercase());
    match extension.as_deref() {
        Some("rs") => "rust",
        Some("py") => "python",
        Some("ts" | "tsx") => "typescript",
        Some("js" | "jsx") => "javascript",
        Some("c" | "h") => "c",
        Some("cc" | "cpp" | "hpp") => "cpp",
        Some("cs") => "csharp",
        Some("java") => "java",
        Some("go") => "go",
        Some("toml") => "toml",
        Some("yaml" | "yml") => "yaml",
        Some("json") => "json",
        Some("md") => "markdown",
        Some("sh") => "shell",
        Some("ps1" | "bat") => "powershell",
        _ => "text",
    }
}

pub fn is_test_path(path: &str) -> bool {
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
    use super::{detect_language, is_test_path};

    #[test]
    fn detects_common_languages() {
        assert_eq!(detect_language("src/main.rs"), "rust");
        assert_eq!(detect_language("pkg/module.py"), "python");
        assert_eq!(detect_language("frontend/app.tsx"), "typescript");
        assert_eq!(detect_language("scripts/build.ps1"), "powershell");
        assert_eq!(detect_language("README.unknown"), "text");
    }

    #[test]
    fn detects_test_paths() {
        assert!(is_test_path("tests/unit/test_api.py"));
        assert!(is_test_path("pkg/src/foo_test.rs"));
        assert!(is_test_path("web/src/app.spec.ts"));
        assert!(!is_test_path("src/main.rs"));
    }
}
