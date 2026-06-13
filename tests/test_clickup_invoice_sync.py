from datetime import date
from types import SimpleNamespace

from clickup_integration.invoice_sync import (
    InvoiceChargeMapping,
    InvoiceAutomationSettings,
    apply_clickup_bc_sales_invoice,
    prepare_clickup_bc_sales_invoice_preview,
    prepare_clickup_invoice_status_transition,
)


class FakeBCInvoiceClient:
    def __init__(self, *, existing_invoices: list[dict] | None = None) -> None:
        self.settings = SimpleNamespace()
        self.existing_invoices = existing_invoices or []
        self.created_headers: list[dict] = []
        self.created_lines: list[dict] = []
        self.customer_name_lookups: list[str] = []

    def find_entities(self, entity_name: str, *, filters: str, top: int = 1, company_id=None, market=None):
        assert entity_name == "salesInvoices"
        assert market == "GT"
        assert "externalDocumentNumber eq 'PO-7788" in filters
        return list(self.existing_invoices)

    def resolve_account_by_number(self, account_number: str, *, market: str | None = None):
        assert market == "GT"
        return {"id": f"acc-{account_number}", "number": account_number}

    def resolve_item_by_number(self, item_number: str, *, market: str | None = None):
        assert market == "GT"
        return {"id": f"item-{item_number}", "number": item_number}

    def resolve_customer_by_name(self, customer_name: str, *, market: str | None = None):
        assert market == "GT"
        self.customer_name_lookups.append(customer_name)
        if customer_name == "MASESA":
            return {"id": "customer-masesa-id", "number": "C-MASESA", "displayName": "MASESA"}
        return None

    def create_sales_invoice(self, payload: dict, *, company_id=None, market=None):
        assert market == "GT"
        self.created_headers.append(payload)
        return {"id": "invoice-id-1", "number": "SI-0001", **payload}

    def create_sales_invoice_line(self, sales_invoice_id: str, payload: dict, *, company_id=None, market=None):
        assert market == "GT"
        assert sales_invoice_id == "invoice-id-1"
        self.created_lines.append(payload)
        return {"id": f"line-{len(self.created_lines)}", **payload}


def make_settings() -> InvoiceAutomationSettings:
    return InvoiceAutomationSettings(
        ready_status="Listo para facturar",
        ok_finops_status="OK Finops",
        eta_horizon_days=10,
        supported_market="GT",
        supported_currency="USD",
        invoice_status_field_names=("Estatus de facturación (USD)/",),
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
        freight_account_number="4100",
        inland_account_number="4200",
        destination_account_number="4300",
    )


def make_clickup_summary(*, status: str) -> dict:
    return {
        "task_id": "task-7788",
        "custom_id": "MTM-7788",
        "status": status,
        "market": "GT",
        "due_date": "2026-04-15",
        "custom_fields": {
            "ETA": {"value": "2026-04-15"},
            "Invoice Currency": {"value": "USD"},
            "Business Central Customer ID": {"value": "customer-id-1"},
            "Business Central Customer Number": {"value": "C00067"},
            "Business Central Invoice Number": {"id": "field-invoice-number"},
            "Business Central Invoice ID": {"id": "field-invoice-id"},
            "Reference": {"value": "PO-7788"},
            "Freight": {"value": "100.50"},
            "Inland": {"value": "0"},
            "Destination Charges": {"value": "45.00"},
        },
    }


def test_prepare_clickup_invoice_status_transition_ready() -> None:
    result = prepare_clickup_invoice_status_transition(
        clickup_summary=make_clickup_summary(status="OK Finops"),
        settings=make_settings(),
        today=date(2026, 4, 8),
    )

    assert result["status"] == "ready_to_update"
    assert result["target_status"] == "Listo para facturar"
    assert result["eta_date"] == "2026-04-15"


def test_prepare_clickup_invoice_status_transition_uses_eta_field_id() -> None:
    settings = InvoiceAutomationSettings(
        **{
            **make_settings().__dict__,
            "eta_field_names": ("Missing ETA",),
            "eta_field_ids": ("field-eta-id",),
        }
    )
    summary = make_clickup_summary(status="OK Finops")
    summary["due_date"] = None
    summary["custom_fields"].pop("ETA")
    summary["custom_fields"]["ETA/"] = {
        "id": "field-eta-id",
        "value": "2026-04-15",
    }

    result = prepare_clickup_invoice_status_transition(
        clickup_summary=summary,
        settings=settings,
        today=date(2026, 4, 8),
    )

    assert result["status"] == "ready_to_update"
    assert result["eta_date"] == "2026-04-15"


def test_prepare_clickup_bc_sales_invoice_preview_requires_customer() -> None:
    summary = make_clickup_summary(status="Listo para facturar")
    summary["custom_fields"].pop("Business Central Customer ID")
    summary["custom_fields"].pop("Business Central Customer Number")

    result = prepare_clickup_bc_sales_invoice_preview(
        clickup_summary=summary,
        bc_client=FakeBCInvoiceClient(),
        settings=make_settings(),
        today=date(2026, 4, 8),
    )

    assert result["status"] == "missing_required_fields"
    assert "Business Central Customer ID or Business Central Customer Number" in result["missing_fields"]


def test_prepare_clickup_bc_sales_invoice_preview_resolves_customer_from_clickup_dropdown() -> None:
    settings = InvoiceAutomationSettings(
        **{
            **make_settings().__dict__,
            "bc_customer_name_field_names": ("Invoice to (Consignee's name)",),
            "bc_customer_name_field_ids": ("field-customer-name",),
        }
    )
    summary = make_clickup_summary(status="Listo para facturar")
    summary["custom_fields"].pop("Business Central Customer ID")
    summary["custom_fields"].pop("Business Central Customer Number")
    summary["custom_fields"]["Invoice to (Consignee's name)"] = {
        "id": "field-customer-name",
        "value": 115,
        "type": "drop_down",
        "type_config": {
            "options": [
                {"id": "customer-masesa-option", "name": "MASESA", "orderindex": 115},
            ]
        },
    }
    bc_client = FakeBCInvoiceClient()

    result = prepare_clickup_bc_sales_invoice_preview(
        clickup_summary=summary,
        bc_client=bc_client,
        settings=settings,
        today=date(2026, 4, 8),
    )

    assert result["status"] == "dry_run_ready"
    assert result["customer_id"] == "customer-masesa-id"
    assert result["customer_number"] == "C-MASESA"
    assert result["customer_resolution"]["status"] == "resolved"
    assert bc_client.customer_name_lookups == ["MASESA"]


def test_prepare_clickup_bc_sales_invoice_preview_blocks_duplicates() -> None:
    result = prepare_clickup_bc_sales_invoice_preview(
        clickup_summary=make_clickup_summary(status="Listo para facturar"),
        bc_client=FakeBCInvoiceClient(
            existing_invoices=[{"id": "existing-id", "number": "SI-0009", "externalDocumentNumber": "PO-7788"}]
        ),
        settings=make_settings(),
        today=date(2026, 4, 8),
    )

    assert result["status"] == "duplicate_invoice"
    assert result["existing_invoice"]["number"] == "SI-0009"


def test_apply_clickup_bc_sales_invoice_creates_header_and_lines() -> None:
    bc_client = FakeBCInvoiceClient()

    result = apply_clickup_bc_sales_invoice(
        clickup_summary=make_clickup_summary(status="Listo para facturar"),
        bc_client=bc_client,
        settings=make_settings(),
        today=date(2026, 4, 8),
    )

    assert result["status"] == "applied"
    assert result["created_invoice"]["number"] == "SI-0001"
    assert bc_client.created_headers[0]["currencyCode"] == "USD"
    assert bc_client.created_headers[0]["externalDocumentNumber"] == "PO-7788"
    assert bc_client.created_headers[0]["dueDate"] == "2026-04-15"
    assert len(bc_client.created_lines) == 2
    assert bc_client.created_lines[0]["lineObjectNumber"] == "4100"
    assert bc_client.created_lines[0]["unitPrice"] == 100.5
    assert bc_client.created_lines[1]["lineObjectNumber"] == "4300"
    assert bc_client.created_lines[1]["unitPrice"] == 45.0
    assert result["invoice_writeback"]["bc_invoice_number"] == "SI-0001"
    assert result["invoice_writeback"]["bc_invoice_id"] == "invoice-id-1"
    assert result["invoice_writeback"]["field_ids"]["invoice_number"] == "field-invoice-number"
    assert result["invoice_writeback"]["field_ids"]["invoice_id"] == "field-invoice-id"


def test_prepare_clickup_bc_sales_invoice_preview_uses_charge_mapping_items() -> None:
    settings = InvoiceAutomationSettings(
        **{
            **make_settings().__dict__,
            "charge_mappings": (
                InvoiceChargeMapping(
                    charge_name="Freight (Ocean/Truck/Air)",
                    clickup_field_name="Freight (Ocean/Truck/Air)",
                    clickup_field_id="field-freight",
                    bc_item_number="INT000000026",
                    bc_description="TRANSPORTE MARITIMO",
                    tax_group="NO IVA",
                ),
                InvoiceChargeMapping(
                    charge_name="Destination Charges",
                    clickup_field_name="Destination Charges",
                    clickup_field_id="field-destination",
                    bc_item_number="NAT00000028",
                    bc_description="DESTINATION CHARGES",
                    tax_group="IVA 12",
                ),
            ),
        }
    )
    summary = make_clickup_summary(status="Listo para facturar")
    summary["custom_fields"]["Freight (Ocean/Truck/Air)"] = {
        "id": "field-freight",
        "value": "100.50",
    }
    summary["custom_fields"]["Destination Charges"]["id"] = "field-destination"

    result = prepare_clickup_bc_sales_invoice_preview(
        clickup_summary=summary,
        bc_client=FakeBCInvoiceClient(),
        settings=settings,
        today=date(2026, 4, 8),
    )

    assert result["status"] == "dry_run_ready"
    assert result["invoice_count"] == 2
    assert result["invoice_groups"] == ["INT", "NAT"]
    assert result["proposed_bc_invoices"][0]["proposed_bc_payload"]["externalDocumentNumber"] == "PO-7788-INT"
    assert result["proposed_bc_invoices"][1]["proposed_bc_payload"]["externalDocumentNumber"] == "PO-7788-NAT"
    assert result["proposed_bc_invoices"][0]["total"] == 100.5
    assert result["proposed_bc_invoices"][1]["total"] == 45.0
    assert len(result["proposed_bc_line_payloads"]) == 2
    assert result["proposed_bc_line_payloads"][0]["lineType"] == "Item"
    assert result["proposed_bc_line_payloads"][0]["lineObjectNumber"] == "INT000000026"
    assert result["proposed_bc_line_payloads"][0]["itemId"] == "item-INT000000026"
    assert result["proposed_bc_line_payloads"][1]["lineObjectNumber"] == "NAT00000028"
    assert result["line_sources"][0]["source_field_id"] == "field-freight"


def test_prepare_clickup_bc_sales_invoice_preview_adds_shipment_metadata_for_template() -> None:
    settings = InvoiceAutomationSettings(
        **{
            **make_settings().__dict__,
            "charge_mappings": (
                InvoiceChargeMapping(
                    charge_name="Freight (Ocean/Truck/Air)",
                    clickup_field_name="Freight (Ocean/Truck/Air)",
                    clickup_field_id="field-freight",
                    bc_item_number="INT000000026",
                    bc_description="TRANSPORTE MARITIMO",
                    tax_group="NO IVA",
                ),
            ),
        }
    )
    summary = make_clickup_summary(status="Listo para facturar")
    summary["name"] = "CI-20260323"
    summary["custom_fields"]["Freight (Ocean/Truck/Air)"] = {
        "id": "field-freight",
        "value": "100.50",
    }
    summary["custom_fields"]["Booking number/"] = {"value": "TPEG23916500"}
    summary["custom_fields"]["Container(s) number(s)/"] = {"value": "TLLU6047125"}

    result = prepare_clickup_bc_sales_invoice_preview(
        clickup_summary=summary,
        bc_client=FakeBCInvoiceClient(),
        settings=settings,
        today=date(2026, 4, 8),
    )

    assert result["status"] == "dry_run_ready"
    assert result["shipment_metadata"] == {
        "shipment_number": "CI-20260323",
        "booking": "TPEG23916500",
        "containers": "TLLU6047125",
    }
    assert result["proposed_bc_payload"]["customerPurchaseOrderReference"] == "CI-20260323"
    assert len(result["proposed_bc_line_payloads"]) == 1
    metadata_line = result["proposed_bc_invoices"][0]["proposed_bc_line_payloads"][0]
    assert metadata_line == {
        "lineType": "Comment",
        "description": "MTM META BOOKING TPEG23916500 CONTAINER TLLU6047125",
    }


def test_prepare_clickup_bc_sales_invoice_preview_uses_custom_invoice_status() -> None:
    summary = make_clickup_summary(status="por arribar")
    summary["custom_fields"]["Estatus de facturación (USD)/"] = {
        "id": "field-invoice-status",
        "value": 1,
        "type_config": {
            "options": [
                {"id": "status-ok", "name": "OK Fin-Ops", "orderindex": 0},
                {"id": "status-ready", "name": "Listo para facturar", "orderindex": 1},
            ]
        },
    }

    result = prepare_clickup_bc_sales_invoice_preview(
        clickup_summary=summary,
        bc_client=FakeBCInvoiceClient(),
        settings=make_settings(),
        today=date(2026, 4, 8),
    )

    assert result["status"] == "dry_run_ready"
    assert result["task_status"] == "Listo para facturar"
    assert result["status_source"] == "custom_field"


def test_prepare_clickup_bc_sales_invoice_preview_defaults_currency_to_usd() -> None:
    summary = make_clickup_summary(status="Listo para facturar")
    summary["custom_fields"]["Invoice Currency"]["value"] = None
    summary["custom_fields"]["Currency"] = {"value": None}

    result = prepare_clickup_bc_sales_invoice_preview(
        clickup_summary=summary,
        bc_client=FakeBCInvoiceClient(),
        settings=make_settings(),
        today=date(2026, 4, 8),
    )

    assert result["status"] == "dry_run_ready"
    assert result["currency"] == "USD"
    assert result["proposed_bc_payload"]["currencyCode"] == "USD"
