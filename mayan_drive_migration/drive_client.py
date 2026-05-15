from __future__ import annotations

import logging
from pathlib import Path
from typing import Any


LOGGER = logging.getLogger(__name__)

DRIVE_FOLDER_MIME = "application/vnd.google-apps.folder"
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

OFFICE_EXPORTS = {
    "application/vnd.google-apps.document": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".docx",
    ),
    "application/vnd.google-apps.spreadsheet": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xlsx",
    ),
    "application/vnd.google-apps.presentation": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".pptx",
    ),
}

PDF_EXPORTS = {
    "application/vnd.google-apps.document": ("application/pdf", ".pdf"),
    "application/vnd.google-apps.spreadsheet": ("application/pdf", ".pdf"),
    "application/vnd.google-apps.presentation": ("application/pdf", ".pdf"),
}


class DriveClient:
    def __init__(self, service_account_file: Path, export_mode: str = "office") -> None:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        credentials = service_account.Credentials.from_service_account_file(
            str(service_account_file),
            scopes=SCOPES,
        )
        self.service = build("drive", "v3", credentials=credentials, cache_discovery=False)
        self.export_mode = export_mode

    def scan_folder(self, root_folder_id: str) -> list[dict[str, Any]]:
        root = self._get_file(root_folder_id, fields="id,name,mimeType")
        root_name = root.get("name", root_folder_id)
        files: list[dict[str, Any]] = []
        self._scan_folder(root_folder_id, root_name, root_name, files)
        return files

    def download_file(self, file_record: dict[str, Any], destination_dir: Path) -> Path:
        from googleapiclient.http import MediaIoBaseDownload

        destination_dir.mkdir(parents=True, exist_ok=True)
        file_id = file_record["file_id"]
        name = file_record["name"]
        mime_type = file_record["mime_type"]
        export = self._export_spec(mime_type)
        if export:
            export_mime, extension = export
            destination = destination_dir / _with_suffix(name, extension)
            request = self.service.files().export_media(fileId=file_id, mimeType=export_mime)
        else:
            destination = destination_dir / name
            request = self.service.files().get_media(fileId=file_id)

        with destination.open("wb") as handle:
            downloader = MediaIoBaseDownload(handle, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
                if status:
                    LOGGER.debug("Downloaded %.0f%% of %s", status.progress() * 100, file_id)
        return destination

    def _scan_folder(
        self,
        folder_id: str,
        folder_name: str,
        current_path: str,
        files: list[dict[str, Any]],
    ) -> None:
        for child in self._list_children(folder_id):
            name = child["name"]
            mime_type = child["mimeType"]
            full_path = f"{current_path}/{name}"
            if mime_type == DRIVE_FOLDER_MIME:
                self._scan_folder(child["id"], name, full_path, files)
                continue
            files.append(
                {
                    "file_id": child["id"],
                    "name": name,
                    "mime_type": mime_type,
                    "modified_time": child.get("modifiedTime", ""),
                    "size": child.get("size"),
                    "full_path": full_path,
                    "parent_path": current_path,
                }
            )

    def _list_children(self, folder_id: str) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        page_token = None
        while True:
            response = (
                self.service.files()
                .list(
                    q=f"'{folder_id}' in parents and trashed = false",
                    spaces="drive",
                    fields="nextPageToken, files(id,name,mimeType,modifiedTime,size)",
                    pageSize=1000,
                    pageToken=page_token,
                )
                .execute()
            )
            results.extend(response.get("files", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                return results

    def _get_file(self, file_id: str, fields: str) -> dict[str, Any]:
        return self.service.files().get(fileId=file_id, fields=fields).execute()

    def _export_spec(self, mime_type: str) -> tuple[str, str] | None:
        if self.export_mode == "pdf":
            return PDF_EXPORTS.get(mime_type)
        return OFFICE_EXPORTS.get(mime_type)


def _with_suffix(name: str, suffix: str) -> str:
    path = Path(name)
    if path.suffix:
        return path.with_suffix(suffix).name
    return f"{name}{suffix}"
