from __future__ import annotations

import csv
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .manifest import FAILED, PENDING, SKIPPED, UPLOADED, Manifest


def validate_manifest(manifest_path: Path, report_json_path: Path, report_csv_path: Path) -> dict[str, Any]:
    manifest = Manifest.load(manifest_path)
    counts = {
        "total_files_discovered": len(manifest.items),
        "total_uploaded": 0,
        "total_failed": 0,
        "total_skipped": 0,
        "total_pending": 0,
    }
    for item in manifest.items.values():
        if item.status == UPLOADED:
            counts["total_uploaded"] += 1
        elif item.status == FAILED:
            counts["total_failed"] += 1
        elif item.status == SKIPPED:
            counts["total_skipped"] += 1
        elif item.status == PENDING:
            counts["total_pending"] += 1

    failed = [asdict(item) for item in manifest.items.values() if item.status == FAILED]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **counts,
        "failed_files": failed,
    }
    report_json_path.parent.mkdir(parents=True, exist_ok=True)
    report_json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    _write_csv(report_csv_path, manifest)
    return report


def _write_csv(path: Path, manifest: Manifest) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["status", "google_file_id", "source_path", "mayan_document_id", "error_message"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for item in manifest.items.values():
            writer.writerow({field: getattr(item, field, "") for field in fieldnames})
