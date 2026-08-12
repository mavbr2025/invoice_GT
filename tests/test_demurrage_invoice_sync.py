from __future__ import annotations

from types import SimpleNamespace

from clickup_integration.demurrage_invoice_sync import (
    prepare_clickup_bc_demurrage_invoice_preview,
)
from clickup_integration.invoice_sync import InvoiceAutomationSettings


class FakeDemurrageBCClient:
    def __init__(self, *, attached: bool = True, fully_invoiced: bool = False) -> None:
        self.settings = SimpleNamespace()
        self.attached = attached
        self.fully_invoiced = fully_invoiced

    def find_entities(self, entity_name: str, *, filters: str, top: int = 1, **_kwargs):
        if entity_name == "customers":
            return [
                {
                    "id": "customer-current",
                    "number": "C00033",
                    "displayName": "TEXTILE WORKS SOCIEDAD ANONIMA",
                    "currencyCode": "USD",
                    "paymentTermsId": "term-15-days",
                    "country": "GT",
                }
            ]
        if entity_name == "salesInvoices" and "contains(externalDocumentNumber" in filters:
            return [
                {
                    "id": "dem-history-1",
                    "number": "GTFVR0004338",
                    "externalDocumentNumber": "GT250103 || MTMLXGT-26066",
                    "customerNumber": "C00024",
                    "customerName": "TEXMODAS SA",
                    "currencyCode": "USD",
                    "status": "Paid",
                }
            ]
        return []

    def get_posted_sales_invoice_by_number(self, invoice_number: str, **_kwargs):
        if not self.attached or invoice_number != "GTFVR0004338":
            return None
        return {
            "id": "dem-history-1",
            "number": invoice_number,
            "externalDocumentNumber": "GT250103 || MTMLXGT-26066",
            "customerNumber": "C00024",
            "customerName": "TEXMODAS SA",
            "currencyCode": "USD",
            "status": "Paid",
        }

    def get_posted_sales_invoice_lines(self, invoice_id: str, **_kwargs):
        assert invoice_id == "dem-history-1"
        quantity = 24 if self.fully_invoiced else 9
        return [
            {
                "lineObjectNumber": "NAT00000033",
                "description": "DEMORA",
                "quantity": quantity,
                "unitPrice": 185,
                "amountIncludingTax": quantity * 185,
            }
        ]

    def get_posted_invoice_fel_description_by_number(self, invoice_number: str, **_kwargs):
        return {
            "number": invoice_number,
            "electronicDocumentStatus": "Stamp Received",
        }

    def get_customer_by_id(self, customer_id: str, **_kwargs):
        return {
            "id": customer_id,
            "number": "C00033",
            "displayName": "TEXTILE WORKS SOCIEDAD ANONIMA",
            "currencyCode": "USD",
            "paymentTermsId": "term-15-days",
            "country": "GT",
        }

    def get_customer_invoicing_by_number(self, customer_number: str, **_kwargs):
        return {
            "id": "customer-current",
            "number": customer_number,
            "countryRegionCode": "GT",
            "resolvedFelCountryCode": "GT",
            "felCountryReady": True,
        }

    def resolve_item_by_number(self, item_number: str, **_kwargs):
        assert item_number == "NAT00000033"
        return {"id": "item-demurrage", "number": item_number}


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


def demurrage_summary(*, dedicated_attachment: bool = True) -> dict:
    fields = {
        "Estatus de facturación (USD)/": {
            "id": "b436ff28-24d8-4a5a-9f7e-66623401dee1",
            "type": "drop_down",
            "value": 9,
            "type_config": {
                "options": [{"name": "Facturada", "orderindex": 9}]
            },
        },
        "Invoice Currency": {"value": "USD"},
        "Business Central Customer ID": {"value": "customer-current"},
        "Business Central Customer Number": {"value": "C00033"},
        "D&D al cliente (USD)": {
            "id": "e0dce9a5-00f2-4aa1-b563-b997c29136bc",
            "type": "formula",
            "value": "4440",
            "type_config": {"calculation_state": "failed"},
        },
        "Días de D&D": {
            "id": "d5620363-46c1-433f-b6a1-5643d67dc74f",
            "type": "formula",
            "value": "24",
        },
        "Number of Containers": {
            "id": "a05a2c81-2079-4467-9bfe-3723537bd350",
            "value": "1",
        },
        "Corte de D&D": {
            "id": "7cd14623-4ac1-4c03-bcea-50782047f2d6",
            "type": "checkbox",
            "value": "true",
        },
        "Container(s) number(s)/": {"value": "TCLU4945180"},
    }
    if dedicated_attachment:
        fields["Factura D&D al cliente"] = {
            "id": "323c1843-401d-4ba5-92a1-f6fdc8187da0",
            "type": "attachment",
            "value": [{"title": "Factura_ GTFVR0004338.eml"}],
        }
    return {
        "task_id": "86e1c272u",
        "custom_id": "MTMLXGT-26066",
        "name": "GT250103 || MTMLXGT-26066",
        "market": "GT",
        "storage_context_mode": "legacy_task",
        "custom_fields": fields,
    }


def test_demurrage_preview_derives_rate_and_invoices_only_pending_delta() -> None:
    result = prepare_clickup_bc_demurrage_invoice_preview(
        clickup_summary=demurrage_summary(),
        bc_client=FakeDemurrageBCClient(),
        invoice_settings=invoice_settings(),
    )

    assert result["status"] == "dry_run_ready"
    assert result["reference"] == "MTMLXGT-26066-DEM-02"
    assert result["customer_number"] == "C00033"
    assert result["derived_rate"]["daily_rate"] == 185.0
    assert result["proposed_bc_line_payloads"] == [
        {
            "lineType": "Item",
            "lineObjectNumber": "NAT00000033",
            "itemId": "item-demurrage",
            "description": "DEMORA - TCLU4945180",
            "quantity": 15,
            "unitPrice": 185.0,
        }
    ]
    validation = result["demurrage_validation"]
    reconciliation = validation["storage_reconciliation"]
    assert reconciliation["billable_to_date"] == 4440.0
    assert reconciliation["active_invoiced"] == 1665.0
    assert reconciliation["pending_to_invoice"] == 2775.0
    assert reconciliation["pending_container_days"] == 15
    assert validation["warnings"][-1]["reason"] == "historical_customer_changed"


def test_demurrage_preview_blocks_customer_change_without_dedicated_invoice_evidence() -> None:
    result = prepare_clickup_bc_demurrage_invoice_preview(
        clickup_summary=demurrage_summary(dedicated_attachment=False),
        bc_client=FakeDemurrageBCClient(attached=False),
        invoice_settings=invoice_settings(),
    )

    assert result["status"] == "storage_history_customer_mismatch"
    assert result["expected_customer_number"] == "C00033"


def test_demurrage_preview_reports_fully_invoiced() -> None:
    result = prepare_clickup_bc_demurrage_invoice_preview(
        clickup_summary=demurrage_summary(),
        bc_client=FakeDemurrageBCClient(fully_invoiced=True),
        invoice_settings=invoice_settings(),
    )

    assert result["status"] == "fully_invoiced"
    assert result["storage_reconciliation"]["pending_to_invoice"] == 0.0


def test_demurrage_preview_blocks_historical_rate_mismatch() -> None:
    client = FakeDemurrageBCClient()

    def mismatched_lines(_invoice_id: str, **_kwargs):
        return [
            {
                "lineObjectNumber": "NAT00000033",
                "description": "DEMORA",
                "quantity": 9,
                "unitPrice": 180,
                "amountIncludingTax": 1620,
            }
        ]

    client.get_posted_sales_invoice_lines = mismatched_lines
    result = prepare_clickup_bc_demurrage_invoice_preview(
        clickup_summary=demurrage_summary(),
        bc_client=client,
        invoice_settings=invoice_settings(),
    )

    assert result["status"] == "storage_history_rate_mismatch"
    assert result["expected_daily_rate"] == 185.0


def test_demurrage_preview_requires_cut_checkbox() -> None:
    summary = demurrage_summary()
    summary["custom_fields"]["Corte de D&D"]["value"] = None

    result = prepare_clickup_bc_demurrage_invoice_preview(
        clickup_summary=summary,
        bc_client=FakeDemurrageBCClient(),
        invoice_settings=invoice_settings(),
    )

    assert result["status"] == "demurrage_cut_not_ready"


def test_demurrage_preview_blocks_historical_currency_mismatch() -> None:
    client = FakeDemurrageBCClient()
    original_find = client.find_entities

    def find_with_gtq(entity_name: str, **kwargs):
        rows = original_find(entity_name, **kwargs)
        if entity_name == "salesInvoices":
            return [{**row, "currencyCode": "GTQ"} for row in rows]
        return rows

    client.find_entities = find_with_gtq
    result = prepare_clickup_bc_demurrage_invoice_preview(
        clickup_summary=demurrage_summary(dedicated_attachment=False),
        bc_client=client,
        invoice_settings=invoice_settings(),
    )

    assert result["status"] == "storage_history_currency_mismatch"
    assert result["expected_currency"] == "USD"
