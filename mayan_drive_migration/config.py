from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


DEFAULT_METADATA_LABELS: dict[str, str] = {
    "content_code": "content_code",
    "channel_or_format": "channel_or_format",
    "language": "language",
    "section_code": "section_code",
    "version": "version",
    "document_stage": "document_stage",
    "title": "title",
    "original_filename": "original_filename",
    "google_file_id": "google_file_id",
    "google_drive_full_path": "google_drive_full_path",
    "google_modified_time": "google_modified_time",
    "google_mime_type": "google_mime_type",
    "migration_timestamp": "migration_timestamp",
    "source": "source",
}


@dataclass(frozen=True)
class Settings:
    google_service_account_file: Path
    google_drive_root_folder_id: str
    mayan_base_url: str
    mayan_api_token: str
    mayan_default_document_type_id: int
    manifest_path: Path
    download_temp_dir: Path
    dry_run: bool
    metadata_labels: dict[str, str] = field(default_factory=lambda: DEFAULT_METADATA_LABELS.copy())
    workspace_export_mode: str = "office"
    report_json_path: Path = Path("migration_report.json")
    report_csv_path: Path = Path("migration_report.csv")
    log_path: Path = Path("migration.log")
    request_timeout_seconds: int = 60
    retry_attempts: int = 3
    retry_min_seconds: float = 1.0
    retry_max_seconds: float = 10.0
    tag_keyword_limit: int = 5


def load_settings(env_file: str | Path | None = None) -> Settings:
    load_dotenv(dotenv_path=env_file)

    missing = [name for name in _required_names() if not os.getenv(name)]
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

    labels = DEFAULT_METADATA_LABELS.copy()
    labels.update(_load_json_env("MAYAN_METADATA_LABELS", {}))

    return Settings(
        google_service_account_file=Path(_env("GOOGLE_SERVICE_ACCOUNT_FILE")),
        google_drive_root_folder_id=_env("GOOGLE_DRIVE_ROOT_FOLDER_ID"),
        mayan_base_url=_env("MAYAN_BASE_URL").rstrip("/"),
        mayan_api_token=_env("MAYAN_API_TOKEN"),
        mayan_default_document_type_id=int(_env("MAYAN_DEFAULT_DOCUMENT_TYPE_ID")),
        manifest_path=Path(_env("MANIFEST_PATH")),
        download_temp_dir=Path(_env("DOWNLOAD_TEMP_DIR")),
        dry_run=_parse_bool(_env("DRY_RUN")),
        metadata_labels=labels,
        workspace_export_mode=os.getenv("WORKSPACE_EXPORT_MODE", "office").lower(),
        report_json_path=Path(os.getenv("REPORT_JSON_PATH", "migration_report.json")),
        report_csv_path=Path(os.getenv("REPORT_CSV_PATH", "migration_report.csv")),
        log_path=Path(os.getenv("LOG_PATH", "migration.log")),
        request_timeout_seconds=int(os.getenv("REQUEST_TIMEOUT_SECONDS", "60")),
        retry_attempts=int(os.getenv("RETRY_ATTEMPTS", "3")),
        retry_min_seconds=float(os.getenv("RETRY_MIN_SECONDS", "1")),
        retry_max_seconds=float(os.getenv("RETRY_MAX_SECONDS", "10")),
        tag_keyword_limit=int(os.getenv("TAG_KEYWORD_LIMIT", "5")),
    )


def _required_names() -> list[str]:
    return [
        "GOOGLE_SERVICE_ACCOUNT_FILE",
        "GOOGLE_DRIVE_ROOT_FOLDER_ID",
        "MAYAN_BASE_URL",
        "MAYAN_API_TOKEN",
        "MAYAN_DEFAULT_DOCUMENT_TYPE_ID",
        "MANIFEST_PATH",
        "DOWNLOAD_TEMP_DIR",
        "DRY_RUN",
    ]


def _env(name: str) -> str:
    value = os.getenv(name)
    if value is None:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _load_json_env(name: str, default: dict[str, Any]) -> dict[str, Any]:
    raw = os.getenv(name)
    if not raw:
        return default
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError(f"{name} must be a JSON object")
    return parsed
