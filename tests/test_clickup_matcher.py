from clickup_integration.matcher import match_clickup_customer_to_bc


class FakeBCClient:
    def __init__(self, rows):
        self.rows = rows

    def get_entities(self, entity_name: str, *, top: int | None = None, market: str | None = None):
        assert entity_name == "customers"
        assert market == "GT"
        return {"value": self.rows}


def test_matcher_returns_exact_tax_id_match() -> None:
    clickup_summary = {
        "status": "current customer",
        "market": "GT",
        "name": "FPK",
        "custom_fields": {
            "Tax ID": {"value": "304932-9"},
            "Clientes/": {
                "value": 1,
                "type_config": {"options": [{"name": "FPK ELECTRONICOS.S.A.", "orderindex": 1}]},
            },
            "Webpage": {"value": "https://fpk.com.gt"},
        },
    }
    bc = FakeBCClient(
        [
            {
                "id": "bc-1",
                "number": "C00099",
                "displayName": "FPK ELECTRONICOS, SOCIEDAD ANONIMA",
                "email": "",
                "website": "",
                "country": "GT",
                "currencyCode": "USD",
                "taxRegistrationNumber": "3049329",
            }
        ]
    )

    result = match_clickup_customer_to_bc(clickup_summary=clickup_summary, bc_client=bc)

    assert result["status"] == "likely_match"
    assert result["match_basis"] == "exact_tax_id"
    assert result["candidates"][0]["number"] == "C00099"
    assert result["candidates"][0]["score"] == 1.0


def test_matcher_tax_id_guard_prevents_weak_fuzzy_duplicate() -> None:
    clickup_summary = {
        "status": "current customer",
        "market": "GT",
        "name": "FPK",
        "custom_fields": {
            "Tax ID": {"value": "304932-9"},
            "Clientes/": {
                "value": 1,
                "type_config": {"options": [{"name": "FPK ELECTRONICOS.S.A.", "orderindex": 1}]},
            },
            "Webpage": {"value": "https://fpk.com.gt"},
        },
    }
    bc = FakeBCClient(
        [
            {
                "id": "bc-1",
                "number": "C00007",
                "displayName": "ABURA, SOCIEDAD ANONIMA",
                "email": "transito_importaciones1@codaca.com.gt",
                "website": "",
                "country": "GT",
                "currencyCode": "USD",
                "taxRegistrationNumber": "82374929",
            }
        ]
    )

    result = match_clickup_customer_to_bc(clickup_summary=clickup_summary, bc_client=bc)

    assert result["status"] == "no_match"
    assert result["match_basis"] == "tax_id_guard_no_exact_match"
    assert result["candidates"][0]["number"] == "C00007"
