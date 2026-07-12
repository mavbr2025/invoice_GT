from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

from inspection_reports.config import GraphSettings
from inspection_reports.models import SharePointItem


@dataclass
class GraphToken:
    value: str
    expires_at: datetime

    def is_valid(self) -> bool:
        return datetime.now(timezone.utc) < self.expires_at


class GraphTokenProvider:
    def __init__(self, settings: GraphSettings) -> None:
        self.settings = settings
        self._token: GraphToken | None = None

    def get_token(self) -> str:
        if self._token and self._token.is_valid():
            return self._token.value

        response = requests.post(
            self.settings.token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": self.settings.client_id,
                "client_secret": self.settings.client_secret,
                "scope": self.settings.scope,
            },
            headers={"User-Agent": self.settings.user_agent},
            timeout=self.settings.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        expires_in = int(payload.get("expires_in", 3600))
        self._token = GraphToken(
            value=payload["access_token"],
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=max(expires_in - 60, 60)),
        )
        return self._token.value


class SharePointGraphClient:
    def __init__(self, settings: GraphSettings) -> None:
        self.settings = settings
        self.token_provider = GraphTokenProvider(settings)
        self.session = requests.Session()

    def get_site_id(self, *, hostname: str, site_path: str) -> str:
        site = self._request("GET", f"/sites/{hostname}:{site_path}")
        return site["id"]

    def list_files_recursive(
        self,
        *,
        hostname: str,
        site_path: str,
        folder_path: str,
        max_depth: int,
    ) -> list[SharePointItem]:
        site_id = self.get_site_id(hostname=hostname, site_path=site_path)
        return self._list_files_recursive(
            site_id=site_id,
            folder_path=_clean_path(folder_path),
            depth=0,
            max_depth=max_depth,
        )

    def get_item_from_share_url(self, share_url: str) -> SharePointItem:
        item = self._request("GET", f"/shares/{_share_id_from_url(share_url)}/driveItem")
        return _to_item(item, _path_from_drive_item(item))

    def get_item_by_drive_path(self, *, drive_id: str, item_path: str) -> SharePointItem:
        clean_path = _clean_path(item_path)
        item = self._request("GET", f"/drives/{drive_id}/root:/{_encode_path(clean_path)}")
        return _to_item(item, clean_path)

    def list_files_recursive_from_folder_item(
        self,
        folder: SharePointItem,
        *,
        max_depth: int,
    ) -> list[SharePointItem]:
        return self._list_files_recursive_from_drive_item(
            drive_id=folder.drive_id,
            item_id=folder.id,
            parent_path=folder.path,
            depth=0,
            max_depth=max_depth,
        )

    def find_child_file_by_name_from_folder_item(
        self,
        *,
        folder: SharePointItem,
        file_name: str,
    ) -> SharePointItem | None:
        normalized = file_name.strip().lower()
        for child in self._list_children_by_drive_item(drive_id=folder.drive_id, item_id=folder.id):
            if child.get("folder") is not None:
                continue
            if (child.get("name") or "").strip().lower() == normalized:
                return _to_item(child, _join_path(folder.path, child.get("name") or file_name))
        return None

    def find_child_file_by_name(
        self,
        *,
        hostname: str,
        site_path: str,
        folder_path: str,
        file_name: str,
    ) -> SharePointItem | None:
        site_id = self.get_site_id(hostname=hostname, site_path=site_path)
        clean_folder = _clean_path(folder_path)
        normalized = file_name.strip().lower()
        for child in self._list_children(site_id=site_id, folder_path=clean_folder):
            if child.get("folder") is not None:
                continue
            if (child.get("name") or "").strip().lower() == normalized:
                return _to_item(child, _join_path(clean_folder, child.get("name") or file_name))
        return None

    def download_item(self, item: SharePointItem, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        response = self._raw_request(
            "GET",
            f"/drives/{item.drive_id}/items/{item.id}/content",
            stream=True,
        )
        response.raise_for_status()
        with destination.open("wb") as output:
            for chunk in response.iter_content(chunk_size=1024 * 256):
                if chunk:
                    output.write(chunk)
        return destination

    def upload_file_to_folder_item(
        self,
        *,
        folder: SharePointItem,
        local_path: Path,
        file_name: str | None = None,
    ) -> SharePointItem:
        target_name = file_name or local_path.name
        encoded_name = quote(target_name, safe="")
        with local_path.open("rb") as source:
            item = self._request(
                "PUT",
                f"/drives/{folder.drive_id}/items/{folder.id}:/{encoded_name}:/content",
                data=source,
                headers={"Content-Type": "application/pdf"},
            )
        return _to_item(item, _join_path(folder.path, target_name))

    def upload_file(
        self,
        *,
        hostname: str,
        site_path: str,
        folder_path: str,
        local_path: Path,
        file_name: str | None = None,
    ) -> SharePointItem:
        site_id = self.get_site_id(hostname=hostname, site_path=site_path)
        clean_folder = _clean_path(folder_path)
        self.ensure_folder_path(site_id=site_id, folder_path=clean_folder)

        target_name = file_name or local_path.name
        encoded_path = _encode_path(_join_path(clean_folder, target_name))
        url = f"/sites/{site_id}/drive/root:/{encoded_path}:/content"
        with local_path.open("rb") as source:
            item = self._request(
                "PUT",
                url,
                data=source,
                headers={"Content-Type": "application/pdf"},
        )
        return _to_item(item, _join_path(clean_folder, target_name))

    def create_view_link_for_item(
        self,
        item: SharePointItem,
        *,
        scope: str = "organization",
    ) -> str:
        payload = self._request(
            "POST",
            f"/drives/{item.drive_id}/items/{item.id}/createLink",
            json={"type": "view", "scope": scope},
        )
        link = payload.get("link") or {}
        web_url = link.get("webUrl")
        if not web_url:
            raise ValueError("Microsoft Graph did not return a SharePoint sharing link.")
        return web_url

    def create_view_link(
        self,
        *,
        hostname: str,
        site_path: str,
        item_path: str,
        scope: str = "organization",
    ) -> str:
        site_id = self.get_site_id(hostname=hostname, site_path=site_path)
        encoded_path = _encode_path(_clean_path(item_path))
        payload = self._request(
            "POST",
            f"/sites/{site_id}/drive/root:/{encoded_path}:/createLink",
            json={"type": "view", "scope": scope},
        )
        link = payload.get("link") or {}
        web_url = link.get("webUrl")
        if not web_url:
            raise ValueError("Microsoft Graph did not return a SharePoint sharing link.")
        return web_url

    def ensure_folder_path(self, *, site_id: str, folder_path: str) -> None:
        current = ""
        for part in [part for part in folder_path.split("/") if part]:
            existing = self._find_child_folder(site_id=site_id, parent_path=current, name=part)
            if existing:
                current = _join_path(current, part)
                continue

            parent_url = (
                f"/sites/{site_id}/drive/root/children"
                if not current
                else f"/sites/{site_id}/drive/root:/{_encode_path(current)}:/children"
            )
            self._request(
                "POST",
                parent_url,
                json={
                    "name": part,
                    "folder": {},
                    "@microsoft.graph.conflictBehavior": "fail",
                },
            )
            current = _join_path(current, part)

    def _find_child_folder(
        self,
        *,
        site_id: str,
        parent_path: str,
        name: str,
    ) -> dict[str, Any] | None:
        children = self._list_children(site_id=site_id, folder_path=parent_path)
        normalized = name.strip().lower()
        for child in children:
            if child.get("folder") is not None and (child.get("name") or "").strip().lower() == normalized:
                return child
        return None

    def _list_files_recursive(
        self,
        *,
        site_id: str,
        folder_path: str,
        depth: int,
        max_depth: int,
    ) -> list[SharePointItem]:
        children = self._list_children(site_id=site_id, folder_path=folder_path)
        items: list[SharePointItem] = []
        for child in children:
            child_path = _join_path(folder_path, child.get("name") or "")
            if child.get("folder") is not None:
                if depth < max_depth:
                    items.extend(
                        self._list_files_recursive(
                            site_id=site_id,
                            folder_path=child_path,
                            depth=depth + 1,
                            max_depth=max_depth,
                        )
                    )
                continue
            items.append(_to_item(child, child_path))
        return items

    def _list_files_recursive_from_drive_item(
        self,
        *,
        drive_id: str,
        item_id: str,
        parent_path: str,
        depth: int,
        max_depth: int,
    ) -> list[SharePointItem]:
        children = self._list_children_by_drive_item(drive_id=drive_id, item_id=item_id)
        items: list[SharePointItem] = []
        for child in children:
            child_path = _join_path(parent_path, child.get("name") or "")
            if child.get("folder") is not None:
                if depth < max_depth:
                    items.extend(
                        self._list_files_recursive_from_drive_item(
                            drive_id=drive_id,
                            item_id=child["id"],
                            parent_path=child_path,
                            depth=depth + 1,
                            max_depth=max_depth,
                        )
                    )
                continue
            items.append(_to_item(child, child_path))
        return items

    def _list_children(self, *, site_id: str, folder_path: str) -> list[dict[str, Any]]:
        url = (
            f"/sites/{site_id}/drive/root/children"
            if not folder_path
            else f"/sites/{site_id}/drive/root:/{_encode_path(folder_path)}:/children"
        )
        return self._paged_request(url)

    def _list_children_by_drive_item(self, *, drive_id: str, item_id: str) -> list[dict[str, Any]]:
        return self._paged_request(f"/drives/{drive_id}/items/{item_id}/children")

    def _paged_request(self, path_or_url: str) -> list[dict[str, Any]]:
        values: list[dict[str, Any]] = []
        next_url: str | None = path_or_url
        while next_url:
            payload = self._request("GET", next_url)
            values.extend(payload.get("value") or [])
            next_url = payload.get("@odata.nextLink")
        return values

    def _request(
        self,
        method: str,
        path_or_url: str,
        *,
        json: dict[str, Any] | None = None,
        data: Any = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        response = self._raw_request(method, path_or_url, json=json, data=data, headers=headers)
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            detail = response.text[:1000] if response.text else response.reason
            raise RuntimeError(
                f"Microsoft Graph request failed with HTTP {response.status_code} "
                f"for {method} {response.url}: {detail}"
            ) from exc
        if not response.content:
            return {}
        return response.json()

    def _raw_request(
        self,
        method: str,
        path_or_url: str,
        *,
        json: dict[str, Any] | None = None,
        data: Any = None,
        headers: dict[str, str] | None = None,
        stream: bool = False,
    ) -> requests.Response:
        url = path_or_url if path_or_url.startswith("https://") else f"https://graph.microsoft.com/v1.0{path_or_url}"
        request_headers = {
            "Authorization": f"Bearer {self.token_provider.get_token()}",
            "User-Agent": self.settings.user_agent,
        }
        if headers:
            request_headers.update(headers)
        return self.session.request(
            method=method,
            url=url,
            headers=request_headers,
            json=json,
            data=data,
            timeout=self.settings.timeout_seconds,
            stream=stream,
        )


def is_supported_image(item: SharePointItem, extensions: tuple[str, ...]) -> bool:
    return item.path.lower().endswith(extensions)


def _to_item(payload: dict[str, Any], path: str) -> SharePointItem:
    file_details = payload.get("file") or {}
    parent = payload.get("parentReference") or {}
    return SharePointItem(
        id=payload["id"],
        name=payload.get("name") or Path(path).name,
        drive_id=payload.get("parentReference", {}).get("driveId") or parent.get("driveId") or "",
        path=path,
        web_url=payload.get("webUrl"),
        mime_type=file_details.get("mimeType"),
        size_bytes=payload.get("size"),
        is_folder=payload.get("folder") is not None,
    )


def _path_from_drive_item(payload: dict[str, Any]) -> str:
    name = payload.get("name") or ""
    parent = payload.get("parentReference") or {}
    parent_path = parent.get("path") or ""
    root_marker = "root:"
    if root_marker in parent_path:
        parent_path = parent_path.split(root_marker, 1)[1]
    return _join_path(parent_path, name)


def _share_id_from_url(url: str) -> str:
    encoded = base64.urlsafe_b64encode(url.encode("utf-8")).decode("ascii").rstrip("=")
    return f"u!{encoded}"


def _clean_path(path: str | None) -> str:
    return (path or "").strip().strip("/")


def _join_path(*parts: str) -> str:
    return "/".join(part.strip().strip("/") for part in parts if part and part.strip().strip("/"))


def _encode_path(path: str) -> str:
    return quote(_clean_path(path), safe="/")
