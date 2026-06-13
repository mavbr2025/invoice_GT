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


def test_resolve_customer_by_name_accepts_unique_contained_match() -> None:
    class CustomerClient(BusinessCentralClient):
        def get_entities(self, entity_name, *, top=None, filters=None, company_id=None, market=None):
            assert entity_name == "customers"
            assert top == 1000
            assert market == "GT"
            return {
                "value": [
                    {
                        "id": "customer-1",
                        "number": "C0001",
                        "displayName": "MASESA, SOCIEDAD ANONIMA",
                        "email": "",
                        "website": "",
                    },
                    {
                        "id": "customer-2",
                        "number": "C0002",
                        "displayName": "OTHER CUSTOMER",
                        "email": "",
                        "website": "",
                    },
                ]
            }

    client = CustomerClient(make_settings())

    assert client.resolve_customer_by_name("MASESA", market="GT") == {
        "id": "customer-1",
        "number": "C0001",
        "displayName": "MASESA, SOCIEDAD ANONIMA",
        "email": "",
        "website": "",
    }


def test_resolve_customer_by_name_accepts_unique_email_or_website_match() -> None:
    class CustomerClient(BusinessCentralClient):
        def get_entities(self, entity_name, *, top=None, filters=None, company_id=None, market=None):
            assert entity_name == "customers"
            return {
                "value": [
                    {
                        "id": "customer-1",
                        "number": "C0001",
                        "displayName": "MOTOCOM, SOCIEDAD ANONIMA",
                        "email": "kevin.ortigoza@masesa.com",
                        "website": "https://masesa.com",
                    },
                    {
                        "id": "customer-2",
                        "number": "C0002",
                        "displayName": "OTHER CUSTOMER",
                        "email": "",
                        "website": "",
                    },
                ]
            }

    client = CustomerClient(make_settings())

    assert client.resolve_customer_by_name("MASESA", market="GT") == {
        "id": "customer-1",
        "number": "C0001",
        "displayName": "MOTOCOM, SOCIEDAD ANONIMA",
        "email": "kevin.ortigoza@masesa.com",
        "website": "https://masesa.com",
    }


def test_resolve_customer_by_name_matches_sa_to_sociedad_anonima() -> None:
    class CustomerClient(BusinessCentralClient):
        def get_entities(self, entity_name, *, top=None, filters=None, company_id=None, market=None):
            assert entity_name == "customers"
            return {
                "value": [
                    {
                        "id": "customer-1",
                        "number": "C00058",
                        "displayName": "SUPER AUTO REPUESTOS, SOCIEDAD ANONIMA",
                    }
                ]
            }

    client = CustomerClient(make_settings())

    assert client.resolve_customer_by_name("Super Auto Repuestos S.A.", market="GT") == {
        "id": "customer-1",
        "number": "C00058",
        "displayName": "SUPER AUTO REPUESTOS, SOCIEDAD ANONIMA",
    }
