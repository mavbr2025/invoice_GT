from __future__ import annotations

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
