from __future__ import annotations

from typing import Any

import requests

from business_central_client.auth import TokenProvider
from business_central_client.config import Settings


class BusinessCentralClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.token_provider = TokenProvider(settings)
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": settings.user_agent,
            }
        )

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token_provider.get_token()}"}

    def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        request_headers = self._headers()
        if headers:
            request_headers.update(headers)
        response = self.session.request(
            method=method,
            url=url,
            headers=request_headers,
            params=params,
            json=json,
            timeout=self.settings.timeout_seconds,
        )
        response.raise_for_status()
        if not response.content:
            return {}
        return response.json()

    def get_environments(self) -> dict[str, Any]:
        return self._request("GET", self.settings.environments_url)

    def get_companies(self) -> dict[str, Any]:
        return self._request("GET", f"{self.settings.api_base_url}/companies")

    def get_company_metadata(
        self,
        *,
        company_id: str | None = None,
        market: str | None = None,
    ) -> dict[str, Any] | None:
        resolved_company_id = self._resolve_company_id(company_id=company_id, market=market)
        if not resolved_company_id:
            return None

        companies = self.get_companies().get("value", [])
        for company in companies:
            if company.get("id") == resolved_company_id:
                return company
        return None

    def get_entities(
        self,
        entity_name: str,
        *,
        top: int | None = None,
        filters: str | None = None,
        company_id: str | None = None,
        market: str | None = None,
    ) -> dict[str, Any]:
        company = self._resolve_company_id(company_id=company_id, market=market)
        if not company:
            raise ValueError(
                "A company ID is required. Set BC_COMPANY_ID, configure BC_MARKET_<CODE>_COMPANY_ID, "
                "or pass company_id explicitly."
            )

        params: dict[str, Any] = {}
        if top is not None:
            params["$top"] = top
        if filters:
            params["$filter"] = filters

        url = f"{self.settings.api_base_url}/companies({company})/{entity_name}"
        return self._request("GET", url, params=params or None)

    def get_entity(
        self,
        entity_name: str,
        entity_id: str,
        *,
        company_id: str | None = None,
        market: str | None = None,
    ) -> dict[str, Any]:
        company = self._resolve_company_id(company_id=company_id, market=market)
        if not company:
            raise ValueError(
                "A company ID is required. Set BC_COMPANY_ID, configure BC_MARKET_<CODE>_COMPANY_ID, "
                "or pass company_id explicitly."
            )

        url = f"{self.settings.api_base_url}/companies({company})/{entity_name}({entity_id})"
        return self._request("GET", url)

    def patch_entity(
        self,
        entity_name: str,
        entity_id: str,
        payload: dict[str, Any],
        *,
        company_id: str | None = None,
        market: str | None = None,
        if_match: str = "*",
    ) -> dict[str, Any]:
        company = self._resolve_company_id(company_id=company_id, market=market)
        if not company:
            raise ValueError(
                "A company ID is required. Set BC_COMPANY_ID, configure BC_MARKET_<CODE>_COMPANY_ID, "
                "or pass company_id explicitly."
            )

        url = f"{self.settings.api_base_url}/companies({company})/{entity_name}({entity_id})"
        return self._request(
            "PATCH",
            url,
            json=payload,
            headers={"If-Match": if_match},
        )

    def patch_company_path(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        company_id: str | None = None,
        market: str | None = None,
        if_match: str = "*",
        **path_params: str,
    ) -> dict[str, Any]:
        company = self._resolve_company_id(company_id=company_id, market=market)
        if not company:
            raise ValueError(
                "A company ID is required. Set BC_COMPANY_ID, configure BC_MARKET_<CODE>_COMPANY_ID, "
                "or pass company_id explicitly."
            )

        normalized_path = path.strip()
        if normalized_path.startswith("http://") or normalized_path.startswith("https://"):
            url = normalized_path
        else:
            url = self._expand_relative_path(normalized_path, company, **path_params)

        return self._request(
            "PATCH",
            url,
            json=payload,
            headers={"If-Match": if_match},
        )

    def post_to_company(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        company_id: str | None = None,
        market: str | None = None,
    ) -> dict[str, Any]:
        company = self._resolve_company_id(company_id=company_id, market=market)
        if not company:
            raise ValueError(
                "A company ID is required. Set BC_COMPANY_ID, configure BC_MARKET_<CODE>_COMPANY_ID, "
                "or pass company_id explicitly."
            )

        normalized_path = path.strip()
        if normalized_path.startswith("http://") or normalized_path.startswith("https://"):
            url = normalized_path
        else:
            url = self._expand_relative_path(normalized_path, company)

        return self._request("POST", url, json=payload)

    def _expand_relative_path(self, path: str, company_id: str, **path_params: str) -> str:
        cleaned = path if path.startswith("/") else f"/{path}"
        rendered = cleaned.format(company_id=company_id, **path_params)
        if rendered.startswith("/api/"):
            return f"https://api.businesscentral.dynamics.com/v2.0/{self.settings.environment}{rendered}"
        if rendered.startswith("/companies("):
            return f"{self.settings.api_base_url}{rendered}"
        raise ValueError(
            "Unsupported relative path. Use an absolute URL, a path starting with "
            "'/api/', or a company-scoped path starting with '/companies('."
        )

    def resolve_payment_term(self, code_or_name: str, *, market: str | None = None) -> dict[str, Any] | None:
        needle = (code_or_name or "").strip().upper()
        if not needle:
            return None

        rows = self.get_entities("paymentTerms", top=500, market=market).get("value", [])
        for row in rows:
            if (row.get("code") or "").strip().upper() == needle:
                return row
        for row in rows:
            if (row.get("displayName") or "").strip().upper() == needle:
                return row
        return None

    def resolve_payment_method(self, code_or_name: str, *, market: str | None = None) -> dict[str, Any] | None:
        needle = (code_or_name or "").strip().upper()
        if not needle:
            return None

        rows = self.get_entities("paymentMethods", top=500, market=market).get("value", [])
        for row in rows:
            if (row.get("code") or "").strip().upper() == needle:
                return row
        for row in rows:
            if (row.get("displayName") or "").strip().upper() == needle:
                return row
        return None

    def _resolve_company_id(
        self,
        *,
        company_id: str | None,
        market: str | None,
    ) -> str | None:
        if company_id:
            return company_id

        market_settings = self.settings.get_market(market)
        if market_settings:
            return market_settings.company_id

        return self.settings.company_id
