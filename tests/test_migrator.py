from pathlib import Path

from mayan_drive_migration.config import Settings
from mayan_drive_migration.manifest import FAILED, SKIPPED, UPLOADED
from mayan_drive_migration.migrator import Migrator, build_tags


class FakeDrive:
    records = [
        {
            "file_id": "g1",
            "name": "isdr_wa_en_1f_v1- Base Doc - Identify Spurious Medicines.docx",
            "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "modified_time": "2026-01-01T00:00:00Z",
            "full_path": "Root/Base Documents/isdr_wa_en_1f_v1- Base Doc - Identify Spurious Medicines.docx",
            "parent_path": "Root/Base Documents",
        }
    ]

    def __init__(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path

    def scan_folder(self, root_folder_id: str) -> list[dict]:
        return self.records

    def download_file(self, file_record: dict, destination_dir: Path) -> Path:
        path = destination_dir / file_record["name"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"content")
        return path


class FakeMayan:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get_or_create_cabinet(self, path: str) -> int:
        self.calls.append("cabinet")
        return 10

    def create_document(self, label: str, document_type_id: int) -> int:
        self.calls.append("document")
        return 20

    def upload_file(self, document_id: int, file_path: Path) -> None:
        self.calls.append("upload")

    def attach_document_to_cabinet(self, document_id: int, cabinet_id: int) -> None:
        self.calls.append("attach")

    def set_metadata(self, document_id: int, metadata: dict) -> None:
        self.calls.append("metadata")

    def add_tags(self, document_id: int, tags: list[str]) -> None:
        self.calls.append("tags")


class MetadataFailOnceMayan(FakeMayan):
    def __init__(self) -> None:
        super().__init__()
        self.failed = False

    def set_metadata(self, document_id: int, metadata: dict) -> None:
        self.calls.append("metadata")
        if not self.failed:
            self.failed = True
            raise RuntimeError("metadata unavailable")


class UploadFailOnceMayan(FakeMayan):
    def __init__(self) -> None:
        super().__init__()
        self.failed = False

    def upload_file(self, document_id: int, file_path: Path) -> None:
        self.calls.append("upload")
        if not self.failed:
            self.failed = True
            raise RuntimeError('POST https://mayan.example.com/api/v4/documents/20/files/ returned 400: {"file_new":["The submitted file is empty."]}')


def test_build_tags() -> None:
    tags = build_tags(
        "Root/Base Documents",
        {"language": "en", "version": "v1", "document_stage": "Base Doc", "title": "Identify Spurious Medicines"},
        3,
    )

    assert tags == ["Root", "Base Documents", "en", "v1", "Base Doc", "Identify", "Spurious", "Medicines"]


def test_dry_run_does_not_call_mayan(tmp_path) -> None:
    settings = _settings(tmp_path, dry_run=False)
    mayan = FakeMayan()
    migrator = Migrator(settings, drive_client=FakeDrive(tmp_path), mayan_client=mayan)

    manifest = migrator.scan()
    manifest = migrator.migrate(dry_run=True)

    assert manifest.items["g1"].status == SKIPPED
    assert mayan.calls == []


def test_successful_migration(tmp_path) -> None:
    settings = _settings(tmp_path, dry_run=False)
    mayan = FakeMayan()
    migrator = Migrator(settings, drive_client=FakeDrive(tmp_path), mayan_client=mayan)

    migrator.scan()
    manifest = migrator.migrate()

    assert manifest.items["g1"].status == UPLOADED
    assert manifest.items["g1"].mayan_document_id == 20
    assert mayan.calls == ["cabinet", "document", "upload", "attach", "metadata", "tags"]


def test_metadata_retry_does_not_reupload_existing_document(tmp_path) -> None:
    settings = _settings(tmp_path, dry_run=False)
    mayan = MetadataFailOnceMayan()
    migrator = Migrator(settings, drive_client=FakeDrive(tmp_path), mayan_client=mayan)

    migrator.scan()
    first = migrator.migrate()
    second = migrator.migrate(retry_failed=True)

    assert first.items["g1"].mayan_document_id == 20
    assert second.items["g1"].status == UPLOADED
    assert mayan.calls == [
        "cabinet",
        "document",
        "upload",
        "attach",
        "metadata",
        "cabinet",
        "attach",
        "metadata",
        "tags",
    ]


def test_upload_retry_reuploads_existing_document(tmp_path) -> None:
    settings = _settings(tmp_path, dry_run=False)
    mayan = UploadFailOnceMayan()
    migrator = Migrator(settings, drive_client=FakeDrive(tmp_path), mayan_client=mayan)

    migrator.scan()
    first = migrator.migrate()
    second = migrator.migrate(retry_failed=True)

    assert first.items["g1"].status == FAILED
    assert first.items["g1"].mayan_document_id == 20
    assert second.items["g1"].status == UPLOADED
    assert second.items["g1"].mayan_document_id == 20
    assert mayan.calls == [
        "cabinet",
        "document",
        "upload",
        "cabinet",
        "upload",
        "attach",
        "metadata",
        "tags",
    ]


def _settings(tmp_path, dry_run: bool) -> Settings:
    return Settings(
        google_service_account_file=tmp_path / "service.json",
        google_drive_root_folder_id="root",
        mayan_base_url="https://mayan.example.com",
        mayan_api_token="token",
        mayan_default_document_type_id=1,
        manifest_path=tmp_path / "manifest.json",
        download_temp_dir=tmp_path / "downloads",
        dry_run=dry_run,
        report_json_path=tmp_path / "report.json",
        report_csv_path=tmp_path / "report.csv",
        log_path=tmp_path / "migration.log",
    )
