from types import SimpleNamespace

from clickup_integration.create_preview import prepare_clickup_bc_customer_create_preview


class FakeBCClient:
    def __init__(self) -> None:
        self.settings = SimpleNamespace(
            tenant_id="tenant-id",
            environment="Production",
            customer_invoicing_sync_path=None,
        )

    def get_company_metadata(self, *, market: str | None = None, company_id: str | None = None):
        if market == "GT":
            return {"name": "MTM_GT_PROD", "displayName": "MTM LOGIX GUATEMALA, SOCIEDAD ANONIMA"}
        return None

    def resolve_payment_term(self, code_or_name: str, *, market: str | None = None):
        assert market == "GT"
        if code_or_name == "7 DÍAS":
            return {"id": "term-7", "code": "7 DÍAS"}
        return None

    def resolve_payment_method(self, code_or_name: str, *, market: str | None = None):
        assert market == "GT"
        if code_or_name == "CREDITO":
            return {"id": "method-credit", "code": "CREDITO"}
        return None


def test_prepare_clickup_bc_customer_create_preview_prefers_more_legal_name() -> None:
    clickup_summary = {
        "task_id": "task-1",
        "custom_id": "MTM-2035664",
        "name": "FPK",
        "status": "current customer",
        "market": "GT",
        "custom_fields": {
            "Business Central Legal Name": {"value": "FPK Electronicos, S.A."},
            "Clientes/": {
                "value": 73,
                "type_config": {
                    "options": [
                        {"name": "FPK ELECTRONICOS.S.A.", "orderindex": 73},
                    ]
                },
            },
            "Webpage": {"value": "https://fpk.com.gt"},
            "Customer Tax ID": {"value": "304932-9"},
            "Contact E-mail 1": {"value": "operaciones@fpk.com.gt"},
            "Contact Phone 1": {"value": "+502 5511 2349"},
            "Customer Address": {"value": "11 Calle 5 - 59, Cdad. de Guatemala 01009, Guatemala"},
            "Credit Days Required": {"value": "7"},
            "Credit amount approved": {
                "id": "54574add-833f-42a5-b027-3b0d64ef95af",
                "value": "21400.23",
            },
            "Sales email": {"value": None},
            "BC Match Status": {
                "id": "field-status",
                "type_config": {
                    "options": [
                        {"id": "opt-2", "name": "Confirmed", "orderindex": 2},
                    ]
                },
            },
            "Business Central Customer Number": {"id": "field-number"},
            "Business Central Customer ID": {"id": "field-id"},
            "Business Central Customer Link": {"id": "field-link"},
        },
    }
    current_match = {
        "status": "possible_match",
        "candidates": [{"number": "C00001", "displayName": "ALCANCE INTEGRAL, SOCIEDAD ANONIMA"}],
    }

    preview = prepare_clickup_bc_customer_create_preview(
        clickup_summary=clickup_summary,
        current_match_result=current_match,
        bc_client=FakeBCClient(),
    )

    assert preview["status"] == "dry_run_ready"
    assert preview["proposed_bc_payload"]["displayName"] == "FPK ELECTRONICOS, S.A."
    assert preview["proposed_bc_payload"]["country"] == "GT"
    assert preview["proposed_bc_payload"]["website"] == "https://fpk.com.gt"
    assert preview["proposed_bc_payload"]["taxRegistrationNumber"] == "3049329"
    assert preview["proposed_bc_payload"]["email"] == "operaciones@fpk.com.gt"
    assert preview["proposed_bc_payload"]["phoneNumber"] == "+502 5511 2349"
    assert preview["proposed_bc_payload"]["paymentTermsId"] == "term-7"
    assert preview["proposed_bc_payload"]["paymentMethodId"] == "method-credit"
    assert preview["proposed_bc_payload"]["creditLimit"] == 21400.23
    assert (
        preview["proposed_bc_payload"]["addressLine1"]
        == "11 Calle 5 - 59, Cdad. de Guatemala 01009, Guatemala"
    )
    assert preview["proposed_bc_invoicing_payload"] == {
        "cfdiCustomerName": "FPK ELECTRONICOS, S.A.",
        "vatRegistrationNumber": "3049329",
        "invoiceEmail": "operaciones@fpk.com.gt",
        "correoFactura": "operaciones@fpk.com.gt",
        "contactName": None,
        "contactEmail": "operaciones@fpk.com.gt",
        "contactPhone": "+502 5511 2349",
        "paymentTermsCode": "7 DÍAS",
        "paymentMethodCode": "CREDITO",
        "cashFlowPaymentTermsCode": "7 DÍAS",
        "copySellToAddressTo": "Company",
        "taxIdentificationType": "Legal Entity",
        "generalBusinessPostingGroupCode": "NAC",
        "customerPostingGroupCode": "NAC",
    }
    assert preview["expected_clickup_writeback"]["bc_customer_number"] == "<BC response.number>"
    assert (
        preview["expected_clickup_writeback"]["bc_customer_link"]
        == "https://businesscentral.dynamics.com/tenant-id/Production/?company=MTM_GT_PROD&page=21&filter=Customer.%27No.%27%20IS%20%27%3CBC%20response.number%3E%27&dc=0"
    )
    assert preview["expected_clickup_writeback"]["bc_match_status"] == {
        "label": "Confirmed",
        "option_id": "opt-2",
    }
    assert any("possible BC match exists" in warning for warning in preview["warnings"])


def test_prepare_clickup_bc_customer_create_preview_rejects_non_current_customer() -> None:
    preview = prepare_clickup_bc_customer_create_preview(
        clickup_summary={"status": "qualification"},
        current_match_result=None,
        bc_client=FakeBCClient(),
    )
    assert preview["status"] == "not_current_customer"


def test_prepare_clickup_bc_customer_create_preview_blocks_missing_required_fields() -> None:
    preview = prepare_clickup_bc_customer_create_preview(
        clickup_summary={
            "task_id": "task-incomplete",
            "custom_id": "MTM-2040546",
            "name": "TEXTILES PARIS",
            "status": "current customer",
            "market": "GT",
            "custom_fields": {
                "Tax ID": {"value": "27375145"},
                "Contact Phone 1": {"value": "+502 22211083"},
            },
        },
        current_match_result={"status": "no_match", "candidates": []},
        bc_client=FakeBCClient(),
    )

    assert preview["status"] == "missing_required_fields"
    assert preview["missing_required_fields"] == [
        "Business Central Legal Name",
        "Contact E-mail 1 or Contact Email 1",
        "Customer Address",
        "Credit Terms or Credit Days Required",
    ]
