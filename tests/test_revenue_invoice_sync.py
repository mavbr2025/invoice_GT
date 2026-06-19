from __future__ import annotations

import base64
from decimal import Decimal

from clickup_integration.revenue_invoice_sync import (
    ClickUpFieldRegistry,
    RevenueInvoiceSyncError,
    RevenueInvoiceSyncSettings,
    build_invoice_task_name,
    find_clickup_tasks_for_invoice,
    map_collection_status,
    prepare_revenue_invoice_sync,
    run_revenue_invoice_sync,
    sync_revenue_invoice,
)


def make_settings(**overrides) -> RevenueInvoiceSyncSettings:
    return RevenueInvoiceSyncSettings(
        workspace_id="8451352",
        market="GT",
        revenue_list_id="901710831940",
        invoicing_list_id="152220606",
        exception_list_id="exception-list",
        default_task_status="vigente",
        incremental_days=14,
        weekly_full_days=120,
        page_size=100,
        max_task_pages=3,
        attach_documents=True,
        field_names={
            "master_bl": ("Master BL Number/",),
            "series": ("Serie",),
            "client_invoice": ("Factura Cliente",),
            "type": ("Type",),
            "date": ("Date",),
            "collection_status": ("Collection Estatus",),
            "currency": ("Currency Invoice",),
            "customer": ("Customer",),
            "carrier": ("Carrier/",),
            "vat_usd": ("VAT (USD)",),
            "total_invoice_usd": ("Total Invoice (USD)",),
            "fx_rate": ("FX Rate",),
            "po": ("PO",),
            "bc_system_id": ("Business Central Invoice ID",),
            "bc_invoice_url": ("Business Central Invoice Link",),
            "invoice_no": ("Business Central Invoice Number",),
        },
        **overrides,
    )


def make_registry() -> ClickUpFieldRegistry:
    return ClickUpFieldRegistry.from_fields(
        [
            dropdown_field(
                "field-status",
                "Collection Estatus",
                ["COLLECTED", "TO COLLECT", "PARTIALLY PAID", "CREDIT NOTE"],
            ),
            dropdown_field("field-currency", "Currency Invoice", ["USD", "GTQ", "EUR"]),
            dropdown_field("field-customer", "Customer", ["DORAL IMPORTACIONES SOCIEDAD ANONIMA"]),
            dropdown_field("field-carrier", "Carrier/", ["ONE", "MAERSK"]),
            dropdown_field("field-type", "Type", ["FACT", "NCRE"]),
            text_field("field-mbl", "Master BL Number/"),
            text_field("field-serie", "Serie"),
            text_field("field-factura", "Factura Cliente"),
            {"id": "field-date", "name": "Date", "type": "date"},
            {"id": "field-vat-usd", "name": "VAT (USD)", "type": "currency"},
            {"id": "field-total-usd", "name": "Total Invoice (USD)", "type": "currency"},
            {"id": "field-fx", "name": "FX Rate", "type": "number"},
            text_field("field-po", "PO"),
            text_field("field-bc-id", "Business Central Invoice ID"),
            text_field("field-link", "Business Central Invoice Link"),
            text_field("field-invoice-no", "Business Central Invoice Number"),
        ]
    )


def dropdown_field(field_id: str, name: str, options: list[str]) -> dict:
    return {
        "id": field_id,
        "name": name,
        "type": "drop_down",
        "type_config": {
            "options": [
                {"id": f"{field_id}-{index}", "name": option, "orderindex": index}
                for index, option in enumerate(options)
            ]
        },
    }


def text_field(field_id: str, name: str) -> dict:
    return {"id": field_id, "name": name, "type": "short_text"}


def make_invoice(**overrides) -> dict:
    invoice = {
        "id": "bc-system-1",
        "number": "GTFVR0003573",
        "customerId": "customer-id-1",
        "customerName": "DORAL IMPORTACIONES SOCIEDAD ANONIMA",
        "customerNumber": "C00010",
        "postingDate": "2026-05-21",
        "documentDate": "2026-05-21",
        "dueDate": "2026-06-20",
        "currencyCode": "USD",
        "totalAmountExcludingTax": "100.00",
        "totalTaxAmount": "12.00",
        "totalAmountIncludingTax": "112.00",
        "remainingAmount": "112.00",
        "externalDocumentNumber": "PO-123",
        "fiscalInvoiceNumberPAC": "9C46F9FF-58D7-4D09-A51B-123456789ABC",
        "numero": "1490504969",
    }
    invoice.update(overrides)
    return invoice


def make_lines() -> list[dict]:
    return [
        {
            "lineNumber": 10000,
            "description": "COORDINACION VIRTUAL DE TRANSPORTE MARITIMO PO PO-123 CARRIER ONE BOOKING ONE123 CONTAINER ONEU1234567",
            "quantity": 1,
            "unitPrice": "100.00",
            "taxAmount": "12.00",
            "amountIncludingTax": "112.00",
        }
    ]


def test_collection_status_mapping() -> None:
    assert map_collection_status(total=Decimal("112"), remaining=Decimal("112")) == "TO COLLECT"
    assert map_collection_status(total=Decimal("112"), remaining=Decimal("30")) == "PARTIALLY PAID"
    assert map_collection_status(total=Decimal("112"), remaining=Decimal("0")) == "COLLECTED"
    assert (
        map_collection_status(
            total=Decimal("112"),
            remaining=Decimal("112"),
            document_type="credit memo",
        )
        == "CREDIT NOTE"
    )


def test_prepare_revenue_invoice_sync_maps_payload() -> None:
    payload = prepare_revenue_invoice_sync(
        invoice=make_invoice(),
        lines=make_lines(),
        customer={"taxRegistrationNumber": "43268536"},
        company_name="MTM LOGIX GUATEMALA",
        bc_invoice_url="https://businesscentral.example/invoice",
        registry=make_registry(),
        settings=make_settings(),
    )

    assert payload["task_name"] == "GTFVR0003573"
    assert payload["collection_status"] == "TO COLLECT"
    assert "# Invoice Lines" in payload["description"]
    assert "43268536" in payload["description"]
    field_values = {field["field_name"]: field["value"] for field in payload["custom_fields"]}
    assert field_values["Collection Estatus"] == "field-status-1"
    assert field_values["Currency Invoice"] == "field-currency-0"
    assert field_values["Customer"] == "field-customer-0"
    assert field_values["Carrier/"] == "field-carrier-0"
    assert field_values["Factura Cliente"] == "1490504969"
    assert field_values["Serie"] == "9C46F9FF"
    assert field_values["PO"] == "PO-123"
    assert field_values["VAT (USD)"] == 12.0
    assert field_values["Total Invoice (USD)"] == 112.0
    assert field_values["FX Rate"] == 1.0
    assert field_values["Type"] == "field-type-0"


def test_missing_dropdown_option_raises_exception() -> None:
    registry = ClickUpFieldRegistry.from_fields(
        [
            dropdown_field("field-status", "Collection Estatus", ["TO COLLECT"]),
            dropdown_field("field-currency", "Currency Invoice", ["GTQ"]),
        ]
    )

    try:
        prepare_revenue_invoice_sync(
            invoice=make_invoice(currencyCode="USD"),
            lines=[],
            customer=None,
            company_name="MTM LOGIX GUATEMALA",
            bc_invoice_url=None,
            registry=registry,
            settings=make_settings(),
        )
    except RevenueInvoiceSyncError as exc:
        assert exc.category == "missing_dropdown_option"
        assert exc.retryable is False
    else:
        raise AssertionError("Expected missing dropdown option to raise")


def test_find_clickup_tasks_for_invoice_filters_exact_invoice() -> None:
    clickup = FakeClickUp(tasks=[{"id": "1", "name": "GTFVR0003573 | CUSTOMER | USD 112.00"}])

    matches = find_clickup_tasks_for_invoice(
        clickup,
        list_id="901710831940",
        invoice_no="GTFVR0003573",
        max_pages=3,
    )

    assert [task["id"] for task in matches] == ["1"]


def test_sync_dry_run_updates_existing_without_duplicate() -> None:
    clickup = FakeClickUp(tasks=[{"id": "existing-task", "name": "GTFVR0003573 | OLD | USD 100.00"}])
    bc = FakeBC()

    result = sync_revenue_invoice(
        invoice=make_invoice(),
        bc=bc,
        clickup=clickup,
        registry=make_registry(),
        settings=make_settings(),
        dry_run=True,
    )

    assert result["status"] == "dry_run"
    assert result["action"] == "update"
    assert result["clickup_task_id"] == "existing-task"
    assert clickup.created_tasks == []


def test_sync_duplicate_clickup_tasks_goes_to_exception() -> None:
    clickup = FakeClickUp(
        tasks=[
            {"id": "task-1", "name": "GTFVR0003573 | CUSTOMER | USD 112.00"},
            {"id": "task-2", "name": "GTFVR0003573 | CUSTOMER COPY | USD 112.00"},
        ]
    )

    result = sync_revenue_invoice(
        invoice=make_invoice(),
        bc=FakeBC(),
        clickup=clickup,
        registry=make_registry(),
        settings=make_settings(),
        dry_run=False,
    )

    assert result["status"] == "failed"
    assert result["error_type"] == "duplicate_clickup_tasks"
    assert clickup.exception_tasks


def test_attachment_failure_does_not_block_task_sync() -> None:
    clickup = FakeClickUp(attachment_error=RuntimeError("upload failed"))
    invoice = make_invoice(pdfBase64=base64.b64encode(b"%PDF-1.4").decode())

    result = sync_revenue_invoice(
        invoice=invoice,
        bc=FakeBC(),
        clickup=clickup,
        registry=make_registry(),
        settings=make_settings(),
        dry_run=False,
    )

    assert result["status"] == "applied"
    assert result["attachment_status"].startswith("failed:")
    assert clickup.created_tasks[0]["name"] == "GTFVR0003573"
    assert clickup.comments


def test_weekly_full_review_reprocesses_without_duplicates() -> None:
    clickup = FakeClickUp(tasks=[{"id": "existing-task", "name": "GTFVR0003573 | OLD | USD 112.00"}])
    bc = FakeBC()

    result = run_revenue_invoice_sync(
        bc=bc,
        clickup=clickup,
        settings=make_settings(),
        dry_run=True,
        full_review=True,
    )

    assert result["sync_type"] == "weekly_full"
    assert result["invoice_count"] == 1
    assert result["results"][0]["action"] == "update"
    assert clickup.created_tasks == []


def test_missing_shipment_task_is_non_blocking() -> None:
    payload = prepare_revenue_invoice_sync(
        invoice=make_invoice(),
        lines=[],
        customer={"taxRegistrationNumber": "43268536"},
        company_name="MTM LOGIX GUATEMALA",
        bc_invoice_url=None,
        registry=make_registry(),
        settings=make_settings(),
    )

    assert payload["mapped"]["connected_shipment_task"] is None
    assert payload["collection_status"] == "TO COLLECT"


def test_build_invoice_task_name_formats_amount() -> None:
    assert (
        build_invoice_task_name(
            invoice_no="GTFVR0003573",
            customer_name="NUEVOS ALMACENES, S.A.",
            currency="GTQ",
            total=Decimal("12500"),
        )
        == "GTFVR0003573"
    )


class FakeBC:
    def get_posted_sales_invoices(self, *, top=None, filters=None, market=None, **kwargs):
        assert market == "GT"
        assert "postingDate ge" in filters
        return [make_invoice()]

    def get_posted_sales_invoice_lines(self, sales_invoice_id: str, *, market: str | None = None):
        assert sales_invoice_id == "bc-system-1"
        assert market == "GT"
        return make_lines()

    def get_gt_registered_invoice_by_number(self, invoice_number: str, *, market: str | None = None):
        assert invoice_number == "GTFVR0003573"
        assert market == "GT"
        return {"numero": "1490504969"}

    def get_customer_ledger_entries_by_document_no(self, document_no: str, *, market: str | None = None):
        assert document_no == "GTFVR0003573"
        assert market == "GT"
        return [{"UUID_Factura": "9C46F9FF-58D7-4D09-A51B-123456789ABC"}]

    def get_customer_by_id(self, customer_id: str, *, market: str | None = None):
        assert customer_id == "customer-id-1"
        assert market == "GT"
        return {"displayName": "DORAL IMPORTACIONES SOCIEDAD ANONIMA", "taxRegistrationNumber": "43268536"}

    def get_company_metadata(self, *, company_id=None, market=None):
        assert market == "GT"
        return {"name": "MTM LOGIX GUATEMALA"}

    def build_sales_invoice_url(self, *, company_name: str, invoice_number: str):
        return f"https://businesscentral.example/{company_name}/{invoice_number}"


class FakeClickUp:
    def __init__(self, *, tasks: list[dict] | None = None, attachment_error: Exception | None = None) -> None:
        self.tasks = tasks or []
        self.attachment_error = attachment_error
        self.created_tasks: list[dict] = []
        self.updated_tasks: list[dict] = []
        self.field_updates: list[dict] = []
        self.comments: list[dict] = []
        self.exception_tasks: list[dict] = []

    def get_list_tasks(self, list_id: str, *, include_closed=False, page=0, query=None, **kwargs):
        if page > 0:
            return {"tasks": []}
        if query:
            return {"tasks": [task for task in self.tasks if query in task["name"]]}
        return {"tasks": list(self.tasks)}

    def get_list_custom_fields(self, list_id: str):
        return {
            "fields": list(make_registry().fields_by_name.values()),
        }

    def create_task(self, list_id: str, *, name: str, description: str | None = None, status: str | None = None):
        task = {"id": f"created-{len(self.created_tasks) + 1}", "name": name, "description": description, "status": status}
        if list_id == "exception-list":
            self.exception_tasks.append(task)
        else:
            self.created_tasks.append(task)
        return task

    def update_task(self, task_id: str, **kwargs):
        self.updated_tasks.append({"id": task_id, **kwargs})
        return {"id": task_id, **kwargs}

    def set_task_custom_field_value(self, task_id: str, field_id: str, value):
        self.field_updates.append({"task_id": task_id, "field_id": field_id, "value": value})
        return {}

    def create_task_comment(self, task_id: str, *, comment_text: str, notify_all: bool = False):
        self.comments.append({"task_id": task_id, "comment_text": comment_text, "notify_all": notify_all})
        return {}

    def attach_file_to_task(self, task_id: str, local_path, **kwargs):
        if self.attachment_error:
            raise self.attachment_error
        return {"id": "attachment-1"}
