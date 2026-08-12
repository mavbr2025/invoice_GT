from __future__ import annotations

from types import SimpleNamespace

from clickup_integration.invoice_sync import InvoiceAutomationSettings
from clickup_integration.storage_invoice_sync import (
    StorageInvoiceSettings,
    build_clickup_storage_invoice_context,
    issue_clickup_bc_storage_invoice,
    prepare_clickup_bc_storage_invoice_preview,
)


class FakeStorageBCClient:
    def __init__(
        self,
        *,
        legacy_invoice: dict | None = None,
        invoices_by_reference: dict[str, dict] | None = None,
        history_invoices: list[dict] | None = None,
        lines_by_invoice_id: dict[str, list[dict]] | None = None,
    ) -> None:
        self.settings = SimpleNamespace()
        self.legacy_invoice = legacy_invoice
        self.invoices_by_reference = invoices_by_reference or {}
        self.history_invoices = history_invoices or []
        self.lines_by_invoice_id = lines_by_invoice_id or {}

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
        if "contains(externalDocumentNumber" in filters:
            return self.history_invoices
        for reference, invoice in self.invoices_by_reference.items():
            if f"externalDocumentNumber eq '{reference}'" in filters:
                return [invoice]
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
        if invoice_id in self.lines_by_invoice_id:
            return self.lines_by_invoice_id[invoice_id]
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


def aggregated_storage_summary() -> dict:
    summary = storage_summary(amount="108")
    summary["task_id"] = "86e1k2ptx"
    summary["custom_id"] = "MTMLXGT-26217"
    summary["name"] = "PO I-GM26-035 - MTMLXGT-26217"
    summary["storage_context_mode"] = "parent_subtasks"
    summary["storage_entries"] = [
        {
            "task_id": "86e2rk9b1",
            "custom_id": "MTMLXGT-32186",
            "container": "FFAU6506597",
            "amount": 54,
            "days": 2,
            "containers": 1,
            "cut": True,
            "amount_formula_state": "failed",
        },
        {
            "task_id": "86e2rk9b9",
            "custom_id": "MTMLXGT-32187",
            "container": "ONEU0145016",
            "amount": 81,
            "days": 3,
            "containers": 1,
            "cut": True,
            "amount_formula_state": "failed",
        },
    ]
    return summary


def cumulative_storage_summary() -> dict:
    summary = storage_summary(amount="972")
    summary["task_id"] = "86e1c272u"
    summary["custom_id"] = "MTMLXGT-26066"
    summary["name"] = "GT250103 || MTMLXGT-26066"
    summary["custom_fields"]["Días de almacenaje incurridos"]["value"] = "36"
    summary["custom_fields"]["Number of Containers"]["value"] = "1"
    summary["custom_fields"]["Factura almacenaje al cliente"] = {
        "id": "c4994b71-cff2-46a3-b169-08f5019e0a93",
        "type": "attachment",
        "value": [{"title": "Factura_GTFVR0004336.pdf"}],
    }
    return summary


def raw_field(field_id: str, name: str, value, field_type: str = "number") -> dict:
    return {"id": field_id, "name": name, "type": field_type, "value": value}


def test_storage_context_moves_child_request_to_parent_and_collects_siblings() -> None:
    requested = {
        "id": "86e2rk9b9",
        "custom_id": "MTMLXGT-32187",
        "name": "ONEU0145016",
        "parent": "86e1k2ptx",
        "status": {"status": "Facturada"},
        "custom_fields": [],
    }
    parent = {
        "id": "86e1k2ptx",
        "custom_id": "MTMLXGT-26217",
        "name": "PO I-GM26-035 - MTMLXGT-26217",
        "status": {"status": "Facturada"},
        "custom_fields": [],
        "subtasks": [
            {
                "id": "86e2rk9b1",
                "custom_id": "MTMLXGT-32186",
                "name": "FFAU6506597",
                "status": {"status": "Facturada"},
                "custom_fields": [
                    raw_field("16edb6b2-ba0c-4a1e-94f0-f3f511d2f647", "Almacenaje al cliente (USD)", 54),
                    raw_field("edcdf91d-ff83-44a9-a869-dbeaff186ce4", "Días de almacenaje incurridos", 2),
                    raw_field("a05a2c81-2079-4467-9bfe-3723537bd350", "Number of Containers", 1),
                    raw_field("f8bb0632-c52d-43ed-b9a8-02c8d3635e9a", "Corte de almacenaje", True, "checkbox"),
                ],
            },
            {
                "id": "86e2rk9b9",
                "custom_id": "MTMLXGT-32187",
                "name": "ONEU0145016",
                "status": {"status": "Facturada"},
                "custom_fields": [
                    raw_field("16edb6b2-ba0c-4a1e-94f0-f3f511d2f647", "Almacenaje al cliente (USD)", 81),
                    raw_field("edcdf91d-ff83-44a9-a869-dbeaff186ce4", "Días de almacenaje incurridos", 3),
                    raw_field("a05a2c81-2079-4467-9bfe-3723537bd350", "Number of Containers", 1),
                    raw_field("f8bb0632-c52d-43ed-b9a8-02c8d3635e9a", "Corte de almacenaje", True, "checkbox"),
                ],
            },
        ],
    }

    context = build_clickup_storage_invoice_context(
        requested_task=requested,
        invoice_task=parent,
        storage_settings=StorageInvoiceSettings(),
    )

    assert context["task_id"] == "86e1k2ptx"
    assert context["custom_id"] == "MTMLXGT-26217"
    assert context["storage_requested_custom_id"] == "MTMLXGT-32187"
    assert [(entry["container"], entry["days"], entry["amount"]) for entry in context["storage_entries"]] == [
        ("FFAU6506597", 2, 54.0),
        ("ONEU0145016", 3, 81.0),
    ]


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


def test_storage_preview_aggregates_parent_subtasks_with_individual_days() -> None:
    result = prepare_clickup_bc_storage_invoice_preview(
        clickup_summary=aggregated_storage_summary(),
        bc_client=FakeStorageBCClient(),
        invoice_settings=invoice_settings(),
    )

    assert result["status"] == "dry_run_ready"
    assert result["reference"] == "MTMLXGT-26217-ALM"
    lines = result["proposed_bc_line_payloads"]
    assert [(line["quantity"], line["unitPrice"]) for line in lines] == [(2, 27), (3, 27)]
    assert [line["description"] for line in lines] == [
        "ALMACENAJES EN PUERTO - FFAU6506597",
        "ALMACENAJES EN PUERTO - ONEU0145016",
    ]
    assert sum(line["quantity"] * line["unitPrice"] for line in lines) == 135
    assert result["storage_validation"]["aggregation_mode"] == "parent_subtasks"
    assert result["storage_validation"]["container_days"] == 5


def test_storage_preview_blocks_until_active_split_invoices_are_cancelled() -> None:
    invoices = {
        "MTMLXGT-32186-ALM": {
            "id": "posted-storage-1",
            "number": "GTFVR0004523",
            "externalDocumentNumber": "MTMLXGT-32186-ALM",
            "customerNumber": "C00102",
            "totalAmountIncludingTax": 54,
        },
        "MTMLXGT-32187-ALM": {
            "id": "posted-storage-2",
            "number": "GTFVR0004524",
            "externalDocumentNumber": "MTMLXGT-32187-ALM",
            "customerNumber": "C00102",
            "totalAmountIncludingTax": 81,
        },
    }
    result = prepare_clickup_bc_storage_invoice_preview(
        clickup_summary=aggregated_storage_summary(),
        bc_client=FakeStorageBCClient(invoices_by_reference=invoices),
        invoice_settings=invoice_settings(),
    )

    assert result["status"] == "replacement_required"
    assert result["replacement_reference"] == "MTMLXGT-26217-ALM"
    assert [row["number"] for row in result["invoices_to_cancel"]] == [
        "GTFVR0004523",
        "GTFVR0004524",
    ]
    assert sum(
        line["quantity"] * line["unitPrice"]
        for line in result["proposed_bc_line_payloads"]
    ) == 135


def test_storage_preview_ignores_split_invoices_with_canceled_status() -> None:
    invoices = {
        "MTMLXGT-32186-ALM": {
            "id": "posted-storage-1",
            "number": "GTFVR0004523",
            "status": "Canceled",
            "externalDocumentNumber": "MTMLXGT-32186-ALM",
            "customerNumber": "C00102",
            "totalAmountIncludingTax": 54,
        },
        "MTMLXGT-32187-ALM": {
            "id": "posted-storage-2",
            "number": "GTFVR0004524",
            "status": "Canceled",
            "externalDocumentNumber": "MTMLXGT-32187-ALM",
            "customerNumber": "C00102",
            "totalAmountIncludingTax": 81,
        },
    }
    result = prepare_clickup_bc_storage_invoice_preview(
        clickup_summary=aggregated_storage_summary(),
        bc_client=FakeStorageBCClient(invoices_by_reference=invoices),
        invoice_settings=invoice_settings(),
    )

    assert result["status"] == "dry_run_ready"
    assert result["reference"] == "MTMLXGT-26217-ALM"


def test_storage_preview_invoices_only_cumulative_pending_delta() -> None:
    history_invoice = {
        "id": "storage-history-1",
        "number": "GTFVR0004336",
        "externalDocumentNumber": "GT250103 || MTMLXGT-26066",
        "customerNumber": "C00102",
        "customerName": "CUSTOMER",
        "currencyCode": "USD",
        "status": "Open",
    }
    history_lines = {
        "storage-history-1": [
            {
                "lineType": "Item",
                "lineObjectNumber": "NAT00000034",
                "description": "ALMACENAJES",
                "quantity": 22,
                "unitPrice": 27,
                "amountIncludingTax": 594,
            }
        ]
    }
    result = prepare_clickup_bc_storage_invoice_preview(
        clickup_summary=cumulative_storage_summary(),
        bc_client=FakeStorageBCClient(
            history_invoices=[history_invoice],
            lines_by_invoice_id=history_lines,
        ),
        invoice_settings=invoice_settings(),
    )

    assert result["status"] == "dry_run_ready"
    assert result["reference"] == "MTMLXGT-26066-ALM-02"
    assert result["proposed_bc_line_payloads"] == [
        {
            "lineType": "Item",
            "lineObjectNumber": "NAT00000034",
            "itemId": "item-storage",
            "description": "ALMACENAJES EN PUERTO - Container 1",
            "quantity": 14,
            "unitPrice": 27.0,
        }
    ]
    reconciliation = result["storage_validation"]["storage_reconciliation"]
    assert reconciliation["billable_to_date"] == 972.0
    assert reconciliation["active_invoiced"] == 594.0
    assert reconciliation["pending_to_invoice"] == 378.0
    assert reconciliation["active_invoiced_container_days"] == 22
    assert reconciliation["pending_container_days"] == 14


def test_storage_preview_reports_fully_invoiced_without_new_payload() -> None:
    history_invoice = {
        "id": "storage-history-full",
        "number": "GTFVR0004999",
        "externalDocumentNumber": "MTMLXGT-26066-ALM",
        "customerNumber": "C00102",
        "status": "Open",
    }
    result = prepare_clickup_bc_storage_invoice_preview(
        clickup_summary=cumulative_storage_summary(),
        bc_client=FakeStorageBCClient(
            history_invoices=[history_invoice],
            lines_by_invoice_id={
                "storage-history-full": [
                    {
                        "lineObjectNumber": "NAT00000034",
                        "description": "ALMACENAJES",
                        "quantity": 36,
                        "unitPrice": 27,
                        "amountIncludingTax": 972,
                    }
                ]
            },
        ),
        invoice_settings=invoice_settings(),
    )

    assert result["status"] == "fully_invoiced"
    assert result["storage_reconciliation"]["pending_to_invoice"] == 0.0


def test_storage_preview_blocks_historical_customer_mismatch() -> None:
    history_invoice = {
        "id": "storage-history-wrong-customer",
        "number": "GTFVR0004336",
        "externalDocumentNumber": "GT250103 || MTMLXGT-26066",
        "customerNumber": "C99999",
        "currencyCode": "USD",
        "status": "Open",
    }
    result = prepare_clickup_bc_storage_invoice_preview(
        clickup_summary=cumulative_storage_summary(),
        bc_client=FakeStorageBCClient(
            history_invoices=[history_invoice],
            lines_by_invoice_id={
                "storage-history-wrong-customer": [
                    {
                        "lineObjectNumber": "NAT00000034",
                        "description": "ALMACENAJES",
                        "quantity": 22,
                        "unitPrice": 27,
                        "amountIncludingTax": 594,
                    }
                ]
            },
        ),
        invoice_settings=invoice_settings(),
    )

    assert result["status"] == "storage_history_customer_mismatch"
    assert result["expected_customer_number"] == "C00102"


def test_storage_preview_blocks_when_active_history_exceeds_billable_cut() -> None:
    history_invoice = {
        "id": "storage-history-over",
        "number": "GTFVR0004998",
        "externalDocumentNumber": "MTMLXGT-26066-ALM",
        "customerNumber": "C00102",
        "status": "Open",
    }
    result = prepare_clickup_bc_storage_invoice_preview(
        clickup_summary=cumulative_storage_summary(),
        bc_client=FakeStorageBCClient(
            history_invoices=[history_invoice],
            lines_by_invoice_id={
                "storage-history-over": [
                    {
                        "lineObjectNumber": "NAT00000034",
                        "description": "ALMACENAJES",
                        "quantity": 37,
                        "unitPrice": 27,
                        "amountIncludingTax": 999,
                    }
                ]
            },
        ),
        invoice_settings=invoice_settings(),
    )

    assert result["status"] == "storage_overinvoiced"
    assert result["storage_reconciliation"]["pending_to_invoice"] == -27.0


def test_storage_preview_excludes_canceled_history_from_invoiced_total() -> None:
    history_invoice = {
        "id": "storage-history-canceled",
        "number": "GTFVR0004336",
        "externalDocumentNumber": "GT250103 || MTMLXGT-26066",
        "customerNumber": "C00102",
        "status": "Canceled",
    }
    result = prepare_clickup_bc_storage_invoice_preview(
        clickup_summary=cumulative_storage_summary(),
        bc_client=FakeStorageBCClient(
            history_invoices=[history_invoice],
            lines_by_invoice_id={
                "storage-history-canceled": [
                    {
                        "lineObjectNumber": "NAT00000034",
                        "description": "ALMACENAJES",
                        "quantity": 22,
                        "unitPrice": 27,
                        "amountIncludingTax": 594,
                    }
                ]
            },
        ),
        invoice_settings=invoice_settings(),
    )

    assert result["status"] == "dry_run_ready"
    assert result["reference"] == "MTMLXGT-26066-ALM"
    assert result["proposed_bc_line_payloads"][0]["quantity"] == 36
    reconciliation = result["storage_validation"]["storage_reconciliation"]
    assert reconciliation["active_invoiced"] == 0.0
    assert [row["number"] for row in reconciliation["canceled_storage_invoices"]] == [
        "GTFVR0004336"
    ]


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
