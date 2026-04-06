from business_central_client.client import BusinessCentralClient
from business_central_client.config import MarketSettings, Settings


def make_settings() -> Settings:
    return Settings(
        tenant_id="tenant-id",
        client_id="client-id",
        client_secret="secret",
        environment="Production",
        company_id="company-id",
        default_market="MX",
        markets={
            "MX": MarketSettings(
                key="MX",
                company_id="mx-company-id",
                local_currency_code="MXN",
                supported_currency_codes=("MXN", "USD"),
            ),
            "GT": MarketSettings(
                key="GT",
                company_id="gt-company-id",
                local_currency_code="GTQ",
                supported_currency_codes=("GTQ", "USD"),
            ),
        },
        api_version="v2.0",
        timeout_seconds=30,
        user_agent="ContractingTool/0.1",
        custom_pricing_path=None,
    )


def test_api_base_url() -> None:
    settings = make_settings()
    assert (
        settings.api_base_url
        == "https://api.businesscentral.dynamics.com/v2.0/Production/api/v2.0"
    )


def test_expand_company_scoped_path() -> None:
    client = BusinessCentralClient(make_settings())
    assert (
        client._expand_relative_path("/companies({company_id})/items", "abc")
        == "https://api.businesscentral.dynamics.com/v2.0/Production/api/v2.0/companies(abc)/items"
    )


def test_expand_custom_api_path() -> None:
    client = BusinessCentralClient(make_settings())
    assert (
        client._expand_relative_path(
            "/api/contoso/pricing/v1.0/companies({company_id})/priceCalculations",
            "abc",
        )
        == "https://api.businesscentral.dynamics.com/v2.0/Production/api/contoso/pricing/v1.0/companies(abc)/priceCalculations"
    )


def test_resolve_market_company_id() -> None:
    client = BusinessCentralClient(make_settings())
    assert client._resolve_company_id(company_id=None, market="GT") == "gt-company-id"
    assert client._resolve_company_id(company_id=None, market="MX") == "mx-company-id"
    assert client._resolve_company_id(company_id="override-id", market="GT") == "override-id"
