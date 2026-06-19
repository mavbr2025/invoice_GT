from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from business_central_client.client import BusinessCentralClient
from clickup_integration.client import ClickUpClient
from clickup_integration.writeback import resolve_clickup_dropdown_option_id


logger = logging.getLogger(__name__)

DEFAULT_WORKSPACE_ID = "8451352"
DEFAULT_REVENUE_GT_LIST_ID = "901710831940"
DEFAULT_INVOICING_LIST_ID = "152220606"
REVENUE_GT_FIELD_IDS = {
    "master_bl": "8f9d6623-4723-482b-84ba-180dfba29643",
    "series": "b962ce3f-5c42-4242-9d0f-edbf1884d517",
    "client_invoice": "8fd7f415-555d-463a-8160-a99afb3fe293",
    "type": "3186b9a9-298a-4c2d-8521-e440e8afb99a",
    "date": "127528e0-3e2b-4ed7-b68e-ac5e47e8d2fa",
    "customer_no": "fd1bbe61-4874-4221-9d90-305d48f38937",
    "customer": "1f98fcd6-adb2-4829-83e2-8bbdcb22037a",
    "vat_usd": "33abbf83-ab8d-42a9-9788-668569a596cd",
    "total_invoice_usd": "a60cc882-a3e3-41a8-9e97-b701800b2936",
    "currency": "1a235fa5-dfef-41c3-9b98-003ec526a385",
    "fx_rate": "7c0d0b4c-61aa-4fb8-ae4a-b5e47b033fd8",
    "revenue_recognition": "4f593074-54a5-4c19-a2f6-d24413dcbad6",
    "collection_status": "6b8e94a6-272e-4a8d-b634-bd31974f73c9",
    "po": "4c2b82d7-9ce7-4ea9-bdbb-603a3b84f387",
    "carrier": "49d677fc-e828-41b9-a6f3-2acf65e50ad2",
    "bc_invoice_url": "47d7bfd5-eb15-4187-b1ce-46b68f5edd18",
}


class RevenueInvoiceSyncError(Exception):
    def __init__(
        self,
        message: str,
        *,
        category: str = "sync_error",
        invoice_no: str | None = None,
        bc_system_id: str | None = None,
        retryable: bool = True,
        payload_summary: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.invoice_no = invoice_no
        self.bc_system_id = bc_system_id
        self.retryable = retryable
        self.payload_summary = payload_summary or {}


@dataclass(frozen=True)
class RevenueInvoiceSyncSettings:
    workspace_id: str = DEFAULT_WORKSPACE_ID
    market: str = "GT"
    revenue_list_id: str = DEFAULT_REVENUE_GT_LIST_ID
    invoicing_list_id: str = DEFAULT_INVOICING_LIST_ID
    exception_list_id: str | None = None
    default_task_status: str = "vigente"
    incremental_days: int = 14
    weekly_full_days: int = 120
    page_size: int = 100
    max_task_pages: int = 10
    attach_documents: bool = True
    field_names: dict[str, tuple[str, ...]] = field(default_factory=dict)
    field_ids: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "RevenueInvoiceSyncSettings":
        return cls(
            workspace_id=os.getenv("CLICKUP_REVENUE_GT_WORKSPACE_ID", DEFAULT_WORKSPACE_ID).strip()
            or DEFAULT_WORKSPACE_ID,
            market=os.getenv("BC_REVENUE_GT_MARKET", "GT").strip().upper() or "GT",
            revenue_list_id=os.getenv(
                "CLICKUP_REVENUE_GT_LIST_ID",
                DEFAULT_REVENUE_GT_LIST_ID,
            ).strip()
            or DEFAULT_REVENUE_GT_LIST_ID,
            invoicing_list_id=os.getenv(
                "CLICKUP_REVENUE_GT_INVOICING_LIST_ID",
                DEFAULT_INVOICING_LIST_ID,
            ).strip()
            or DEFAULT_INVOICING_LIST_ID,
            exception_list_id=os.getenv("CLICKUP_REVENUE_GT_EXCEPTION_LIST_ID", "").strip()
            or None,
            default_task_status=os.getenv("CLICKUP_REVENUE_GT_DEFAULT_STATUS", "vigente").strip()
            or "vigente",
            incremental_days=_env_int("BC_REVENUE_GT_INCREMENTAL_DAYS", default=14),
            weekly_full_days=_env_int("BC_REVENUE_GT_WEEKLY_FULL_DAYS", default=120),
            page_size=_env_int("BC_REVENUE_GT_PAGE_SIZE", default=100),
            max_task_pages=_env_int("CLICKUP_REVENUE_GT_MAX_TASK_PAGES", default=10),
            attach_documents=_env_bool("CLICKUP_REVENUE_GT_ATTACH_DOCUMENTS", default=True),
            field_names=_field_names_from_env(),
            field_ids=_field_ids_from_env(),
        )


@dataclass(frozen=True)
class ClickUpFieldRegistry:
    fields_by_name: dict[str, dict[str, Any]]
    fields_by_id: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def from_clickup_list(cls, clickup: ClickUpClient, list_id: str) -> "ClickUpFieldRegistry":
        payload = clickup.get_list_custom_fields(list_id)
        fields = payload.get("fields") or payload.get("custom_fields") or []
        return cls.from_fields(fields)

    @classmethod
    def from_fields(cls, fields: list[dict[str, Any]]) -> "ClickUpFieldRegistry":
        return cls(
            fields_by_name={field.get("name", ""): field for field in fields if field.get("name")},
            fields_by_id={field.get("id", ""): field for field in fields if field.get("id")},
        )

    def find(self, names: tuple[str, ...] | list[str], field_id: str | None = None) -> dict[str, Any] | None:
        if field_id:
            field = self.fields_by_id.get(field_id)
            if field:
                return field
        for name in names:
            field = self.fields_by_name.get(name)
            if field:
                return field
        return None

    def resolve_dropdown(self, field: dict[str, Any], label: str) -> str:
        try:
            return resolve_clickup_dropdown_option_id(field, label)
        except ValueError as exc:
            raise RevenueInvoiceSyncError(
                f"Missing ClickUp dropdown option {label!r} for field {field.get('name')!r}.",
                category="missing_dropdown_option",
                retryable=False,
                payload_summary={
                    "field": field.get("name"),
                    "expected_option": label,
                    "available_options": [
                        option.get("name")
                        for option in (field.get("type_config") or {}).get("options", [])
                    ],
                },
            ) from exc


@dataclass(frozen=True)
class RevenueInvoiceDocuments:
    pdf_path: Path | None = None
    xml_path: Path | None = None
    sat_path: Path | None = None
    warnings: tuple[str, ...] = ()


def prepare_revenue_invoice_sync(
    *,
    invoice: dict[str, Any],
    lines: list[dict[str, Any]],
    customer: dict[str, Any] | None,
    company_name: str | None,
    bc_invoice_url: str | None,
    registry: ClickUpFieldRegistry,
    settings: RevenueInvoiceSyncSettings | None = None,
    sync_timestamp: datetime | None = None,
) -> dict[str, Any]:
    config = settings or RevenueInvoiceSyncSettings.from_env()
    synced_at = sync_timestamp or datetime.now(UTC)
    invoice_no = _first_value(invoice, "number", "No.", "no")
    if not invoice_no:
        raise RevenueInvoiceSyncError(
            "Business Central invoice is missing an invoice number.",
            category="missing_invoice_number",
            bc_system_id=_bc_system_id(invoice),
            retryable=False,
        )

    total = _decimal_value(
        invoice,
        "totalAmountIncludingTax",
        "amountIncludingVAT",
        "Amount_Including_VAT",
        "totalAmount",
    )
    remaining = _decimal_value(
        invoice,
        "remainingAmount",
        "remainingBalance",
        "Remaining_Amount",
        "balanceDue",
        default=total,
    )
    tax = _decimal_value(invoice, "totalTaxAmount", "taxAmount", "Total_VAT", default=Decimal("0"))
    subtotal = _decimal_value(
        invoice,
        "totalAmountExcludingTax",
        "amount",
        "subtotal",
        default=(total - tax),
    )
    currency = (_first_value(invoice, "currencyCode", "currency", "Currency_Code") or "GTQ").upper()
    customer_name = _first_value(invoice, "customerName", "billToName", "Bill_to_Name") or (
        customer or {}
    ).get("displayName")
    customer_no = _first_value(invoice, "customerNumber", "billToCustomerNumber", "Bill_to_Customer_No")
    customer_tax_id = _first_value(
        customer or {},
        "taxRegistrationNumber",
        "vatRegistrationNumber",
        "VAT Registration No.",
    ) or _first_value(invoice, "customerTaxId", "taxRegistrationNumber")
    collection_status = map_collection_status(
        total=total,
        remaining=remaining,
        document_type=_first_value(invoice, "documentType", "Document_Type"),
    )
    paid_date = _paid_date(invoice) if collection_status == "COLLECTED" else None
    shipment_refs = derive_shipment_references(invoice=invoice, lines=lines)
    dte_authorization = _first_value(
        invoice,
        "UUID_Factura",
        "UUID_Factura_GT",
        "fiscalInvoiceNumberPAC",
        "Fiscal_Invoice_Number_PAC",
        "dteAuthorization",
        "DTE_Authorization",
    )
    sat_reference = _first_value(invoice, "satReference", "SAT_Reference", "uuid")

    mapped = {
        "invoice_no": invoice_no,
        "series": _fiscal_invoice_series(dte_authorization),
        "client_invoice_number": _first_value(invoice, "numero", "Numero", "fiscalNumber"),
        "clickup_document_type": _clickup_document_type(invoice_no),
        "bc_system_id": _bc_system_id(invoice),
        "legal_entity": company_name,
        "customer_name": customer_name,
        "customer_no": customer_no,
        "customer_tax_id": customer_tax_id,
        "posting_date": _first_value(invoice, "postingDate", "Posting_Date"),
        "document_date": _first_value(invoice, "documentDate", "invoiceDate", "Document_Date"),
        "due_date": _first_value(invoice, "dueDate", "Due_Date"),
        "payment_terms": _first_value(invoice, "paymentTermsCode", "paymentTermsId"),
        "currency": currency,
        "subtotal": subtotal,
        "tax": tax,
        "total": total,
        "remaining": remaining,
        "fx_rate": _exchange_rate(invoice, currency=currency),
        "revenue_recognition": _first_value(invoice, "revenueRecognition", "Revenue_Recognition"),
        "collection_status": collection_status,
        "paid_date": paid_date,
        "applied_credit_note": _first_value(invoice, "appliedCreditMemo", "appliedCreditNote"),
        "dte_authorization": dte_authorization,
        "sat_reference": sat_reference,
        "bc_invoice_url": bc_invoice_url,
        **shipment_refs,
    }
    description = build_invoice_description(mapped, lines, synced_at=synced_at)
    custom_fields = build_custom_field_updates(mapped, registry=registry, settings=config)

    return {
        "invoice_no": invoice_no,
        "bc_system_id": mapped["bc_system_id"],
        "task_name": build_invoice_task_name(invoice_no=invoice_no),
        "description": description,
        "custom_fields": custom_fields,
        "collection_status": collection_status,
        "mapped": _json_safe(mapped),
    }


def build_custom_field_updates(
    mapped: dict[str, Any],
    *,
    registry: ClickUpFieldRegistry,
    settings: RevenueInvoiceSyncSettings,
) -> list[dict[str, Any]]:
    updates: list[dict[str, Any]] = []

    def add_value(key: str, value: Any) -> None:
        if value in {None, ""}:
            return
        field = registry.find(settings.field_names.get(key, ()), settings.field_ids.get(key))
        if field:
            updates.append({"field_id": field["id"], "field_name": field["name"], "value": value})

    def add_date(key: str, value: Any) -> None:
        timestamp_ms = _clickup_date_ms(value)
        if timestamp_ms is not None:
            add_value(key, timestamp_ms)

    def add_dropdown(key: str, label: str | None, *, required: bool = False) -> None:
        if not label:
            return
        field = registry.find(settings.field_names.get(key, ()), settings.field_ids.get(key))
        if not field:
            if required:
                raise RevenueInvoiceSyncError(
                    f"Required ClickUp custom field for {key} is missing from the Revenue Guatemala list.",
                    category="missing_custom_field",
                    invoice_no=mapped.get("invoice_no"),
                    bc_system_id=mapped.get("bc_system_id"),
                    retryable=False,
                    payload_summary={"field_key": key, "candidate_names": settings.field_names.get(key, ())},
                )
            return
        value = registry.resolve_dropdown(field, label) if required else _optional_dropdown_value(registry, field, label)
        if value is None:
            return
        updates.append(
            {
                "field_id": field["id"],
                "field_name": field["name"],
                "value": value,
                "label": label,
            }
        )

    add_dropdown("collection_status", mapped.get("collection_status"), required=True)
    add_dropdown("currency", mapped.get("currency"), required=True)
    add_dropdown("customer", mapped.get("customer_name"), required=False)
    add_dropdown("customer_no", mapped.get("customer_no"), required=False)
    add_dropdown("carrier", mapped.get("carrier"), required=False)
    add_dropdown("type", mapped.get("clickup_document_type"), required=False)
    add_dropdown("revenue_recognition", mapped.get("revenue_recognition"), required=False)
    add_date("date", mapped.get("posting_date") or mapped.get("document_date"))
    add_value("master_bl", mapped.get("mbl"))
    add_value("series", mapped.get("series"))
    add_value("client_invoice", mapped.get("client_invoice_number"))
    add_value("po", mapped.get("po_number"))
    add_value("vat_usd", _currency_amount(mapped, "tax", expected_currency="USD"))
    add_value("total_invoice_usd", _currency_amount(mapped, "total", expected_currency="USD"))
    add_value("fx_rate", _decimal_to_float(mapped.get("fx_rate")))
    add_value("bc_system_id", mapped.get("bc_system_id"))
    add_value("bc_invoice_url", mapped.get("bc_invoice_url"))
    add_value("invoice_no", mapped.get("invoice_no"))
    add_value("customer_tax_id", mapped.get("customer_tax_id"))
    add_value("dte_authorization", mapped.get("dte_authorization"))
    add_value("sat_reference", mapped.get("sat_reference"))
    add_value("remaining_balance", _decimal_to_float(mapped.get("remaining")))
    add_value("total_amount", _decimal_to_float(mapped.get("total")))
    return updates


def map_collection_status(
    *,
    total: Decimal,
    remaining: Decimal,
    document_type: str | None = None,
) -> str:
    if (document_type or "").strip().casefold() in {"credit memo", "credit_note", "ncre"}:
        return "CREDIT NOTE"
    if remaining <= Decimal("0"):
        return "COLLECTED"
    if total > Decimal("0") and remaining < total:
        return "PARTIALLY PAID"
    return "TO COLLECT"


def build_invoice_task_name(
    *,
    invoice_no: str,
    customer_name: str | None = None,
    currency: str | None = None,
    total: Decimal | None = None,
) -> str:
    return invoice_no


def build_invoice_description(
    mapped: dict[str, Any],
    lines: list[dict[str, Any]],
    *,
    synced_at: datetime,
) -> str:
    return f"""# Invoice Summary
- Invoice No.: {mapped.get("invoice_no") or ""}
- BC SystemId: {mapped.get("bc_system_id") or ""}
- Legal Entity: {mapped.get("legal_entity") or ""}
- Customer: {mapped.get("customer_name") or ""}
- Customer No.: {mapped.get("customer_no") or ""}
- Customer Tax ID / NIT: {mapped.get("customer_tax_id") or ""}
- Posting Date: {mapped.get("posting_date") or ""}
- Document Date: {mapped.get("document_date") or ""}
- Due Date: {mapped.get("due_date") or ""}
- Payment Terms: {mapped.get("payment_terms") or ""}
- Currency: {mapped.get("currency") or ""}
- Subtotal: {_money(mapped.get("subtotal"))}
- Tax: {_money(mapped.get("tax"))}
- Total: {_money(mapped.get("total"))}
- Remaining Balance: {_money(mapped.get("remaining"))}
- Collection Status: {mapped.get("collection_status") or ""}
- Paid Date: {mapped.get("paid_date") or ""}
- Applied Credit Note: {mapped.get("applied_credit_note") or ""}

# Shipment / Operations References
- PO Number: {mapped.get("po_number") or ""}
- Shipment / File No.: {mapped.get("shipment_no") or ""}
- HBL: {mapped.get("hbl") or ""}
- MBL: {mapped.get("mbl") or ""}
- Container: {mapped.get("container") or ""}
- Carrier: {mapped.get("carrier") or ""}
- Service Type: {mapped.get("service_type") or ""}
- Salesperson / Owner: {mapped.get("owner") or ""}
- Connected ClickUp Shipment Task: {mapped.get("connected_shipment_task") or ""}

# Documents
- Business Central Invoice Link: {mapped.get("bc_invoice_url") or ""}
- Invoice PDF: attached when exposed by Business Central
- XML / SAT / DTE: attached when exposed by Business Central
- DTE Authorization: {mapped.get("dte_authorization") or ""}
- SAT Reference: {mapped.get("sat_reference") or ""}

# Invoice Lines
| Line No. | Description | Quantity | Unit Price | Tax | Amount |
| --- | --- | ---: | ---: | ---: | ---: |
{_line_table(lines)}

# Sync Metadata
- Last Sync Timestamp: {synced_at.isoformat()}
- Sync Mode: scheduled
- Source: Business Central
- Target: ClickUp Revenue Guatemala
"""


def derive_shipment_references(*, invoice: dict[str, Any], lines: list[dict[str, Any]]) -> dict[str, str | None]:
    text = " ".join(
        str(value or "")
        for value in [
            _first_value(invoice, "externalDocumentNumber", "customerPurchaseOrderReference"),
            *[
                _first_value(line, "description", "Description", "displayName")
                for line in lines
            ],
        ]
    )
    carrier = _normalize_carrier(
        _first_match(text, r"\b(MAERSK|MSC|ONE|HAPAG|CMA|COSCO|EVERGREEN|WAN HAI|ZIM|YANG MING)\b")
    )
    container = "; ".join(sorted(set(re.findall(r"\b[A-Z]{4}\d{7}\b", text)))) or None
    return {
        "po_number": _first_value(invoice, "externalDocumentNumber", "customerPurchaseOrderReference"),
        "shipment_no": _first_match(text, r"\b(?:FILE|SHIPMENT|BOOKING)[:\s-]+([A-Z0-9-]{5,})\b"),
        "hbl": _first_match(text, r"\bHBL[:\s-]+([A-Z0-9-]+)\b"),
        "mbl": _first_match(text, r"\bMBL[:\s-]+([A-Z0-9-]+)\b"),
        "container": container,
        "carrier": carrier,
        "service_type": derive_service_type(text),
        "owner": _first_value(invoice, "salespersonCode", "salesPerson", "operator"),
        "connected_shipment_task": None,
    }


def derive_service_type(text: str) -> str:
    lowered = text.casefold()
    if any(word in lowered for word in ["maritimo", "marítimo", "ocean", "container", "booking"]):
        return "ocean"
    if any(word in lowered for word in ["air", "aereo", "aéreo", "awb"]):
        return "air"
    if any(word in lowered for word in ["truck", "trucking", "terrestre"]):
        return "trucking"
    if any(word in lowered for word in ["warehouse", "almacenaje", "almacenajes"]):
        return "warehouse"
    return "other"


def find_clickup_tasks_for_invoice(
    clickup: ClickUpClient,
    *,
    list_id: str,
    invoice_no: str,
    max_pages: int,
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for page in range(max_pages):
        payload = clickup.get_list_tasks(
            list_id,
            include_closed=True,
            page=page,
            query=invoice_no,
        )
        tasks = payload.get("tasks", [])
        if not tasks:
            break
        for task in tasks:
            if _task_matches_invoice(task, invoice_no):
                matches.append(task)
    return matches


def prefetch_clickup_tasks_for_invoices(
    clickup: ClickUpClient,
    *,
    list_id: str,
    invoice_numbers: list[str],
    max_pages: int,
) -> dict[str, list[dict[str, Any]]]:
    invoice_numbers = [invoice_no for invoice_no in invoice_numbers if invoice_no]
    if not invoice_numbers:
        return {}

    tasks: list[dict[str, Any]] = []
    for page in range(max_pages):
        payload = clickup.get_list_tasks(
            list_id,
            include_closed=True,
            page=page,
        )
        page_tasks = payload.get("tasks", [])
        if not page_tasks:
            break
        tasks.extend(page_tasks)

    return {
        invoice_no: [task for task in tasks if _task_matches_invoice(task, invoice_no)]
        for invoice_no in invoice_numbers
    }


def _task_matches_invoice(task: dict[str, Any], invoice_no: str) -> bool:
    name = task.get("name") or ""
    prefix = f"{invoice_no} |"
    return name == invoice_no or name.startswith(prefix) or invoice_no in name


def sync_revenue_invoice(
    *,
    invoice: dict[str, Any],
    bc: BusinessCentralClient,
    clickup: ClickUpClient,
    registry: ClickUpFieldRegistry,
    settings: RevenueInvoiceSyncSettings,
    dry_run: bool = True,
    existing_tasks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    start = time.monotonic()
    invoice_no = _first_value(invoice, "number", "No.", "no")
    bc_system_id = _bc_system_id(invoice)
    try:
        if not invoice_no:
            raise RevenueInvoiceSyncError("Invoice number is missing.", category="missing_invoice_number")
        invoice_id = _first_value(invoice, "id", "systemId", "SystemId")
        enriched_invoice = dict(invoice)
        gt_registered_invoice = bc.get_gt_registered_invoice_by_number(invoice_no, market=settings.market)
        if gt_registered_invoice:
            for key in ("numero", "Numero"):
                value = _first_value(gt_registered_invoice, key)
                if value:
                    enriched_invoice.setdefault(key, value)
        for ledger_entry in bc.get_customer_ledger_entries_by_document_no(invoice_no, market=settings.market):
            fiscal_number = _first_value(
                ledger_entry,
                "UUID_Factura",
                "Fiscal_Invoice_Number_PAC",
                "UUID",
            )
            if fiscal_number:
                enriched_invoice.setdefault("UUID_Factura", fiscal_number)
                break
        lines = (
            bc.get_posted_sales_invoice_lines(invoice_id, market=settings.market)
            if invoice_id
            else []
        )
        customer = None
        customer_id = _first_value(invoice, "customerId", "billToCustomerId")
        if customer_id:
            customer = bc.get_customer_by_id(customer_id, market=settings.market)
        company = bc.get_company_metadata(market=settings.market)
        company_name = (company or {}).get("name") or (company or {}).get("displayName")
        bc_invoice_url = (
            bc.build_sales_invoice_url(company_name=company_name, invoice_number=invoice_no)
            if company_name
            else None
        )
        payload = prepare_revenue_invoice_sync(
            invoice=enriched_invoice,
            lines=lines,
            customer=customer,
            company_name=company_name,
            bc_invoice_url=bc_invoice_url,
            registry=registry,
            settings=settings,
        )
        existing = (
            existing_tasks
            if existing_tasks is not None
            else find_clickup_tasks_for_invoice(
                clickup,
                list_id=settings.revenue_list_id,
                invoice_no=invoice_no,
                max_pages=settings.max_task_pages,
            )
        )
        if len(existing) > 1:
            raise RevenueInvoiceSyncError(
                f"Multiple ClickUp tasks matched invoice {invoice_no}.",
                category="duplicate_clickup_tasks",
                invoice_no=invoice_no,
                bc_system_id=bc_system_id,
                retryable=False,
                payload_summary={"matched_task_ids": [task.get("id") for task in existing]},
            )

        action = "update" if existing else "create"
        if dry_run:
            return _result(
                invoice_no=invoice_no,
                bc_system_id=bc_system_id,
                action=action,
                status="dry_run",
                elapsed_ms=start,
                payload=payload,
                clickup_task_id=(existing[0].get("id") if existing else None),
            )

        if existing:
            task_id = existing[0]["id"]
            clickup.update_task(
                task_id,
                name=payload["task_name"],
                description=payload["description"],
            )
        else:
            created = clickup.create_task(
                settings.revenue_list_id,
                name=payload["task_name"],
                description=payload["description"],
                status=settings.default_task_status,
            )
            task_id = created["id"]

        field_errors: list[str] = []
        for update in payload["custom_fields"]:
            try:
                clickup.set_task_custom_field_value(task_id, update["field_id"], update["value"])
            except Exception as exc:
                field_errors.append(f"{update['field_name']}: {type(exc).__name__}: {exc}")

        attachment_status = "skipped"
        if settings.attach_documents:
            attachment_status = attach_invoice_documents(
                clickup=clickup,
                task_id=task_id,
                invoice=invoice,
            )

        warnings = tuple(field_errors)
        comment = build_automation_log_comment(
            action=action,
            payload=payload,
            attachment_status=attachment_status,
            warnings=warnings,
        )
        clickup.create_task_comment(task_id, comment_text=comment, notify_all=False)

        if field_errors:
            create_exception_task(
                clickup=clickup,
                settings=settings,
                error=RevenueInvoiceSyncError(
                    "One or more ClickUp custom fields failed to update.",
                    category="custom_field_update_failed",
                    invoice_no=invoice_no,
                    bc_system_id=bc_system_id,
                    payload_summary={"field_errors": field_errors},
                ),
            )

        return _result(
            invoice_no=invoice_no,
            bc_system_id=bc_system_id,
            action=action,
            status="applied_with_warnings" if field_errors else "applied",
            elapsed_ms=start,
            clickup_task_id=task_id,
            payload={"attachment_status": attachment_status, "warnings": field_errors},
        )
    except RevenueInvoiceSyncError as exc:
        create_exception_task(clickup=clickup, settings=settings, error=exc)
        logger.exception(
            "Revenue invoice sync failed invoice_no=%s bc_system_id=%s error_type=%s",
            exc.invoice_no or invoice_no,
            exc.bc_system_id or bc_system_id,
            exc.category,
        )
        return _result(
            invoice_no=exc.invoice_no or invoice_no,
            bc_system_id=exc.bc_system_id or bc_system_id,
            action="error",
            status="failed",
            elapsed_ms=start,
            error_type=exc.category,
            payload={"message": str(exc), "retryable": exc.retryable},
        )


def run_revenue_invoice_sync(
    *,
    bc: BusinessCentralClient,
    clickup: ClickUpClient,
    settings: RevenueInvoiceSyncSettings | None = None,
    dry_run: bool = True,
    invoice_no: str | None = None,
    full_review: bool = False,
) -> dict[str, Any]:
    config = settings or RevenueInvoiceSyncSettings.from_env()
    registry = ClickUpFieldRegistry.from_clickup_list(clickup, config.revenue_list_id)
    if invoice_no:
        invoice = bc.get_posted_sales_invoice_by_number(invoice_no, market=config.market)
        invoices = [invoice] if invoice else []
    else:
        since = date.today() - timedelta(days=config.weekly_full_days if full_review else config.incremental_days)
        invoices = bc.get_posted_sales_invoices(
            top=config.page_size,
            filters=f"postingDate ge {since.isoformat()}",
            market=config.market,
        )
    results = [
        sync_revenue_invoice(
            invoice=invoice,
            bc=bc,
            clickup=clickup,
            registry=registry,
            settings=config,
            dry_run=dry_run,
        )
        for invoice in invoices
    ]
    return {
        "mode": "dry_run" if dry_run else "apply",
        "sync_type": "manual_invoice" if invoice_no else ("weekly_full" if full_review else "incremental"),
        "invoice_count": len(invoices),
        "results": results,
    }


def attach_invoice_documents(
    *,
    clickup: ClickUpClient,
    task_id: str,
    invoice: dict[str, Any],
) -> str:
    pdf_base64 = _first_value(invoice, "pdfBase64", "PDF_64", "pdf_64")
    if not pdf_base64:
        return "not_exposed_by_business_central"
    try:
        import base64

        invoice_no = _first_value(invoice, "number", "No.", "no") or "invoice"
        with NamedTemporaryFile(suffix=".pdf", delete=False) as handle:
            handle.write(base64.b64decode(pdf_base64))
            temp_path = Path(handle.name)
        try:
            clickup.attach_file_to_task(task_id, temp_path, file_name=f"{invoice_no}.pdf", mime_type="application/pdf")
        finally:
            temp_path.unlink(missing_ok=True)
        return "attached"
    except Exception as exc:
        logger.warning("Invoice attachment failed task_id=%s error=%s", task_id, exc)
        return f"failed: {type(exc).__name__}: {exc}"


def build_automation_log_comment(
    *,
    action: str,
    payload: dict[str, Any],
    attachment_status: str,
    warnings: tuple[str, ...] = (),
) -> str:
    mapped = payload.get("mapped") or {}
    changed_fields = ", ".join(update["field_name"] for update in payload.get("custom_fields", [])) or "description/name"
    warning_text = "\n".join(f"- {warning}" for warning in warnings) or "- none"
    return f"""Automation Log
Timestamp: {datetime.now(UTC).isoformat()}
Source: Business Central scheduled sync
Action: {action}
Changed fields: {changed_fields}
Collection status: {mapped.get("collection_status") or ""}
Attachment status: {attachment_status}
Connected shipment task: {mapped.get("connected_shipment_task") or "not found"}
Non-blocking warnings:
{warning_text}
"""


def create_exception_task(
    *,
    clickup: ClickUpClient,
    settings: RevenueInvoiceSyncSettings,
    error: RevenueInvoiceSyncError,
) -> dict[str, Any] | None:
    if not settings.exception_list_id:
        logger.error(
            "CLICKUP_REVENUE_GT_EXCEPTION_LIST_ID is not configured; exception not sent invoice_no=%s category=%s message=%s",
            error.invoice_no,
            error.category,
            error,
        )
        return None
    description = json.dumps(
        {
            "timestamp": datetime.now(UTC).isoformat(),
            "source_system": "Business Central",
            "target_system": "ClickUp",
            "invoice_no": error.invoice_no,
            "bc_system_id": error.bc_system_id,
            "error_category": error.category,
            "error_message": str(error),
            "payload_summary": error.payload_summary,
            "retry_eligible": error.retryable,
        },
        ensure_ascii=False,
        indent=2,
        default=str,
    )
    return clickup.create_task(
        settings.exception_list_id,
        name=f"BC to ClickUp invoice sync exception | {error.invoice_no or 'unknown invoice'} | {error.category}",
        description=description,
    )


def _field_names_from_env() -> dict[str, tuple[str, ...]]:
    defaults = {
        "master_bl": ("Master BL Number/", "Master BL Number", "MBL"),
        "series": ("Serie", "Series"),
        "client_invoice": ("Factura Cliente", "Invoice No."),
        "type": ("Type",),
        "date": ("Date",),
        "collection_status": ("Collection Estatus",),
        "currency": ("Currency Invoice",),
        "customer_no": ("Nº Customer", "No Customer", "Customer No."),
        "customer": ("Customer",),
        "carrier": ("Carrier/", "Carrier"),
        "vat_usd": ("VAT (USD)",),
        "total_invoice_usd": ("Total Invoice (USD)",),
        "fx_rate": ("FX Rate",),
        "revenue_recognition": ("Revenue Recognition",),
        "po": ("PO",),
        "bc_system_id": ("Business Central Invoice ID", "Business Central SystemId"),
        "bc_invoice_url": ("Business Central Invoice Link", "Business Central URL"),
        "invoice_no": ("Business Central Invoice Number", "Invoice No."),
        "customer_tax_id": ("Customer Tax ID", "NIT"),
        "dte_authorization": ("DTE Authorization", "DTE Authorization Number"),
        "sat_reference": ("SAT Reference", "SAT Document Reference"),
        "remaining_balance": ("Remaining Balance",),
        "total_amount": ("Total Invoice Amount", "Invoice Total"),
    }
    raw = os.getenv("CLICKUP_REVENUE_GT_FIELD_NAMES_JSON", "").strip()
    if not raw:
        return defaults
    overrides = json.loads(raw)
    merged = dict(defaults)
    for key, names in overrides.items():
        if isinstance(names, str):
            merged[key] = tuple(name.strip() for name in names.split(",") if name.strip())
        else:
            merged[key] = tuple(str(name).strip() for name in names if str(name).strip())
    return merged


def _field_ids_from_env() -> dict[str, str]:
    raw = os.getenv("CLICKUP_REVENUE_GT_FIELD_IDS_JSON", "").strip()
    if not raw:
        return dict(REVENUE_GT_FIELD_IDS)
    overrides = json.loads(raw)
    merged = dict(REVENUE_GT_FIELD_IDS)
    for key, field_id in overrides.items():
        if str(field_id).strip():
            merged[key] = str(field_id).strip()
    return merged


def _result(
    *,
    invoice_no: str | None,
    bc_system_id: str | None,
    action: str,
    status: str,
    elapsed_ms: float,
    clickup_task_id: str | None = None,
    error_type: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    elapsed = int((time.monotonic() - elapsed_ms) * 1000)
    logger.info(
        "revenue_invoice_sync invoice_no=%s bc_system_id=%s clickup_task_id=%s action=%s status=%s error_type=%s elapsed_ms=%s",
        invoice_no,
        bc_system_id,
        clickup_task_id,
        action,
        status,
        error_type,
        elapsed,
    )
    return {
        "invoice_no": invoice_no,
        "bc_system_id": bc_system_id,
        "clickup_task_id": clickup_task_id,
        "action": action,
        "status": status,
        "error_type": error_type,
        "elapsed_ms": elapsed,
        **(payload or {}),
    }


def _line_table(lines: list[dict[str, Any]]) -> str:
    rows = []
    for index, line in enumerate(lines, start=1):
        rows.append(
            "| {line_no} | {description} | {quantity} | {unit_price} | {tax} | {amount} |".format(
                line_no=_first_value(line, "sequence", "lineNumber", "Line_No") or index,
                description=_markdown_cell(_first_value(line, "description", "Description") or ""),
                quantity=_first_value(line, "quantity", "Quantity") or "",
                unit_price=_money(_decimal_value(line, "unitPrice", "Unit_Price", default=Decimal("0"))),
                tax=_money(_decimal_value(line, "taxAmount", "Tax_Amount", default=Decimal("0"))),
                amount=_money(_decimal_value(line, "amountIncludingTax", "amount", "Line_Amount", default=Decimal("0"))),
            )
        )
    return "\n".join(rows) if rows else "|  | No invoice lines exposed by Business Central |  |  |  |  |"


def _first_value(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if value not in {None, ""}:
            return str(value).strip()
    return ""


def _decimal_value(payload: dict[str, Any], *keys: str, default: Decimal = Decimal("0")) -> Decimal:
    for key in keys:
        value = payload.get(key)
        if value in {None, ""}:
            continue
        try:
            return Decimal(str(value).replace(",", ""))
        except (InvalidOperation, ValueError):
            continue
    return default


def _decimal_to_float(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    return float(value)


def _currency_amount(
    mapped: dict[str, Any],
    key: str,
    *,
    expected_currency: str,
) -> float | None:
    if (mapped.get("currency") or "").upper() != expected_currency:
        return None
    return _decimal_to_float(mapped.get(key))


def _optional_dropdown_value(
    registry: ClickUpFieldRegistry,
    field: dict[str, Any],
    label: str,
) -> str | None:
    try:
        return registry.resolve_dropdown(field, label)
    except RevenueInvoiceSyncError:
        logger.warning(
            "Skipping optional ClickUp dropdown field=%s label=%s because no option matched.",
            field.get("name"),
            label,
        )
        return None


def _normalize_carrier(carrier: str | None) -> str | None:
    normalized = (carrier or "").strip().upper()
    aliases = {
        "HAPAG": "Hapag Lloyd",
        "MAERSK": "Maersk",
        "COSCO": "Cosco",
        "EVERGREEN": "Evergreen",
        "WAN HAI": "Wan Hai",
        "ZIM": "ZIM Line",
        "YANG MING": "Yang Min",
    }
    return aliases.get(normalized, carrier)


def _clickup_date_ms(value: Any) -> int | None:
    if value in {None, ""}:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime(value.year, value.month, value.day, tzinfo=UTC)
    else:
        raw = str(value).strip()
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            try:
                parsed = datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=UTC)
            except ValueError:
                return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return int(parsed.timestamp() * 1000)


def _fiscal_invoice_series(fiscal_invoice_number: str | None) -> str:
    compact = re.sub(r"[^A-Za-z0-9]", "", fiscal_invoice_number or "")
    return compact[:8].upper()


def _clickup_document_type(invoice_no: str | None) -> str:
    normalized = (invoice_no or "").strip().upper()
    if normalized.startswith("GTFVR"):
        return "FACT"
    if normalized.startswith("GTNVR"):
        return "NCRE"
    return ""


def _exchange_rate(invoice: dict[str, Any], *, currency: str) -> Decimal | None:
    rate = _decimal_value(
        invoice,
        "exchangeRate",
        "currencyFactor",
        "Currency_Factor",
        "CurrencyFactor",
        default=Decimal("0"),
    )
    if rate:
        return rate
    if currency.upper() == "USD":
        return Decimal("1")
    return None


def _money(value: Any) -> str:
    if value in {None, ""}:
        return ""
    try:
        return f"{Decimal(str(value)):,.2f}"
    except (InvalidOperation, ValueError):
        return str(value)


def _markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()


def _bc_system_id(invoice: dict[str, Any]) -> str | None:
    return _first_value(invoice, "systemId", "SystemId", "id") or None


def _paid_date(invoice: dict[str, Any]) -> str | None:
    return _first_value(invoice, "closedAt", "paidDate", "lastPaymentDate") or None


def _first_match(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(1) if match.groups() else match.group(0)


def _json_safe(payload: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(payload, default=str, ensure_ascii=False))


def _env_int(name: str, *, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    return int(raw)


def _env_bool(name: str, *, default: bool) -> bool:
    raw = os.getenv(name, "").strip().casefold()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "y", "on"}
