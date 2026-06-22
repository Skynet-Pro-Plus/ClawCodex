"""Filesystem-backed attachment storage with SQLite metadata."""

from __future__ import annotations

import hashlib
import shutil
import uuid
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import BinaryIO

from ..orchestrator.store import OrchestratorStore, get_store, utc_now
from .analyzer import analyze_attachment

ALLOWED_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp",
    ".txt", ".md", ".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".toml", ".yaml", ".yml", ".css", ".html",
    ".pdf", ".csv", ".log",
}
MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024


@dataclass
class AttachmentRecord:
    id: str
    task_id: str | None
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    path: str
    preview_url: str
    analysis_status: str = "ready"
    analysis: dict = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict:
        return asdict(self)


class AttachmentStore:
    def __init__(self, store: OrchestratorStore | None = None, root: str | Path | None = None):
        self.store = store or get_store()
        self.root = Path(root) if root else Path.cwd() / ".claw" / "attachments"
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, fileobj: BinaryIO, filename: str, content_type: str, task_id: str | None = None) -> AttachmentRecord:
        suffix = Path(filename).suffix.lower()
        if suffix and suffix not in ALLOWED_EXTENSIONS:
            raise ValueError(f"attachment type not allowed: {suffix}")
        attachment_id = uuid.uuid4().hex
        bucket = task_id or "pending"
        target_dir = self.root / bucket
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{attachment_id}{suffix}"
        hasher = hashlib.sha256()
        size = 0
        with target.open("wb") as output:
            while True:
                chunk = fileobj.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_ATTACHMENT_BYTES:
                    output.close()
                    target.unlink(missing_ok=True)
                    raise ValueError("attachment exceeds 25MB limit")
                hasher.update(chunk)
                output.write(chunk)
        analysis = analyze_attachment(target, content_type)
        record = AttachmentRecord(
            id=attachment_id,
            task_id=task_id,
            filename=filename,
            content_type=content_type or "application/octet-stream",
            size_bytes=size,
            sha256=hasher.hexdigest(),
            path=str(target),
            preview_url=f"/api/attachments/{attachment_id}/content",
            analysis=analysis,
        )
        self.store.insert_attachment(record.to_dict())
        return record

    def get(self, attachment_id: str) -> AttachmentRecord | None:
        data = self.store.get_attachment(attachment_id)
        return AttachmentRecord(**data) if data else None

    def list_for_task(self, task_id: str) -> list[AttachmentRecord]:
        return [AttachmentRecord(**item) for item in self.store.list_attachments(task_id)]

    def link_to_task(self, task_id: str, attachment_id: str) -> AttachmentRecord:
        record = self.get(attachment_id)
        if record is None:
            raise KeyError(f"attachment not found: {attachment_id}")
        old_path = Path(record.path)
        target_dir = self.root / task_id
        target_dir.mkdir(parents=True, exist_ok=True)
        new_path = target_dir / old_path.name
        if old_path.resolve() != new_path.resolve():
            shutil.move(str(old_path), str(new_path))
        record.task_id = task_id
        record.path = str(new_path)
        self.store.update_attachment_task(attachment_id, task_id, str(new_path))
        return record

    def delete(self, attachment_id: str) -> bool:
        record = self.get(attachment_id)
        if record is None:
            return False
        Path(record.path).unlink(missing_ok=True)
        self.store.delete_attachment(attachment_id)
        return True
