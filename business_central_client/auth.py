from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import requests

from business_central_client.config import Settings


@dataclass
class AccessToken:
    value: str
    expires_at: datetime

    def is_valid(self) -> bool:
        return datetime.now(timezone.utc) < self.expires_at


class TokenProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._token: AccessToken | None = None

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
        # Renew slightly early to avoid using a nearly expired token.
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=max(expires_in - 60, 60))

        self._token = AccessToken(
            value=payload["access_token"],
            expires_at=expires_at,
        )
        return self._token.value
