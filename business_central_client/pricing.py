from __future__ import annotations

from typing import Any

from business_central_client.client import BusinessCentralClient


class PricingService:
    def __init__(self, client: BusinessCentralClient) -> None:
        self.client = client

    def preview_price(
        self,
        *,
        market: str | None,
        customer_number: str,
        item_number: str,
        quantity: float,
        currency_code: str | None,
    ) -> dict[str, Any]:
        market_settings = self.client.settings.get_market(market)
        custom_pricing_path = (
            market_settings.custom_pricing_path
            if market_settings and market_settings.custom_pricing_path
            else self.client.settings.custom_pricing_path
        )

        customer = self._find_first(
            "customers",
            f"number eq '{customer_number}'",
            market=market,
        )
        item = self._find_first(
            "items",
            f"number eq '{item_number}'",
            market=market,
        )
        resolved_currency_code = self._resolve_currency_code(
            explicit_currency_code=currency_code,
            customer=customer,
            market_settings=market_settings,
        )

        result: dict[str, Any] = {
            "market": market_settings.key if market_settings else market,
            "customer": customer,
            "item": item,
            "quantity": quantity,
            "currencyCode": resolved_currency_code,
        }

        if custom_pricing_path:
            payload = {
                "customerNumber": customer_number,
                "itemNumber": item_number,
                "quantity": quantity,
            }
            if resolved_currency_code:
                payload["currencyCode"] = resolved_currency_code
            result["pricing_mode"] = "custom_endpoint"
            result["pricing_response"] = self.client.post_to_company(
                custom_pricing_path,
                payload,
                market=market,
            )
            return result

        result["pricing_mode"] = "base_item_price"
        result["pricing_response"] = {
            "message": (
                "No custom pricing endpoint is configured. This preview returns the item's "
                "standard unit price only and does not represent full Business Central "
                "customer-specific pricing logic."
            ),
            "baseUnitPrice": item.get("unitPrice"),
            "estimatedExtendedPrice": (
                item.get("unitPrice") * quantity if isinstance(item.get("unitPrice"), (int, float)) else None
            ),
        }
        return result

    def _find_first(
        self,
        entity_name: str,
        filters: str,
        *,
        market: str | None,
    ) -> dict[str, Any]:
        data = self.client.get_entities(
            entity_name,
            top=1,
            filters=filters,
            market=market,
        )
        values = data.get("value", [])
        if not values:
            raise LookupError(f"No {entity_name[:-1]} matched filter: {filters}")
        return values[0]

    def _resolve_currency_code(
        self,
        *,
        explicit_currency_code: str | None,
        customer: dict[str, Any],
        market_settings: Any,
    ) -> str | None:
        if explicit_currency_code:
            normalized = explicit_currency_code.strip().upper()
            self._validate_currency_code(normalized, market_settings)
            return normalized

        customer_currency = (customer.get("currencyCode") or "").strip().upper()
        if customer_currency:
            self._validate_currency_code(customer_currency, market_settings)
            return customer_currency

        if market_settings and market_settings.local_currency_code:
            return market_settings.local_currency_code

        return None

    def _validate_currency_code(self, currency_code: str, market_settings: Any) -> None:
        if not market_settings or not market_settings.supported_currency_codes:
            return

        if currency_code not in market_settings.supported_currency_codes:
            supported = ", ".join(market_settings.supported_currency_codes)
            raise ValueError(
                f"Currency {currency_code} is not configured for market {market_settings.key}. "
                f"Supported currencies: {supported}"
            )
