from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class ClickUpSettings:
    client_id: str | None
    client_secret: str | None
    redirect_uri: str | None
    access_token: str | None
    token_type: str | None
    default_workspace_id: str | None
    default_customer_list_id: str | None

    @property
    def authorization_url(self) -> str:
        return "https://app.clickup.com/api"

    @property
    def token_url(self) -> str:
        return "https://api.clickup.com/api/v2/oauth/token"

    @classmethod
    def from_env(cls, *, require_oauth: bool = False) -> "ClickUpSettings":
        client_id = os.getenv("CLICKUP_CLIENT_ID", "").strip()
        client_secret = os.getenv("CLICKUP_CLIENT_SECRET", "").strip()
        redirect_uri = os.getenv("CLICKUP_REDIRECT_URI", "").strip()

        if require_oauth:
            missing = [
                name
                for name, value in {
                    "CLICKUP_CLIENT_ID": client_id,
                    "CLICKUP_CLIENT_SECRET": client_secret,
                    "CLICKUP_REDIRECT_URI": redirect_uri,
                }.items()
                if not value
            ]
            if missing:
                joined = ", ".join(missing)
                raise ValueError(
                    f"Missing required ClickUp environment variables: {joined}. "
                    "Update .env before using the ClickUp integration."
                )

        return cls(
            client_id=client_id or None,
            client_secret=client_secret or None,
            redirect_uri=redirect_uri or None,
            access_token=os.getenv("CLICKUP_ACCESS_TOKEN", "").strip() or None,
            token_type=os.getenv("CLICKUP_TOKEN_TYPE", "").strip() or None,
            default_workspace_id=os.getenv("CLICKUP_DEFAULT_WORKSPACE_ID", "").strip() or None,
            default_customer_list_id=os.getenv("CLICKUP_DEFAULT_CUSTOMER_LIST_ID", "").strip() or None,
        )
