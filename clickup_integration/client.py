from __future__ import annotations

import mimetypes
import time
from pathlib import Path
from typing import Any

import requests

from clickup_integration.config import ClickUpSettings


class ClickUpClient:
    def __init__(self, settings: ClickUpSettings) -> None:
        self.settings = settings
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )

    def get_authorized_workspaces(self) -> dict[str, Any]:
        return self._request("GET", "https://api.clickup.com/api/v2/team")

    def get_task(
        self,
        task_id: str,
        *,
        custom_task_ids: bool = False,
        team_id: str | None = None,
        include_subtasks: bool = False,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "custom_task_ids": str(custom_task_ids).lower(),
            "include_subtasks": str(include_subtasks).lower(),
        }
        if custom_task_ids and team_id:
            params["team_id"] = team_id
        return self._request("GET", f"https://api.clickup.com/api/v2/task/{task_id}", params=params)

    def get_list_custom_fields(self, list_id: str) -> dict[str, Any]:
        return self._request(
            "GET",
            f"https://api.clickup.com/api/v2/list/{list_id}/field",
        )

    def get_list_tasks(
        self,
        list_id: str,
        *,
        archived: bool = False,
        include_closed: bool = False,
        page: int = 0,
        subtasks: bool = False,
        query: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
                "archived": str(archived).lower(),
                "include_closed": str(include_closed).lower(),
                "page": page,
                "subtasks": str(subtasks).lower(),
        }
        if query:
            params["query"] = query
        return self._request(
            "GET",
            f"https://api.clickup.com/api/v2/list/{list_id}/task",
            params=params,
        )

    def update_task(
        self,
        task_id: str,
        *,
        status: str | None = None,
        name: str | None = None,
        description: str | None = None,
        custom_task_ids: bool = False,
        team_id: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if status is not None:
            payload["status"] = status
        if name is not None:
            payload["name"] = name
        if description is not None:
            payload["description"] = description

        params: dict[str, Any] = {
            "custom_task_ids": str(custom_task_ids).lower(),
        }
        if custom_task_ids and team_id:
            params["team_id"] = team_id

        return self._request(
            "PUT",
            f"https://api.clickup.com/api/v2/task/{task_id}",
            params=params,
            json=payload or None,
        )

    def create_task(
        self,
        list_id: str,
        *,
        name: str,
        description: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"name": name}
        if description is not None:
            payload["description"] = description
        if status is not None:
            payload["status"] = status
        return self._request(
            "POST",
            f"https://api.clickup.com/api/v2/list/{list_id}/task",
            json=payload,
        )

    def create_task_comment(
        self,
        task_id: str,
        *,
        comment_text: str,
        notify_all: bool = False,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"https://api.clickup.com/api/v2/task/{task_id}/comment",
            json={
                "comment_text": comment_text,
                "notify_all": notify_all,
            },
        )

    def get_task_comments(
        self,
        task_id: str,
        *,
        start: int | None = None,
        start_id: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if start is not None:
            params["start"] = start
        if start_id is not None:
            params["start_id"] = start_id
        return self._request(
            "GET",
            f"https://api.clickup.com/api/v2/task/{task_id}/comment",
            params=params or None,
        )

    def create_task_comment_with_mentions(
        self,
        task_id: str,
        *,
        comment_text: str,
        user_ids: tuple[int, ...] | list[int],
        notify_all: bool = False,
    ) -> dict[str, Any]:
        comment: list[dict[str, Any]] = []
        for index, user_id in enumerate(user_ids):
            if index:
                comment.append({"text": " y "})
            comment.append({"type": "tag", "user": {"id": int(user_id)}})
        if comment:
            comment.append({"text": ", "})
        comment.append({"text": comment_text})
        return self._request(
            "POST",
            f"https://api.clickup.com/api/v2/task/{task_id}/comment",
            json={"comment": comment, "notify_all": notify_all},
        )

    def ensure_task_comment_with_mentions(
        self,
        task_id: str,
        *,
        comment_text: str,
        user_ids: tuple[int, ...] | list[int],
        notify_all: bool = False,
    ) -> dict[str, Any]:
        response = self.get_task_comments(task_id)
        for existing in response.get("comments") or []:
            existing_text = str(existing.get("comment_text") or "")
            segment_text = "".join(
                str(segment.get("text") or "")
                for segment in (existing.get("comment") or [])
                if isinstance(segment, dict) and segment.get("text") is not None
            )
            if comment_text in existing_text or comment_text in segment_text:
                return {"status": "existing", "comment": existing}
        created = self.create_task_comment_with_mentions(
            task_id,
            comment_text=comment_text,
            user_ids=user_ids,
            notify_all=notify_all,
        )
        return {"status": "created", "comment": created}

    def attach_file_to_task(
        self,
        task_id: str,
        local_path: str | Path,
        *,
        file_name: str | None = None,
        mime_type: str | None = None,
        custom_task_ids: bool = False,
        team_id: str | None = None,
    ) -> dict[str, Any]:
        path = Path(local_path)
        upload_name = file_name or path.name
        upload_mime_type = (
            mime_type or mimetypes.guess_type(upload_name)[0] or "application/octet-stream"
        )
        params: dict[str, Any] = {
            "custom_task_ids": str(custom_task_ids).lower(),
        }
        if custom_task_ids and team_id:
            params["team_id"] = team_id
        headers = {
            **self._authorization_headers(),
            "Accept": "application/json",
        }
        with path.open("rb") as handle:
            response = requests.post(
                f"https://api.clickup.com/api/v2/task/{task_id}/attachment",
                headers=headers,
                params=params,
                files={"attachment": (upload_name, handle, upload_mime_type)},
                timeout=120,
            )
        response.raise_for_status()
        if not response.content:
            return {}
        return response.json()

    def set_task_custom_field_value(
        self,
        task_id: str,
        field_id: str,
        value: Any,
        *,
        value_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"value": value}
        if value_options:
            payload["value_options"] = value_options
        return self._request(
            "POST",
            f"https://api.clickup.com/api/v2/task/{task_id}/field/{field_id}",
            json=payload,
        )

    def clear_task_custom_field_value(
        self,
        task_id: str,
        field_id: str,
    ) -> dict[str, Any]:
        """Remove the current value before replacing a ClickUp Files field."""
        return self._request(
            "DELETE",
            f"https://api.clickup.com/api/v2/task/{task_id}/field/{field_id}",
        )

    def upload_custom_field_attachment(
        self,
        workspace_id: str,
        field_id: str,
        local_path: str | Path,
        *,
        file_name: str | None = None,
        mime_type: str | None = None,
    ) -> dict[str, Any]:
        path = Path(local_path)
        upload_name = file_name or path.name
        upload_mime_type = (
            mime_type or mimetypes.guess_type(upload_name)[0] or "application/octet-stream"
        )
        headers = {
            **self._authorization_headers(),
            "Accept": "application/json",
        }
        retryable_statuses = {429, 500, 502, 503, 504}
        response: requests.Response | None = None
        for attempt in range(1, 4):
            with path.open("rb") as handle:
                response = requests.post(
                    f"https://api.clickup.com/api/v3/workspaces/{workspace_id}/custom_fields/{field_id}/attachments",
                    headers=headers,
                    files={"attachment": (upload_name, handle, upload_mime_type)},
                    timeout=120,
                )
            if response.status_code not in retryable_statuses:
                response.raise_for_status()
                return response.json()
            if attempt < 3:
                time.sleep(float(attempt))

        if response is None:  # pragma: no cover - defensive guard for requests behavior
            raise RuntimeError(f"ClickUp did not return a response while uploading {upload_name}.")
        response.raise_for_status()
        return response.json()

    def set_task_file_custom_field_attachments(
        self,
        task_id: str,
        field_id: str,
        attachment_ids: list[str],
    ) -> dict[str, Any]:
        return self.set_task_custom_field_value(task_id, field_id, attachment_ids)

    def get_workspace_custom_fields(self, workspace_id: str) -> dict[str, Any]:
        return self._request(
            "GET",
            f"https://api.clickup.com/api/v2/team/{workspace_id}/field",
        )

    def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = self.session.request(
            method=method,
            url=url,
            headers=self._authorization_headers(),
            params=params,
            json=json,
            timeout=30,
        )
        response.raise_for_status()
        if not response.content:
            return {}
        return response.json()

    def _authorization_headers(self) -> dict[str, str]:
        token = self.settings.access_token
        if not token:
            raise ValueError(
                "CLICKUP_ACCESS_TOKEN is not set. Complete the OAuth flow first."
            )

        token_type = (self.settings.token_type or "Bearer").strip()
        if token.startswith("pk_"):
            return {"Authorization": token}
        return {"Authorization": f"{token_type} {token}"}
