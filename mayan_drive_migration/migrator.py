from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from .config import Settings
from .drive_client import DriveClient
from .filename_parser import parse_filename
from .manifest import FAILED, SKIPPED, UPLOADED, Manifest, ManifestItem


LOGGER = logging.getLogger(__name__)


class DriveLike(Protocol):
    def scan_folder(self, root_folder_id: str) -> list[dict]:
        ...

    def download_file(self, file_record: dict, destination_dir: Path) -> Path:
        ...


class MayanLike(Protocol):
    def get_or_create_cabinet(self, path: str) -> int:
        ...

    def create_document(self, label: str, document_type_id: int) -> int:
        ...

    def upload_file(self, document_id: int, file_path: Path) -> None:
        ...

    def attach_document_to_cabinet(self, document_id: int, cabinet_id: int) -> None:
        ...

    def set_metadata(self, document_id: int, metadata: dict) -> None:
        ...

    def add_tags(self, document_id: int, tags: list[str]) -> None:
        ...


class Migrator:
    def __init__(
        self,
        settings: Settings,
        drive_client: DriveLike | None = None,
        mayan_client: MayanLike | None = None,
    ) -> None:
        self.settings = settings
        self.drive_client = drive_client or DriveClient(
            settings.google_service_account_file,
            settings.workspace_export_mode,
        )
        self.mayan_client = mayan_client

    def scan(self) -> Manifest:
        files = self.drive_client.scan_folder(self.settings.google_drive_root_folder_id)
        manifest = Manifest.load(self.settings.manifest_path)
        manifest.upsert_discovered(files)
        manifest.save()
        LOGGER.info("Scanned %s files into %s", len(files), self.settings.manifest_path)
        return manifest

    def migrate(self, *, dry_run: bool = False, force: bool = False, retry_failed: bool = False) -> Manifest:
        manifest = Manifest.load(self.settings.manifest_path)
        if not manifest.items:
            manifest = self.scan()

        effective_dry_run = dry_run or self.settings.dry_run
        mayan = self.mayan_client
        if mayan is None and not effective_dry_run:
            from .mayan_client import MayanClient

            mayan = MayanClient(self.settings)

        file_records = {
            record["file_id"]: record
            for record in self.drive_client.scan_folder(self.settings.google_drive_root_folder_id)
        }

        for item in manifest.pending_items(force=force, retry_failed=retry_failed):
            record = file_records.get(item.google_file_id)
            if not record:
                self._mark_failed(item, "File no longer found in Google Drive")
                manifest.save()
                continue
            self._prepare_item(item, record)
            if effective_dry_run:
                item.status = SKIPPED
                item.error_message = "Dry run: no Mayan upload performed"
                item.touch()
                manifest.save()
                continue
            assert mayan is not None
            self._migrate_one(item, record, mayan)
            manifest.save()
        return manifest

    def _migrate_one(self, item: ManifestItem, record: dict, mayan: MayanLike) -> None:
        temp_path: Path | None = None
        try:
            LOGGER.info("Migrating %s (%s)", item.source_path, item.google_file_id)
            document_id = item.mayan_document_id
            cabinet_id = mayan.get_or_create_cabinet(item.target_cabinet_path)
            should_upload_file = document_id is None or _failed_during_file_upload(item.error_message)
            if should_upload_file:
                temp_path = self.drive_client.download_file(record, self.settings.download_temp_dir)
            if document_id is None:
                document_id = mayan.create_document(
                    item.metadata.get("title") or record["name"],
                    self.settings.mayan_default_document_type_id,
                )
                item.mayan_document_id = document_id
            if should_upload_file:
                mayan.upload_file(document_id, temp_path)
            mayan.attach_document_to_cabinet(document_id, cabinet_id)

            metadata_error = ""
            try:
                mayan.set_metadata(document_id, self._mayan_metadata(item.metadata))
                mayan.add_tags(document_id, build_tags(item.target_cabinet_path, item.metadata, self.settings.tag_keyword_limit))
            except Exception as exc:  # Metadata failures preserve the uploaded document ID.
                metadata_error = f"Uploaded, but metadata/tagging failed: {exc}"
                LOGGER.exception(metadata_error)

            if metadata_error:
                self._mark_failed(item, metadata_error)
            else:
                item.status = UPLOADED
                item.error_message = ""
                item.touch()
        except Exception as exc:
            self._mark_failed(item, str(exc))
            LOGGER.exception("Failed migrating %s (%s)", item.source_path, item.google_file_id)
        finally:
            if temp_path and temp_path.exists():
                temp_path.unlink()

    def _prepare_item(self, item: ManifestItem, record: dict) -> None:
        parsed = parse_filename(record["name"])
        now = datetime.now(timezone.utc).isoformat()
        item.metadata.update(parsed)
        item.metadata.update(
            {
                "google_file_id": record["file_id"],
                "google_drive_full_path": record["full_path"],
                "google_modified_time": record.get("modified_time", ""),
                "google_mime_type": record.get("mime_type", ""),
                "migration_timestamp": now,
                "source": "Google Drive",
            }
        )
        item.source_path = record["full_path"]
        item.target_cabinet_path = record["parent_path"]
        item.touch()

    def _mayan_metadata(self, metadata: dict) -> dict[str, str]:
        return {
            self.settings.metadata_labels.get(key, key): value
            for key, value in metadata.items()
            if value not in (None, "")
        }

    def _mark_failed(self, item: ManifestItem, message: str) -> None:
        item.status = FAILED
        item.error_message = message
        item.retry_count += 1
        item.touch()


def build_tags(cabinet_path: str, metadata: dict, keyword_limit: int = 5) -> list[str]:
    tags: list[str] = []
    tags.extend(part.strip() for part in cabinet_path.replace("\\", "/").split("/") if part.strip())
    for key in ("language", "version", "document_stage"):
        if metadata.get(key):
            tags.append(str(metadata[key]))
    tags.extend(_title_keywords(str(metadata.get("title", "")), keyword_limit))
    return _dedupe([_safe_tag(tag) for tag in tags if _safe_tag(tag)])


def _title_keywords(title: str, limit: int) -> list[str]:
    stop_words = {"a", "an", "and", "at", "for", "in", "of", "or", "the", "to", "while", "with"}
    words = re.findall(r"[A-Za-z0-9]+", title)
    return [word for word in words if len(word) > 2 and word.lower() not in stop_words][:limit]


def _safe_tag(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()[:96]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.lower()
        if key not in seen:
            result.append(value)
            seen.add(key)
    return result


def _failed_during_file_upload(error_message: str) -> bool:
    lowered = error_message.lower()
    return "/files/" in lowered or "file_new" in lowered or "submitted file is empty" in lowered
