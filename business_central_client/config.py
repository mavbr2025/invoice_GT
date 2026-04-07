from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class MarketSettings:
    key: str
    company_id: str
    local_currency_code: str | None = None
    supported_currency_codes: tuple[str, ...] = ()
    custom_pricing_path: str | None = None


@dataclass(frozen=True)
class Settings:
    tenant_id: str
    client_id: str
    client_secret: str
    environment: str
    company_id: str | None
    api_version: str
    timeout_seconds: int
    user_agent: str
    custom_pricing_path: str | None
    customer_invoicing_sync_path: str | None = None
    default_market: str | None = None
    markets: dict[str, MarketSettings] = field(default_factory=dict)

    @property
    def token_url(self) -> str:
        return f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"

    @property
    def scope(self) -> str:
        return "https://api.businesscentral.dynamics.com/.default"

    @property
    def environments_url(self) -> str:
        return "https://api.businesscentral.dynamics.com/environments/v1.2"

    @property
    def api_base_url(self) -> str:
        return (
            "https://api.businesscentral.dynamics.com/"
            f"v2.0/{self.environment}/api/{self.api_version}"
        )

    def get_market(self, market_key: str | None = None) -> MarketSettings | None:
        key = (market_key or self.default_market or "").strip().upper()
        if not key:
            return None
        return self.markets.get(key)

    @classmethod
    def from_env(cls) -> "Settings":
        required = {
            "BC_TENANT_ID": os.getenv("BC_TENANT_ID", "").strip(),
            "BC_CLIENT_ID": os.getenv("BC_CLIENT_ID", "").strip(),
            "BC_CLIENT_SECRET": os.getenv("BC_CLIENT_SECRET", "").strip(),
            "BC_ENVIRONMENT": os.getenv("BC_ENVIRONMENT", "").strip(),
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            joined = ", ".join(missing)
            raise ValueError(
                f"Missing required environment variables: {joined}. "
                "Copy .env.example to .env and fill in the values."
            )

        company_id = os.getenv("BC_COMPANY_ID", "").strip() or None
        default_market = os.getenv("BC_DEFAULT_MARKET", "").strip().upper() or None
        custom_pricing_path = os.getenv("BC_CUSTOM_PRICING_PATH", "").strip() or None
        customer_invoicing_sync_path = (
            os.getenv("BC_CUSTOMER_INVOICING_SYNC_PATH", "").strip() or None
        )
        markets = cls._load_markets_from_env()

        if default_market and default_market not in markets:
            raise ValueError(
                f"BC_DEFAULT_MARKET={default_market} is not configured. "
                "Add BC_MARKET_<CODE>_COMPANY_ID for that market."
            )

        return cls(
            tenant_id=required["BC_TENANT_ID"],
            client_id=required["BC_CLIENT_ID"],
            client_secret=required["BC_CLIENT_SECRET"],
            environment=required["BC_ENVIRONMENT"],
            company_id=company_id,
            default_market=default_market,
            markets=markets,
            api_version=os.getenv("BC_API_VERSION", "v2.0").strip() or "v2.0",
            timeout_seconds=int(os.getenv("BC_TIMEOUT_SECONDS", "30")),
            user_agent=os.getenv("BC_USER_AGENT", "ContractingTool/0.1").strip()
            or "ContractingTool/0.1",
            custom_pricing_path=custom_pricing_path,
            customer_invoicing_sync_path=customer_invoicing_sync_path,
        )

    @staticmethod
    def _load_markets_from_env() -> dict[str, MarketSettings]:
        prefix = "BC_MARKET_"
        suffix = "_COMPANY_ID"
        markets: dict[str, MarketSettings] = {}

        for key, value in os.environ.items():
            if not key.startswith(prefix) or not key.endswith(suffix):
                continue

            company_id = value.strip()
            if not company_id:
                continue

            market_key = key[len(prefix) : -len(suffix)].strip().upper()
            local_currency_code = (
                os.getenv(f"{prefix}{market_key}_LOCAL_CURRENCY_CODE", "").strip().upper() or None
            )
            supported_currency_codes = tuple(
                currency.strip().upper()
                for currency in os.getenv(
                    f"{prefix}{market_key}_SUPPORTED_CURRENCY_CODES",
                    "",
                ).split(",")
                if currency.strip()
            )
            custom_pricing_path = (
                os.getenv(f"{prefix}{market_key}_CUSTOM_PRICING_PATH", "").strip() or None
            )
            markets[market_key] = MarketSettings(
                key=market_key,
                company_id=company_id,
                local_currency_code=local_currency_code,
                supported_currency_codes=supported_currency_codes,
                custom_pricing_path=custom_pricing_path,
            )

        return markets
