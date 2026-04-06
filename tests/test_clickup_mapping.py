from clickup_integration.mapping import (
    is_current_customer_status,
    resolve_dropdown_field,
    resolve_market_code_from_owner_country,
)


def test_resolve_dropdown_field() -> None:
    field = {
        "value": 2,
        "type_config": {
            "options": [
                {"name": "United States Of America", "orderindex": 0},
                {"name": "Mexico", "orderindex": 1},
                {"name": "Guatemala", "orderindex": 2},
            ]
        },
    }
    resolved = resolve_dropdown_field(field)
    assert resolved == {"name": "Guatemala", "orderindex": 2}


def test_resolve_market_code_from_owner_country() -> None:
    assert resolve_market_code_from_owner_country({"name": "Guatemala"}) == "GT"
    assert resolve_market_code_from_owner_country({"name": "Mexico"}) == "MX"
    assert resolve_market_code_from_owner_country({"name": "Brazil"}) is None


def test_is_current_customer_status() -> None:
    assert is_current_customer_status("current customer") is True
    assert is_current_customer_status(" CURRENT   CUSTOMER ") is True
    assert is_current_customer_status("negotiation") is False
    assert is_current_customer_status(None) is False
