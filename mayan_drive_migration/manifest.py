from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


PENDING = "pending"
UPLOADED = "uploaded"
FAILED = "failed"
SKIPPED = "skipped"


@dataclass
class ManifestItem:
    status: str
    google_file_id: str
    source_path: str
    target_cabinet_path: str
    metadata: dict[str, Any] = field(default_factory=dict)
    mayan_document_id: int | None = None
    error_message: str = ""
    retry_count: int = 0
    discovered_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ManifestItem":
        return cls(
            status=data.get("status", PENDING),
            google_file_id=str(data["google_file_id"]),
            source_path=data["source_path"],
            target_cabinet_path=data.get("target_cabinet_path", ""),
            metadata=data.get("metadata", {}),
            mayan_document_id=data.get("mayan_document_id"),
            error_message=data.get("error_message", ""),
            retry_count=int(data.get("retry_count", 0)),
            discovered_at=data.get("discovered_at", datetime.now(timezone.utc).isoformat()),
            updated_at=data.get("updated_at", datetime.now(timezone.utc).isoformat()),
        )

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc).isoformat()


class Manifest:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.items: dict[str, ManifestItem] = {}

    @classmethod
    def load(cls, path: Path) -> "Manifest":
        manifest = cls(path)
        if not path.exists():
            return manifest
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        records = data.get("items", data if isinstance(data, list) else [])
        for record in records:
            item = ManifestItem.from_dict(record)
            manifest.items[item.google_file_id] = item
        return manifest

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "items": [asdict(item) for item in self.items.values()],
        }
        self.path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def export_csv(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = [
            "status",
            "google_file_id",
            "source_path",
            "target_cabinet_path",
            "mayan_document_id",
            "error_message",
            "retry_count",
            "metadata",
        ]
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for item in self.items.values():
                row = asdict(item)
                row["metadata"] = json.dumps(item.metadata, ensure_ascii=False)
                writer.writerow({field: row.get(field, "") for field in fieldnames})

    def upsert_discovered(self, discovered_files: Iterable[dict[str, Any]]) -> None:
        for file_record in discovered_files:
            google_file_id = str(file_record["file_id"])
            source_path = file_record["full_path"]
            target_cabinet_path = file_record["parent_path"]
            existing = self.items.get(google_file_id)
            if existing:
                existing.source_path = source_path
                existing.target_cabinet_path = target_cabinet_path
                existing.metadata.update(_google_metadata(file_record))
                existing.touch()
                continue
            self.items[google_file_id] = ManifestItem(
                status=PENDING,
                google_file_id=google_file_id,
                source_path=source_path,
                target_cabinet_path=target_cabinet_path,
                metadata=_google_metadata(file_record),
            )

    def pending_items(self, *, force: bool = False, retry_failed: bool = False) -> list[ManifestItem]:
        if force:
            return list(self.items.values())
        statuses = {PENDING, SKIPPED}
        if retry_failed:
            statuses.add(FAILED)
        return [item for item in self.items.values() if item.status in statuses]


def _google_metadata(file_record: dict[str, Any]) -> dict[str, Any]:
    return {
        "google_file_id": file_record.get("file_id", ""),
        "google_drive_full_path": file_record.get("full_path", ""),
        "google_modified_time": file_record.get("modified_time", ""),
        "google_mime_type": file_record.get("mime_type", ""),
        "source": "Google Drive",
    }
