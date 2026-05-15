from mayan_drive_migration.manifest import FAILED, PENDING, SKIPPED, UPLOADED, Manifest


def test_manifest_upsert_and_resume_filter(tmp_path) -> None:
    path = tmp_path / "manifest.json"
    manifest = Manifest.load(path)
    manifest.upsert_discovered(
        [
            {
                "file_id": "1",
                "full_path": "Root/File.pdf",
                "parent_path": "Root",
                "modified_time": "2026-01-01T00:00:00Z",
                "mime_type": "application/pdf",
            }
        ]
    )
    manifest.items["1"].status = UPLOADED
    manifest.save()

    loaded = Manifest.load(path)

    assert loaded.pending_items() == []
    assert [item.google_file_id for item in loaded.pending_items(force=True)] == ["1"]


def test_manifest_retry_failed_filter(tmp_path) -> None:
    manifest = Manifest(tmp_path / "manifest.json")
    manifest.upsert_discovered(
        [
            {"file_id": "1", "full_path": "Root/A.pdf", "parent_path": "Root"},
            {"file_id": "2", "full_path": "Root/B.pdf", "parent_path": "Root"},
        ]
    )
    manifest.items["1"].status = FAILED
    manifest.items["2"].status = PENDING

    assert [item.google_file_id for item in manifest.pending_items()] == ["2"]
    assert [item.google_file_id for item in manifest.pending_items(retry_failed=True)] == ["1", "2"]


def test_manifest_skipped_items_are_resumable(tmp_path) -> None:
    manifest = Manifest(tmp_path / "manifest.json")
    manifest.upsert_discovered(
        [{"file_id": "1", "full_path": "Root/A.pdf", "parent_path": "Root"}]
    )
    manifest.items["1"].status = SKIPPED

    assert [item.google_file_id for item in manifest.pending_items()] == ["1"]
