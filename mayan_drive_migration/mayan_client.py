from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .config import Settings


LOGGER = logging.getLogger(__name__)


class MayanAPIError(RuntimeError):
    pass


class MayanClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.base_api_url = f"{settings.mayan_base_url.rstrip('/')}/api/v4"
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Token {settings.mayan_api_token}",
                "Accept": "application/json",
            }
        )

    def get_or_create_cabinet(self, path: str) -> int:
        parent_id: int | None = None
        cabinet_id: int | None = None
        for label in _path_parts(path):
            existing = self._find_cabinet(label=label, parent_id=parent_id)
            if existing:
                cabinet_id = int(existing["id"])
            else:
                response = self._request("POST", "/cabinets/", json={"label": label, "parent": parent_id})
                cabinet_id = int(response["id"])
            parent_id = cabinet_id
        if cabinet_id is None:
            raise MayanAPIError("Cannot create cabinet for empty path")
        return cabinet_id

    def get_or_create_tag(self, label: str) -> int:
        existing = self._find_by_label("/tags/", label)
        if existing:
            return int(existing["id"])
        response = self._request("POST", "/tags/", json={"label": label, "color": "#607D8B"})
        return int(response["id"])

    def create_document(self, label: str, document_type_id: int) -> int:
        response = self._request(
            "POST",
            "/documents/",
            data={"label": label, "document_type_id": str(document_type_id)},
        )
        return int(response["id"])

    def upload_file(self, document_id: int, file_path: Path) -> None:
        with file_path.open("rb") as handle:
            self._request(
                "POST",
                f"/documents/{document_id}/files/",
                files={"file_new": (file_path.name, handle)},
                data={"action_name": "replace"},
                accepted_statuses={200, 201, 202, 204},
                timeout=self._upload_timeout(file_path),
            )

    def attach_document_to_cabinet(self, document_id: int, cabinet_id: int) -> None:
        payloads = ({"document": document_id}, {"document_id": document_id})
        errors: list[str] = []
        for payload in payloads:
            try:
                self._request(
                    "POST",
                    f"/cabinets/{cabinet_id}/documents/add/",
                    json=payload,
                    accepted_statuses={200, 201, 202, 204},
                )
                return
            except MayanAPIError as exc:
                errors.append(str(exc))
        raise MayanAPIError("; ".join(errors))

    def set_metadata(self, document_id: int, metadata: dict[str, Any]) -> None:
        existing_metadata_type_ids = self._document_metadata_type_ids(document_id)
        for label, value in metadata.items():
            if value is None or value == "":
                continue
            metadata_type_id = self._get_or_create_metadata_type(label)
            self._ensure_metadata_type_for_document_type(metadata_type_id)
            if metadata_type_id in existing_metadata_type_ids:
                continue
            payload = {
                "metadata_type_id": metadata_type_id,
                "value": str(value),
            }
            self._request(
                "POST",
                f"/documents/{document_id}/metadata/",
                json=payload,
                accepted_statuses={200, 201, 202, 204},
            )
            existing_metadata_type_ids.add(metadata_type_id)

    def add_tags(self, document_id: int, tags: list[str]) -> None:
        LOGGER.warning("Mayan API does not expose tag-document assignment; ensuring tag records only")
        for tag in tags:
            self.get_or_create_tag(tag)

    def _get_or_create_metadata_type(self, label: str) -> int:
        existing = self._find_by_label("/metadata_types/", label)
        if existing:
            return int(existing["id"])
        response = self._request("POST", "/metadata_types/", json={"label": label, "name": label})
        return int(response["id"])

    def _ensure_metadata_type_for_document_type(self, metadata_type_id: int) -> None:
        path = f"/document_types/{self.settings.mayan_default_document_type_id}/metadata_types/"
        for item in self._paginate(path):
            metadata_type = item.get("metadata_type") or {}
            if item.get("metadata_type_id") == metadata_type_id or metadata_type.get("id") == metadata_type_id:
                return
        try:
            self._request(
                "POST",
                path,
                json={"metadata_type_id": metadata_type_id, "required": False},
                accepted_statuses={200, 201, 202, 204},
            )
        except MayanAPIError as exc:
            if "already exists" not in str(exc).lower():
                raise

    def _document_metadata_type_ids(self, document_id: int) -> set[int]:
        ids: set[int] = set()
        for item in self._paginate(f"/documents/{document_id}/metadata/"):
            metadata_type = item.get("metadata_type") or {}
            metadata_type_id = item.get("metadata_type_id") or metadata_type.get("id")
            if metadata_type_id is not None:
                ids.add(int(metadata_type_id))
        return ids

    def _find_by_label(self, path: str, label: str) -> dict[str, Any] | None:
        for item in self._paginate(path):
            if item.get("label") == label or item.get("name") == label:
                return item
        return None

    def _find_cabinet(self, *, label: str, parent_id: int | None) -> dict[str, Any] | None:
        for item in _flatten_cabinets(self._paginate("/cabinets/")):
            if item.get("label") == label and item.get("parent_id") == parent_id:
                return item
        return None

    def _paginate(self, path: str) -> list[dict[str, Any]]:
        url = self._url(path)
        results: list[dict[str, Any]] = []
        while url:
            response = self._request_url("GET", url)
            if isinstance(response, list):
                results.extend(response)
                return results
            results.extend(response.get("results", []))
            url = response.get("next")
        return results

    def _request(
        self,
        method: str,
        path: str,
        *,
        accepted_statuses: set[int] | None = None,
        **kwargs: Any,
    ) -> Any:
        return self._request_url(method, self._url(path), accepted_statuses=accepted_statuses, **kwargs)

    @retry(
        retry=retry_if_exception_type((requests.RequestException, MayanAPIError)),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def _request_url(
        self,
        method: str,
        url: str,
        *,
        accepted_statuses: set[int] | None = None,
        **kwargs: Any,
    ) -> Any:
        accepted = accepted_statuses or {200, 201}
        timeout = kwargs.pop("timeout", self.settings.request_timeout_seconds)
        _rewind_file_handles(kwargs.get("files"))
        try:
            response = self.session.request(
                method,
                url,
                timeout=timeout,
                **kwargs,
            )
        except requests.RequestException:
            LOGGER.exception("Mayan API request failed: %s %s", method, url)
            raise

        if response.status_code not in accepted:
            LOGGER.error("Mayan API error %s %s: %s", method, url, response.text)
            raise MayanAPIError(f"{method} {url} returned {response.status_code}: {response.text}")
        if response.status_code == 204 or not response.content:
            return {}
        try:
            return response.json()
        except ValueError:
            return {"raw": response.text}

    def _url(self, path: str) -> str:
        return f"{self.base_api_url}/{path.strip('/')}/"

    def _upload_timeout(self, file_path: Path) -> int:
        size_mb = math.ceil(file_path.stat().st_size / (1024 * 1024))
        return max(self.settings.request_timeout_seconds, min(3600, 60 + size_mb * 10))


def _cabinet_label(path: str) -> str:
    return " > ".join(_path_parts(path))


def _path_parts(path: str) -> list[str]:
    return [part.strip() for part in path.replace("\\", "/").split("/") if part.strip()]


def _flatten_cabinets(cabinets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []
    for cabinet in cabinets:
        flattened.append(cabinet)
        flattened.extend(_flatten_cabinets(cabinet.get("children", [])))
    return flattened


def _rewind_file_handles(files: Any) -> None:
    if not files:
        return
    values = files.values() if isinstance(files, dict) else files
    for value in values:
        handle = value[1] if isinstance(value, tuple) and len(value) >= 2 else value
        if hasattr(handle, "seek"):
            handle.seek(0)
