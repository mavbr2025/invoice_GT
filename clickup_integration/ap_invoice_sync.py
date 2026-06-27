from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any

from pypdf import PdfReader

from business_central_client.client import BusinessCentralClient
from clickup_integration.customer_rules import dropdown_label, field_value


@dataclass(frozen=True)
class APPurchaseVendorMapping:
    list_id: str | None
    list_name: str | None
    vendor_number: str
    item_number: str
    tax_code: str
    unit_of_measure_code: str | None = None
    prices_include_tax: bool = True
    due_days: int = 15


@dataclass(frozen=True)
class APPurchaseInvoiceSettings:
    supported_market: str
    supported_currency: str
    approved_finops_labels: tuple[str, ...]
    invoice_number_field_names: tuple[str, ...]
    invoice_date_field_names: tuple[str, ...]
    total_amount_field_names: tuple[str, ...]
    master_bl_field_names: tuple[str, ...]
    finops_status_field_names: tuple[str, ...]
    vendor_mappings: tuple[APPurchaseVendorMapping, ...]

    @classmethod
    def from_env(cls) -> "APPurchaseInvoiceSettings":
        market = os.getenv("CLICKUP_AP_MARKET", "GT").strip().upper() or "GT"
        return cls(
            supported_market=market,
            supported_currency=os.getenv("CLICKUP_AP_CURRENCY", "USD").strip().upper() or "USD",
            approved_finops_labels=_env_csv(
                "CLICKUP_AP_APPROVED_FINOPS_LABELS",
                default=("PROCEDE A PAGO",),
            ),
            invoice_number_field_names=_env_csv(
                "CLICKUP_AP_INVOICE_NUMBER_FIELD_NAMES",
                default=("Invoice Number",),
            ),
            invoice_date_field_names=_env_csv(
                "CLICKUP_AP_INVOICE_DATE_FIELD_NAMES",
                default=("🚢 Invoice date", "Invoice date", "Invoice Date"),
            ),
            total_amount_field_names=_env_csv(
                "CLICKUP_AP_TOTAL_AMOUNT_FIELD_NAMES",
                default=("🚢 Total USD", "Total USD", "Total"),
            ),
            master_bl_field_names=_env_csv(
                "CLICKUP_AP_MASTER_BL_FIELD_NAMES",
                default=("Master BL Number/", "Master BL Number", "BL"),
            ),
            finops_status_field_names=_env_csv(
                "CLICKUP_AP_FINOPS_STATUS_FIELD_NAMES",
                default=("Validación FINOPS", "Validacion FINOPS", "FINOPS Validation"),
            ),
            vendor_mappings=_load_vendor_mappings(),
        )


def prepare_clickup_bc_purchase_invoice_preview(
    *,
    clickup_summary: dict[str, Any],
    bc_client: BusinessCentralClient,
    settings: APPurchaseInvoiceSettings | None = None,
    pdf_contents: list[bytes] | None = None,
    compare_invoice_number: str | None = None,
) -> dict[str, Any]:
    config = settings or APPurchaseInvoiceSettings.from_env()
    custom_fields = clickup_summary.get("custom_fields") or {}
    list_info = clickup_summary.get("list") or {}
    mapping = _resolve_vendor_mapping(clickup_summary, config)
    if mapping is None:
        return {
            "status": "missing_vendor_mapping",
            "message": "No AP vendor mapping matched this ClickUp list.",
            "task_id": clickup_summary.get("task_id"),
            "list": list_info,
        }

    extracted_pdf = _extract_first_supported_pdf(pdf_contents or [])
    clickup_invoice_number = _first_present_field(custom_fields, config.invoice_number_field_names)
    vendor_invoice_number = (
        (extracted_pdf.get("invoice_number") if extracted_pdf else "") or clickup_invoice_number
    )
    if not vendor_invoice_number:
        return {
            "status": "missing_vendor_invoice_number",
            "message": "Could not resolve the vendor invoice number from ClickUp or the PDF.",
            "task_id": clickup_summary.get("task_id"),
        }

    total_amount = _resolve_total_amount(custom_fields, config, extracted_pdf)
    if total_amount is None:
        return {
            "status": "missing_total_amount",
            "message": "Could not resolve the invoice total from ClickUp or the PDF.",
            "task_id": clickup_summary.get("task_id"),
            "vendor_invoice_number": vendor_invoice_number,
        }

    pdf_date = _parse_iso_date((extracted_pdf or {}).get("berthing_date"))
    clickup_invoice_date = _resolve_date_from_fields(custom_fields, config.invoice_date_field_names)
    invoice_date = pdf_date or clickup_invoice_date or date.today()
    posting_date = invoice_date
    due_date = posting_date + timedelta(days=mapping.due_days)
    charge_codes = _resolve_charge_codes(extracted_pdf)
    description = ",".join(charge_codes) if charge_codes else vendor_invoice_number
    finops_status = _resolve_finops_status(custom_fields, config)
    payment_gate = _build_payment_gate(finops_status=finops_status, config=config)
    master_bl = _first_present_field(custom_fields, config.master_bl_field_names)

    vendor = _find_vendor(bc_client=bc_client, vendor_number=mapping.vendor_number, market=config.supported_market)
    if vendor is None:
        return {
            "status": "missing_bc_vendor",
            "message": f"Business Central vendor {mapping.vendor_number} was not found.",
            "task_id": clickup_summary.get("task_id"),
            "vendor_invoice_number": vendor_invoice_number,
        }

    header_payload: dict[str, Any] = {
        "vendorNumber": vendor.get("number") or mapping.vendor_number,
        "vendorInvoiceNumber": vendor_invoice_number,
        "currencyCode": config.supported_currency,
        "invoiceDate": invoice_date.isoformat(),
        "postingDate": posting_date.isoformat(),
        "dueDate": due_date.isoformat(),
        "pricesIncludeTax": mapping.prices_include_tax,
    }
    if vendor.get("id"):
        header_payload["vendorId"] = vendor["id"]

    line_payload: dict[str, Any] = {
        "lineType": "Item",
        "lineObjectNumber": mapping.item_number,
        "description": description,
        "quantity": 1,
        "unitCost": float(total_amount),
        "taxCode": mapping.tax_code,
    }
    if mapping.unit_of_measure_code:
        line_payload["unitOfMeasureCode"] = mapping.unit_of_measure_code
    comment_line_payload = _build_bc_transfer_comment_line(
        task_id=str(clickup_summary.get("task_id") or ""),
        vendor_invoice_number=vendor_invoice_number,
    )

    preview: dict[str, Any] = {
        "status": "dry_run_ready",
        "task_id": clickup_summary.get("task_id"),
        "task_name": clickup_summary.get("name"),
        "task_status": clickup_summary.get("status"),
        "list": list_info,
        "market": config.supported_market,
        "currency": config.supported_currency,
        "payment_gate": payment_gate,
        "vendor": {
            "number": vendor.get("number") or mapping.vendor_number,
            "name": vendor.get("displayName") or vendor.get("name"),
        },
        "vendor_invoice_number": vendor_invoice_number,
        "master_bl": master_bl or (extracted_pdf or {}).get("master_bl") or None,
        "source_dates": {
            "clickup_invoice_date": clickup_invoice_date.isoformat() if clickup_invoice_date else None,
            "pdf_berthing_date": pdf_date.isoformat() if pdf_date else None,
            "selected_invoice_date": invoice_date.isoformat(),
        },
        "extracted_pdf": extracted_pdf,
        "proposed_bc_payload": header_payload,
        "proposed_bc_line_payloads": [line_payload],
        "proposed_bc_comment_line_payloads": [comment_line_payload],
    }
    if compare_invoice_number:
        preview["comparison"] = compare_purchase_invoice_preview_to_bc(
            preview=preview,
            bc_client=bc_client,
            invoice_number=compare_invoice_number,
            market=config.supported_market,
        )
    return preview


def compare_purchase_invoice_preview_to_bc(
    *,
    preview: dict[str, Any],
    bc_client: BusinessCentralClient,
    invoice_number: str,
    market: str,
) -> dict[str, Any]:
    existing = _find_purchase_invoice_by_number(
        bc_client=bc_client,
        invoice_number=invoice_number,
        market=market,
    )
    if existing is None:
        return {
            "status": "missing_existing_invoice",
            "invoice_number": invoice_number,
        }

    lines = bc_client.get_purchase_invoice_lines(existing["id"], market=market)
    proposed_header = preview.get("proposed_bc_payload") or {}
    proposed_lines = preview.get("proposed_bc_line_payloads") or []
    proposed_line = proposed_lines[0] if proposed_lines else {}
    existing_line = lines[0] if lines else {}
    checks = [
        _compare_value("vendorInvoiceNumber", proposed_header, existing),
        _compare_value("vendorNumber", proposed_header, existing),
        _compare_value("currencyCode", proposed_header, existing),
        _compare_value("invoiceDate", proposed_header, existing),
        _compare_value("postingDate", proposed_header, existing),
        _compare_value("dueDate", proposed_header, existing),
        _compare_decimal(
            "totalAmountIncludingTax",
            proposed_value=proposed_line.get("unitCost"),
            existing_value=existing.get("totalAmountIncludingTax"),
        ),
        _compare_value("lineObjectNumber", proposed_line, existing_line),
        _compare_value("description", proposed_line, existing_line),
        _compare_decimal(
            "lineUnitCost",
            proposed_value=proposed_line.get("unitCost"),
            existing_value=existing_line.get("unitCost"),
        ),
        _compare_value("taxCode", proposed_line, existing_line),
    ]
    mismatches = [check for check in checks if check["status"] != "match"]
    return {
        "status": "matched" if not mismatches else "mismatched",
        "invoice_number": invoice_number,
        "existing_invoice": {
            "id": existing.get("id"),
            "number": existing.get("number"),
            "status": existing.get("status"),
            "vendorInvoiceNumber": existing.get("vendorInvoiceNumber"),
            "vendorNumber": existing.get("vendorNumber"),
            "vendorName": existing.get("vendorName"),
            "totalAmountIncludingTax": existing.get("totalAmountIncludingTax"),
        },
        "checks": checks,
        "mismatches": mismatches,
    }


def apply_clickup_bc_purchase_invoice(
    *,
    clickup_summary: dict[str, Any],
    bc_client: BusinessCentralClient,
    settings: APPurchaseInvoiceSettings | None = None,
    pdf_contents: list[bytes] | None = None,
) -> dict[str, Any]:
    config = settings or APPurchaseInvoiceSettings.from_env()
    preview = prepare_clickup_bc_purchase_invoice_preview(
        clickup_summary=clickup_summary,
        bc_client=bc_client,
        settings=config,
        pdf_contents=pdf_contents,
    )
    if preview.get("status") != "dry_run_ready":
        return preview

    duplicate = _find_purchase_invoice_by_vendor_invoice_number(
        bc_client=bc_client,
        vendor_invoice_number=preview["vendor_invoice_number"],
        market=config.supported_market,
    )
    if duplicate:
        return {
            **preview,
            "status": "duplicate_purchase_invoice",
            "message": "A Business Central purchase invoice already exists for this vendor invoice number.",
            "existing_invoice": duplicate,
        }

    created_invoice = bc_client.create_purchase_invoice(
        preview["proposed_bc_payload"],
        market=config.supported_market,
    )
    created_lines = []
    for line_payload in preview["proposed_bc_line_payloads"]:
        created_lines.append(
            bc_client.create_purchase_invoice_line(
                created_invoice["id"],
                line_payload,
                market=config.supported_market,
            )
        )
    created_comment_lines = []
    comment_warnings = []
    for line_payload in preview.get("proposed_bc_comment_line_payloads") or []:
        try:
            created_comment_lines.append(
                bc_client.create_purchase_invoice_line(
                    created_invoice["id"],
                    line_payload,
                    market=config.supported_market,
                )
            )
        except Exception as exc:
            comment_warnings.append(str(exc))
    return {
        **preview,
        "status": "applied",
        "created_invoice": created_invoice,
        "created_lines": created_lines,
        "created_comment_lines": created_comment_lines,
        "bc_comment_warnings": comment_warnings,
    }


def build_clickup_ap_transfer_comment(result: dict[str, Any]) -> str:
    created_invoice = result.get("created_invoice") or {}
    invoice_number = created_invoice.get("number") or created_invoice.get("id") or "UNKNOWN"
    vendor = result.get("vendor") or {}
    line_payloads = result.get("proposed_bc_line_payloads") or []
    amount = (line_payloads[0] or {}).get("unitCost") if line_payloads else None
    payment_gate = result.get("payment_gate") or {}
    payment_status = payment_gate.get("finops_status") or "not set"
    return "\n".join(
        [
            "AP invoice transferred to Business Central via integration.",
            f"BC purchase invoice: {invoice_number}",
            f"Vendor invoice: {result.get('vendor_invoice_number') or 'UNKNOWN'}",
            f"Vendor: {vendor.get('number') or 'UNKNOWN'} - {vendor.get('name') or 'UNKNOWN'}",
            f"Amount: {result.get('currency') or ''} {amount if amount is not None else 'UNKNOWN'}",
            f"Payment approval remains controlled in ClickUp. FINOPS status: {payment_status}.",
        ]
    )


def _extract_first_supported_pdf(pdf_contents: list[bytes]) -> dict[str, Any] | None:
    for content in pdf_contents:
        text = _extract_pdf_text(content)
        if not text.strip():
            continue
        extracted = _extract_one_guatemala_nco_invoice(text)
        if extracted:
            extracted["text_excerpt"] = text[:1200]
            return extracted
    return None


def _extract_pdf_text(content: bytes) -> str:
    reader = PdfReader(BytesIO(content))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def _extract_one_guatemala_nco_invoice(text: str) -> dict[str, Any] | None:
    invoice_match = re.search(r"\bNo\.\s*([A-Z0-9-]+)", text, flags=re.IGNORECASE)
    if not invoice_match:
        return None
    charges = [
        {"code": code, "amount": str(_decimal(amount))}
        for code, amount in re.findall(r"^([A-Z]{3})\s+USD\s+([0-9,]+\.\d{2})\s*$", text, flags=re.M)
    ]
    total_match = re.search(r"\bTotal\s+USD\s+([0-9,]+\.\d{2})", text, flags=re.IGNORECASE)
    berthing_match = re.search(r"FECHA\s+ATRAQUE:\s*(\d{4}-\d{2}-\d{2})", text, flags=re.IGNORECASE)
    bl_match = re.search(
        r"\bBL:\s*(?:.|\n){0,160}?([A-Z]{4}[A-Z0-9]{8,})",
        text,
        flags=re.IGNORECASE,
    )
    return {
        "format": "one_gt_nco",
        "invoice_number": invoice_match.group(1).strip().upper(),
        "master_bl": bl_match.group(1).strip().upper() if bl_match else None,
        "berthing_date": berthing_match.group(1) if berthing_match else None,
        "charges": charges,
        "charge_total": str(sum((_decimal(row["amount"]) for row in charges), Decimal("0"))),
        "document_total": str(_decimal(total_match.group(1))) if total_match else None,
    }


def _resolve_vendor_mapping(
    clickup_summary: dict[str, Any],
    config: APPurchaseInvoiceSettings,
) -> APPurchaseVendorMapping | None:
    list_info = clickup_summary.get("list") or {}
    list_id = str(list_info.get("id") or "").strip()
    list_name = str(list_info.get("name") or "").strip()
    normalized_list_name = _normalize_key(list_name)
    for mapping in config.vendor_mappings:
        if mapping.list_id and mapping.list_id == list_id:
            return mapping
        if mapping.list_name and _normalize_key(mapping.list_name) == normalized_list_name:
            return mapping
    return None


def _resolve_total_amount(
    custom_fields: dict[str, dict[str, Any]],
    config: APPurchaseInvoiceSettings,
    extracted_pdf: dict[str, Any] | None,
) -> Decimal | None:
    if extracted_pdf:
        for key in ("document_total", "charge_total"):
            value = extracted_pdf.get(key)
            if value:
                return _decimal(value)
    for field_name in config.total_amount_field_names:
        value = field_value(custom_fields, field_name=field_name)
        if value:
            return _decimal(value)
    return None


def _resolve_charge_codes(extracted_pdf: dict[str, Any] | None) -> list[str]:
    charges = (extracted_pdf or {}).get("charges") or []
    return [str(row.get("code") or "").strip().upper() for row in charges if row.get("code")]


def _resolve_finops_status(
    custom_fields: dict[str, dict[str, Any]],
    config: APPurchaseInvoiceSettings,
) -> str:
    for field_name in config.finops_status_field_names:
        label = dropdown_label(custom_fields, field_name=field_name)
        if label:
            return label
        value = field_value(custom_fields, field_name=field_name)
        if value:
            return value
    return ""


def _build_payment_gate(*, finops_status: str, config: APPurchaseInvoiceSettings) -> dict[str, Any]:
    approved = {_normalize_status(label) for label in config.approved_finops_labels}
    normalized = _normalize_status(finops_status)
    if normalized in approved:
        return {
            "can_pay": True,
            "finops_status": finops_status,
            "message": "FINOPS status is approved for payment.",
        }
    return {
        "can_pay": False,
        "finops_status": finops_status or None,
        "message": (
            "AP invoice can be created in Business Central, but payment is blocked until FINOPS status is one of: "
            + ", ".join(config.approved_finops_labels)
        ),
    }


def _build_bc_transfer_comment_line(*, task_id: str, vendor_invoice_number: str) -> dict[str, Any]:
    description = f"ClickUp integration transfer: {task_id} / {vendor_invoice_number}"
    return {
        "lineType": "Comment",
        "description": description[:100],
    }


def _find_vendor(
    *,
    bc_client: BusinessCentralClient,
    vendor_number: str,
    market: str,
) -> dict[str, Any] | None:
    escaped = vendor_number.replace("'", "''")
    rows = bc_client.find_entities("vendors", filters=f"number eq '{escaped}'", top=2, market=market)
    if not rows:
        return None
    if len(rows) > 1:
        raise ValueError(f"More than one Business Central vendor matched {vendor_number}.")
    return rows[0]


def _find_purchase_invoice_by_number(
    *,
    bc_client: BusinessCentralClient,
    invoice_number: str,
    market: str,
) -> dict[str, Any] | None:
    escaped = invoice_number.replace("'", "''")
    rows = bc_client.find_entities(
        "purchaseInvoices",
        filters=f"number eq '{escaped}'",
        top=2,
        market=market,
    )
    if not rows:
        return None
    if len(rows) > 1:
        raise ValueError(f"More than one Business Central purchase invoice matched {invoice_number}.")
    return rows[0]


def _find_purchase_invoice_by_vendor_invoice_number(
    *,
    bc_client: BusinessCentralClient,
    vendor_invoice_number: str,
    market: str,
) -> dict[str, Any] | None:
    escaped = vendor_invoice_number.replace("'", "''")
    rows = bc_client.find_entities(
        "purchaseInvoices",
        filters=f"vendorInvoiceNumber eq '{escaped}'",
        top=2,
        market=market,
    )
    if not rows:
        return None
    if len(rows) > 1:
        raise ValueError(
            f"More than one Business Central purchase invoice matched vendor invoice {vendor_invoice_number}."
        )
    return rows[0]


def _first_present_field(custom_fields: dict[str, dict[str, Any]], field_names: tuple[str, ...]) -> str:
    for field_name in field_names:
        value = field_value(custom_fields, field_name=field_name)
        if value:
            return value
    return ""


def _resolve_date_from_fields(
    custom_fields: dict[str, dict[str, Any]],
    field_names: tuple[str, ...],
) -> date | None:
    for field_name in field_names:
        parsed = _parse_clickup_date(field_value(custom_fields, field_name=field_name))
        if parsed:
            return parsed
    return None


def _parse_clickup_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    if re.fullmatch(r"\d{13}", text):
        from datetime import datetime, UTC

        return datetime.fromtimestamp(int(text) / 1000, tz=UTC).date()
    return _parse_iso_date(text)


def _parse_iso_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _decimal(value: Any) -> Decimal:
    cleaned = re.sub(r"[^0-9.\-]", "", str(value or ""))
    if not cleaned:
        return Decimal("0")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return Decimal("0")


def _compare_value(
    label: str,
    proposed: dict[str, Any],
    existing: dict[str, Any],
) -> dict[str, Any]:
    proposed_value = proposed.get(label)
    existing_value = existing.get(label)
    return {
        "field": label,
        "status": "match" if str(proposed_value or "") == str(existing_value or "") else "mismatch",
        "proposed": proposed_value,
        "existing": existing_value,
    }


def _compare_decimal(label: str, *, proposed_value: Any, existing_value: Any) -> dict[str, Any]:
    proposed_decimal = _decimal(proposed_value)
    existing_decimal = _decimal(existing_value)
    return {
        "field": label,
        "status": "match" if proposed_decimal == existing_decimal else "mismatch",
        "proposed": float(proposed_decimal),
        "existing": float(existing_decimal),
    }


def _env_csv(name: str, *, default: tuple[str, ...]) -> tuple[str, ...]:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _load_vendor_mappings() -> tuple[APPurchaseVendorMapping, ...]:
    raw = os.getenv("CLICKUP_AP_VENDOR_MAPPING_JSON", "").strip()
    if raw:
        decoded = json.loads(raw)
        if not isinstance(decoded, list):
            raise ValueError("CLICKUP_AP_VENDOR_MAPPING_JSON must decode to a list.")
        return tuple(_vendor_mapping_from_dict(item) for item in decoded)

    return (
        APPurchaseVendorMapping(
            list_id="901709663424",
            list_name="AP ONE GT USD",
            vendor_number="P00115",
            item_number="GTO00000115",
            tax_code="NOIVA",
            unit_of_measure_code="SER",
            prices_include_tax=True,
            due_days=15,
        ),
    )


def _vendor_mapping_from_dict(value: dict[str, Any]) -> APPurchaseVendorMapping:
    return APPurchaseVendorMapping(
        list_id=str(value.get("list_id") or "").strip() or None,
        list_name=str(value.get("list_name") or "").strip() or None,
        vendor_number=str(value["vendor_number"]).strip(),
        item_number=str(value["item_number"]).strip(),
        tax_code=str(value.get("tax_code") or "NOIVA").strip(),
        unit_of_measure_code=str(value.get("unit_of_measure_code") or "").strip() or None,
        prices_include_tax=bool(value.get("prices_include_tax", True)),
        due_days=int(value.get("due_days", 15)),
    )


def _normalize_key(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def _normalize_status(value: str) -> str:
    return " ".join((value or "").strip().upper().split())
