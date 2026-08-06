from __future__ import annotations

from types import SimpleNamespace

from clickup_integration.invoice_sync import InvoiceAutomationSettings
from clickup_integration.storage_invoice_sync import (
    StorageInvoiceSettings,
    issue_clickup_bc_storage_invoice,
    prepare_clickup_bc_storage_invoice_preview,
)


class FakeStorageBCClient:
    def __init__(self, *, legacy_invoice: dict | None = None) -> None:
        self.settings = SimpleNamespace()
        self.legacy_invoice = legacy_invoice

    def find_entities(self, entity_name: str, *, filters: str, top: int = 1, company_id=None, market=None):
        assert market == "GT"
        if entity_name == "customers":
            return [
                {
                    "id": "customer-id-1",
                    "number": "C00102",
                    "displayName": "PROVEEDORA DE SERVICIOS, SOCIEDAD ANONIMA",
                    "currencyCode": "USD",
                    "paymentTermsId": "term-15-days",
                    "country": "GT",
                }
            ]
        assert entity_name == "salesInvoices"
        if "externalDocumentNumber eq 'MTMLXGT-25981-ALM'" in filters:
            return []
        if "externalDocumentNumber eq 'MTMLXGT-25981'" in filters and self.legacy_invoice:
            return [self.legacy_invoice]
        return []

    def get_customer_by_id(self, customer_id: str, *, market=None):
        assert market == "GT"
        return {
            "id": customer_id,
            "number": "C00102",
            "displayName": "PROVEEDORA DE SERVICIOS, SOCIEDAD ANONIMA",
            "currencyCode": "USD",
            "paymentTermsId": "term-15-days",
            "country": "GT",
        }

    def get_customer_invoicing_by_number(self, customer_number: str, *, company_id=None, market=None):
        assert customer_number == "C00102"
        assert market == "GT"
        return {
            "id": "customer-id-1",
            "number": customer_number,
            "countryRegionCode": "GT",
            "resolvedFelCountryCode": "GT",
            "felCountryReady": True,
        }

    def resolve_item_by_number(self, item_number: str, *, market=None):
        assert market == "GT"
        assert item_number == "NAT00000034"
        return {"id": "item-storage", "number": item_number}

    def get_posted_sales_invoice_lines(self, invoice_id: str, *, company_id=None, market=None):
        assert market == "GT"
        return [
            {
                "documentId": invoice_id,
                "lineType": "Item",
                "lineObjectNumber": "NAT00000034",
                "quantity": 10,
                "unitPrice": 27,
            }
        ]

    def get_posted_invoice_fel_description_by_number(self, invoice_number: str, *, company_id=None, market=None):
        assert market == "GT"
        return {
            "id": "fel-storage",
            "number": invoice_number,
            "electronicDocumentStatus": "Stamp Received",
        }


def invoice_settings() -> InvoiceAutomationSettings:
    return InvoiceAutomationSettings(
        ready_status="Listo para facturar",
        ok_finops_status="OK Finops",
        eta_horizon_days=10,
        supported_market="GT",
        supported_currency="USD",
        invoice_status_field_names=("Estatus de facturación (USD)/",),
        invoice_status_field_ids=("b436ff28-24d8-4a5a-9f7e-66623401dee1",),
        eta_field_names=("ETA",),
        currency_field_names=("Invoice Currency",),
        reference_field_names=("Reference",),
        invoice_date_field_names=("Invoice Date",),
        posting_date_field_names=("Posting Date",),
        due_date_field_names=("Due Date",),
        freight_field_names=("Freight",),
        inland_field_names=("Inland",),
        destination_field_names=("Destination Charges",),
        bc_customer_id_field_names=("Business Central Customer ID",),
        bc_customer_number_field_names=("Business Central Customer Number",),
        bc_invoice_number_field_names=("Business Central Invoice Number",),
        bc_invoice_id_field_names=("Business Central Invoice ID",),
        freight_account_number=None,
        inland_account_number=None,
        destination_account_number=None,
    )


def storage_summary(*, status: str = "Facturada", amount: str = "270") -> dict:
    return {
        "task_id": "86e12queh",
        "custom_id": "MTMLXGT-25981",
        "name": "5939 - E1",
        "status": "vacío devuelto",
        "market": "GT",
        "custom_fields": {
            "Estatus de facturación (USD)/": {
                "id": "b436ff28-24d8-4a5a-9f7e-66623401dee1",
                "type": "drop_down",
                "value": 9,
                "type_config": {
                    "options": [
                        {"id": "status-ready", "name": "Listo para facturar", "orderindex": 8},
                        {"id": "status-invoiced", "name": status, "orderindex": 9},
                    ]
                },
            },
            "Invoice Currency": {"value": "USD"},
            "Business Central Customer ID": {"value": "customer-id-1"},
            "Business Central Customer Number": {"value": "C00102"},
            "Almacenaje al cliente (USD)": {
                "id": "16edb6b2-ba0c-4a1e-94f0-f3f511d2f647",
                "type": "formula",
                "value": amount,
                "type_config": {"calculation_state": "failed"},
            },
            "Días de almacenaje incurridos": {
                "id": "edcdf91d-ff83-44a9-a869-dbeaff186ce4",
                "type": "formula",
                "value": "2",
                "type_config": {"calculation_state": "ready"},
            },
            "Number of Containers": {
                "id": "a05a2c81-2079-4467-9bfe-3723537bd350",
                "type": "number",
                "value": "5",
            },
        },
    }


def test_storage_preview_accepts_facturada_and_builds_one_line_per_container() -> None:
    result = prepare_clickup_bc_storage_invoice_preview(
        clickup_summary=storage_summary(),
        bc_client=FakeStorageBCClient(),
        invoice_settings=invoice_settings(),
        storage_settings=StorageInvoiceSettings(),
    )

    assert result["status"] == "dry_run_ready"
    assert result["reference"] == "MTMLXGT-25981-ALM"
    assert result["proposed_bc_payload"]["externalDocumentNumber"] == "MTMLXGT-25981-ALM"
    assert result["invoice_groups"] == ["ALL"]
    lines = result["proposed_bc_line_payloads"]
    assert len(lines) == 5
    assert {line["lineObjectNumber"] for line in lines} == {"NAT00000034"}
    assert {line["quantity"] for line in lines} == {2}
    assert {line["unitPrice"] for line in lines} == {27}
    assert sum(line["quantity"] * line["unitPrice"] for line in lines) == 270
    assert result["storage_validation"]["container_days"] == 10
    assert result["storage_validation"]["warnings"] == [
        {
            "reason": "amount_formula_not_ready",
            "calculation_state": "failed",
            "accepted_because": "component_recalculation_matches",
        }
    ]


def test_storage_preview_requires_existing_facturada_status() -> None:
    result = prepare_clickup_bc_storage_invoice_preview(
        clickup_summary=storage_summary(status="Listo para facturar"),
        bc_client=FakeStorageBCClient(),
        invoice_settings=invoice_settings(),
    )

    assert result["status"] == "not_previously_invoiced"


def test_storage_preview_blocks_amount_mismatch() -> None:
    result = prepare_clickup_bc_storage_invoice_preview(
        clickup_summary=storage_summary(amount="269"),
        bc_client=FakeStorageBCClient(),
        invoice_settings=invoice_settings(),
    )

    assert result["status"] == "storage_amount_mismatch"
    assert result["expected_amount"] == 270.0


def test_storage_issue_reuses_matching_stamped_manual_invoice() -> None:
    legacy_invoice = {
        "id": "posted-storage-id",
        "number": "GTFVR0004450",
        "externalDocumentNumber": "MTMLXGT-25981",
        "customerNumber": "C00102",
        "currencyCode": "USD",
        "totalAmountIncludingTax": 270,
    }
    result = issue_clickup_bc_storage_invoice(
        clickup_summary=storage_summary(),
        bc_client=FakeStorageBCClient(legacy_invoice=legacy_invoice),
        invoice_settings=invoice_settings(),
    )

    assert result["status"] == "applied"
    assert result["reused_existing_storage_invoice"] is True
    assert result["created_invoices"][0]["number"] == "GTFVR0004450"
    assert result["created_invoices"][0]["invoice_group"] == "ALM"
    assert result["finalized_invoices"][0]["custom_api_row_after_stamp"][
        "electronicDocumentStatus"
    ] == "Stamp Received"
