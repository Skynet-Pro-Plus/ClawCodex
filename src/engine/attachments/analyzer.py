"""Lightweight attachment analysis used before model-level understanding."""

from __future__ import annotations

from pathlib import Path
from typing import Any


TEXT_EXTENSIONS = {".txt", ".md", ".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".toml", ".yaml", ".yml", ".css", ".html"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}


def analyze_attachment(path: str | Path, content_type: str) -> dict[str, Any]:
    target = Path(path)
    suffix = target.suffix.lower()
    if content_type.startswith("image/") or suffix in IMAGE_EXTENSIONS:
        return {
            "kind": "image",
            "filename": target.name,
            "note": "Image is ready for multimodal model analysis.",
            "ocr_status": "not_run",
        }
    if content_type.startswith("text/") or suffix in TEXT_EXTENSIONS:
        text = target.read_text(encoding="utf-8", errors="ignore")
        return {
            "kind": "text",
            "filename": target.name,
            "line_count": len(text.splitlines()),
            "preview": text[:4000],
        }
    return {
        "kind": "binary",
        "filename": target.name,
        "note": "Stored as binary metadata; no text preview available.",
    }
