from types import SimpleNamespace

from clickup_integration.writeback import (
    build_bc_customer_url,
    prepare_clickup_bc_invoice_writeback,
    prepare_clickup_bc_writeback,
)


class FakeBCClient:
    def __init__(self) -> None:
        self.settings = SimpleNamespace(
            tenant_id="tenant-id",
            environment="Production",
        )

    def get_company_metadata(self, *, market: str | None = None, company_id: str | None = None):
        if market == "GT":
            return {"name": "MTM_GT_PROD", "displayName": "MTM LOGIX GUATEMALA, SOCIEDAD ANONIMA"}
        return None


def test_build_bc_customer_url() -> None:
    url = build_bc_customer_url(
        tenant_id="tenant-id",
        environment="Production",
        company_name="MTM_GT_PROD",
        customer_number="C00069",
    )
    assert url == (
        "https://businesscentral.dynamics.com/tenant-id/Production/"
        "?company=MTM_GT_PROD&page=21&filter=Customer.%27No.%27%20IS%20%27C00069%27&dc=0"
    )


def test_prepare_clickup_bc_writeback() -> None:
    clickup_summary = {
        "task_id": "task-1",
        "custom_fields": {
            "Business Central Customer Number": {"id": "field-number"},
            "Business Central Customer ID": {"id": "field-id"},
            "Business Central Customer Link": {"id": "field-link"},
            "Business Central Legal Name": {"id": "field-legal-name"},
            "BC Match Status": {
                "id": "field-status",
                "value": "opt-2",
                "type_config": {
                    "options": [
                        {"id": "opt-0", "name": "Unmatched", "orderindex": 0},
                        {"id": "opt-1", "name": "Likely Match", "orderindex": 1},
                        {"id": "opt-2", "name": "Confirmed", "orderindex": 2},
                    ]
                },
            },
        },
    }
    match_result = {
        "status": "likely_match",
        "candidates": [
            {
                "market": "GT",
                "number": "C00069",
                "id": "bc-id-1",
                "displayName": "ESKOLOR, SOCIEDAD ANONIMA",
            }
        ],
    }
    payload = prepare_clickup_bc_writeback(
        clickup_summary=clickup_summary,
        match_result=match_result,
        bc_client=FakeBCClient(),
    )
    assert payload["bc_customer_number"] == "C00069"
    assert payload["bc_customer_id"] == "bc-id-1"
    assert payload["bc_legal_name"] == "ESKOLOR, SOCIEDAD ANONIMA"
    assert payload["bc_match_status"] == "opt-2"
    assert payload["field_ids"]["link"] == "field-link"
    assert payload["field_ids"]["legal_name"] == "field-legal-name"


def test_prepare_clickup_bc_invoice_writeback() -> None:
    payload = prepare_clickup_bc_invoice_writeback(
        clickup_summary={
            "task_id": "task-1",
            "custom_fields": {
                "Business Central Invoice Number": {"id": "field-invoice-number"},
                "Business Central Invoice ID": {"id": "field-invoice-id"},
            },
        },
        created_invoice={"id": "invoice-id-1", "number": "SI-0001"},
    )

    assert payload["bc_invoice_number"] == "SI-0001"
    assert payload["bc_invoice_id"] == "invoice-id-1"
    assert payload["field_ids"]["invoice_number"] == "field-invoice-number"
    assert payload["field_ids"]["invoice_id"] == "field-invoice-id"
    assert payload["missing_fields"] == []
