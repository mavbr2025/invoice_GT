from __future__ import annotations

import os
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from typing import Any

from business_central_client.client import BusinessCentralClient
from clickup_integration.invoice_sync import (
    InvoiceAutomationSettings,
    InvoiceChargeMapping,
    issue_clickup_bc_sales_invoice,
    prepare_clickup_bc_sales_invoice_preview,
)
from clickup_integration.mapping import resolve_dropdown_field


DEFAULT_STORAGE_AMOUNT_FIELD_ID = "16edb6b2-ba0c-4a1e-94f0-f3f511d2f647"
DEFAULT_STORAGE_DAYS_FIELD_ID = "edcdf91d-ff83-44a9-a869-dbeaff186ce4"
DEFAULT_CONTAINER_COUNT_FIELD_ID = "a05a2c81-2079-4467-9bfe-3723537bd350"
DEFAULT_STORAGE_ITEM_NUMBER = "NAT00000034"
SUPPLEMENTAL_REFERENCE_FIELD_NAME = "Almacenaje supplemental invoice reference"
CONTAINER_DAYS_FIELD_NAME = "Almacenaje container-days"


@dataclass(frozen=True)
class StorageInvoiceSettings:
    required_invoice_status: str = "Facturada"
    amount_field_id: str = DEFAULT_STORAGE_AMOUNT_FIELD_ID
    amount_field_name: str = "Almacenaje al cliente (USD)"
    days_field_id: str = DEFAULT_STORAGE_DAYS_FIELD_ID
    days_field_name: str = "Días de almacenaje incurridos"
    container_count_field_id: str = DEFAULT_CONTAINER_COUNT_FIELD_ID
    container_count_field_name: str = "Number of Containers"
    item_number: str = DEFAULT_STORAGE_ITEM_NUMBER
    item_description: str = "ALMACENAJES EN PUERTO"
    daily_rate: Decimal = Decimal("27")
    reference_suffix: str = "ALM"

    @classmethod
    def from_env(cls) -> "StorageInvoiceSettings":
        return cls(
            required_invoice_status=os.getenv(
                "CLICKUP_STORAGE_INVOICE_REQUIRED_STATUS", "Facturada"
            ).strip()
            or "Facturada",
            amount_field_id=os.getenv(
                "CLICKUP_STORAGE_AMOUNT_FIELD_ID", DEFAULT_STORAGE_AMOUNT_FIELD_ID
            ).strip()
            or DEFAULT_STORAGE_AMOUNT_FIELD_ID,
            amount_field_name=os.getenv(
                "CLICKUP_STORAGE_AMOUNT_FIELD_NAME", "Almacenaje al cliente (USD)"
            ).strip()
            or "Almacenaje al cliente (USD)",
            days_field_id=os.getenv(
                "CLICKUP_STORAGE_DAYS_FIELD_ID", DEFAULT_STORAGE_DAYS_FIELD_ID
            ).strip()
            or DEFAULT_STORAGE_DAYS_FIELD_ID,
            days_field_name=os.getenv(
                "CLICKUP_STORAGE_DAYS_FIELD_NAME", "Días de almacenaje incurridos"
            ).strip()
            or "Días de almacenaje incurridos",
            container_count_field_id=os.getenv(
                "CLICKUP_STORAGE_CONTAINER_COUNT_FIELD_ID", DEFAULT_CONTAINER_COUNT_FIELD_ID
            ).strip()
            or DEFAULT_CONTAINER_COUNT_FIELD_ID,
            container_count_field_name=os.getenv(
                "CLICKUP_STORAGE_CONTAINER_COUNT_FIELD_NAME", "Number of Containers"
            ).strip()
            or "Number of Containers",
            item_number=os.getenv(
                "CLICKUP_STORAGE_BC_ITEM_NUMBER", DEFAULT_STORAGE_ITEM_NUMBER
            ).strip()
            or DEFAULT_STORAGE_ITEM_NUMBER,
            item_description=os.getenv(
                "CLICKUP_STORAGE_BC_ITEM_DESCRIPTION", "ALMACENAJES EN PUERTO"
            ).strip()
            or "ALMACENAJES EN PUERTO",
            daily_rate=_env_decimal("CLICKUP_STORAGE_DAILY_RATE", default=Decimal("27")),
            reference_suffix=os.getenv("CLICKUP_STORAGE_REFERENCE_SUFFIX", "ALM").strip()
            or "ALM",
        )


def prepare_clickup_bc_storage_invoice_preview(
    *,
    clickup_summary: dict[str, Any],
    bc_client: BusinessCentralClient,
    invoice_settings: InvoiceAutomationSettings | None = None,
    storage_settings: StorageInvoiceSettings | None = None,
) -> dict[str, Any]:
    base_settings = invoice_settings or InvoiceAutomationSettings.from_env()
    config = storage_settings or StorageInvoiceSettings.from_env()
    validation = _validate_storage_source(clickup_summary=clickup_summary, settings=config)
    if validation["status"] != "passed":
        return validation

    synthetic_summary, synthetic_settings = _prepare_synthetic_invoice_inputs(
        clickup_summary=clickup_summary,
        invoice_settings=base_settings,
        storage_settings=config,
        validation=validation,
    )
    preview = prepare_clickup_bc_sales_invoice_preview(
        clickup_summary=synthetic_summary,
        bc_client=bc_client,
        settings=synthetic_settings,
    )
    if preview.get("status") == "dry_run_ready":
        legacy_duplicate = _find_legacy_storage_invoice(
            bc_client=bc_client,
            market=str(preview.get("market") or "GT"),
            base_reference=validation["base_reference"],
            customer_number=preview.get("customer_number"),
            item_number=config.item_number,
            expected_total=Decimal(str(validation["amount"])),
        )
        if legacy_duplicate:
            return {
                **preview,
                "status": "duplicate_invoice",
                "message": "An existing Business Central Almacenaje invoice matches this shipment and amount.",
                "reference": legacy_duplicate.get("externalDocumentNumber"),
                "invoice_group": "ALM",
                "existing_invoice": legacy_duplicate,
                "duplicate_invoices": [
                    {
                        "invoice_group": "ALM",
                        "reference": legacy_duplicate.get("externalDocumentNumber"),
                        "existing_invoice": legacy_duplicate,
                    }
                ],
                "legacy_storage_reference": True,
                "storage_validation": validation,
            }

    return {
        **preview,
        "storage_validation": validation,
        "supplemental_invoice": True,
    }


def issue_clickup_bc_storage_invoice(
    *,
    clickup_summary: dict[str, Any],
    bc_client: BusinessCentralClient,
    invoice_settings: InvoiceAutomationSettings | None = None,
    storage_settings: StorageInvoiceSettings | None = None,
) -> dict[str, Any]:
    base_settings = invoice_settings or InvoiceAutomationSettings.from_env()
    config = storage_settings or StorageInvoiceSettings.from_env()
    preview = prepare_clickup_bc_storage_invoice_preview(
        clickup_summary=clickup_summary,
        bc_client=bc_client,
        invoice_settings=base_settings,
        storage_settings=config,
    )
    if preview.get("status") == "duplicate_invoice":
        return _recover_stamped_existing_invoice(preview)
    if preview.get("status") != "dry_run_ready":
        return preview

    validation = preview["storage_validation"]
    synthetic_summary, synthetic_settings = _prepare_synthetic_invoice_inputs(
        clickup_summary=clickup_summary,
        invoice_settings=base_settings,
        storage_settings=config,
        validation=validation,
    )
    result = issue_clickup_bc_sales_invoice(
        clickup_summary=synthetic_summary,
        bc_client=bc_client,
        settings=synthetic_settings,
    )
    return _label_storage_invoice_result(
        {
            **result,
            "storage_validation": validation,
            "supplemental_invoice": True,
        }
    )


def _validate_storage_source(
    *,
    clickup_summary: dict[str, Any],
    settings: StorageInvoiceSettings,
) -> dict[str, Any]:
    custom_fields = clickup_summary.get("custom_fields") or {}
    invoice_status = _resolve_invoice_status(custom_fields, clickup_summary)
    market = str(clickup_summary.get("market") or "").strip().upper()
    if market != "GT":
        return {
            "status": "unsupported_market",
            "message": "Almacenaje supplemental invoices only support Guatemala.",
            "market": market or None,
        }
    if _normalize(invoice_status) != _normalize(settings.required_invoice_status):
        return {
            "status": "not_previously_invoiced",
            "message": (
                f"The normal invoice status must already be {settings.required_invoice_status} "
                "before an Almacenaje supplement can be issued."
            ),
            "task_status": invoice_status,
        }

    amount_field = _field_by_id_or_name(
        custom_fields,
        field_id=settings.amount_field_id,
        field_name=settings.amount_field_name,
    )
    days_field = _field_by_id_or_name(
        custom_fields,
        field_id=settings.days_field_id,
        field_name=settings.days_field_name,
    )
    containers_field = _field_by_id_or_name(
        custom_fields,
        field_id=settings.container_count_field_id,
        field_name=settings.container_count_field_name,
    )
    amount = _decimal_value((amount_field or {}).get("value"))
    days = _positive_integral_value((days_field or {}).get("value"))
    containers = _positive_integral_value((containers_field or {}).get("value"))
    missing = []
    if amount is None or amount <= 0:
        missing.append(settings.amount_field_name)
    if days is None:
        missing.append(settings.days_field_name)
    if containers is None:
        missing.append(settings.container_count_field_name)
    if missing:
        return {
            "status": "missing_storage_data",
            "message": "Missing or invalid Almacenaje billing data.",
            "missing_fields": missing,
            "task_status": invoice_status,
        }

    expected_amount = settings.daily_rate * Decimal(days) * Decimal(containers)
    if abs(amount - expected_amount) >= Decimal("0.01"):
        return {
            "status": "storage_amount_mismatch",
            "message": "The ClickUp Almacenaje amount does not reconcile to days, containers, and rate.",
            "amount": float(amount),
            "expected_amount": float(expected_amount),
            "days": days,
            "containers": containers,
            "daily_rate": float(settings.daily_rate),
        }

    base_reference = str(
        clickup_summary.get("custom_id") or clickup_summary.get("task_id") or ""
    ).strip()
    if not base_reference:
        return {
            "status": "missing_reference",
            "message": "A ClickUp custom task ID or task ID is required for Almacenaje invoicing.",
        }
    calculation_state = str(
        ((amount_field or {}).get("type_config") or {}).get("calculation_state") or ""
    ).strip().lower()
    warnings = []
    if calculation_state and calculation_state != "ready":
        warnings.append(
            {
                "reason": "amount_formula_not_ready",
                "calculation_state": calculation_state,
                "accepted_because": "component_recalculation_matches",
            }
        )

    return {
        "status": "passed",
        "message": "Almacenaje source values reconcile.",
        "task_status": invoice_status,
        "base_reference": base_reference,
        "supplemental_reference": f"{base_reference}-{settings.reference_suffix}",
        "amount": float(amount),
        "days": days,
        "containers": containers,
        "container_days": days * containers,
        "daily_rate": float(settings.daily_rate),
        "item_number": settings.item_number,
        "amount_formula_state": calculation_state or None,
        "warnings": warnings,
    }


def _prepare_synthetic_invoice_inputs(
    *,
    clickup_summary: dict[str, Any],
    invoice_settings: InvoiceAutomationSettings,
    storage_settings: StorageInvoiceSettings,
    validation: dict[str, Any],
) -> tuple[dict[str, Any], InvoiceAutomationSettings]:
    custom_fields = dict(clickup_summary.get("custom_fields") or {})
    custom_fields[SUPPLEMENTAL_REFERENCE_FIELD_NAME] = {
        "id": "storage-supplemental-reference",
        "type": "short_text",
        "value": validation["supplemental_reference"],
    }
    custom_fields[CONTAINER_DAYS_FIELD_NAME] = {
        "id": "storage-container-days",
        "type": "number",
        "value": validation["container_days"],
    }
    synthetic_summary = {**clickup_summary, "custom_fields": custom_fields}
    synthetic_settings = replace(
        invoice_settings,
        ready_status=storage_settings.required_invoice_status,
        reference_field_names=(SUPPLEMENTAL_REFERENCE_FIELD_NAME,),
        charge_mappings=(
            InvoiceChargeMapping(
                charge_name=storage_settings.amount_field_name,
                clickup_field_name=storage_settings.amount_field_name,
                clickup_field_id=storage_settings.amount_field_id,
                bc_item_number=storage_settings.item_number,
                bc_description=storage_settings.item_description,
                tax_group="IVA 12",
                quantity_basis="container_count",
            ),
        ),
        split_invoice_by_item_prefix=False,
        int_split_customer_numbers=(),
        shipment_container_count_field_names=(CONTAINER_DAYS_FIELD_NAME,),
    )
    return synthetic_summary, synthetic_settings


def _find_legacy_storage_invoice(
    *,
    bc_client: BusinessCentralClient,
    market: str,
    base_reference: str,
    customer_number: str | None,
    item_number: str,
    expected_total: Decimal,
) -> dict[str, Any] | None:
    escaped_reference = base_reference.replace("'", "''")
    filters = [f"externalDocumentNumber eq '{escaped_reference}'"]
    if customer_number:
        filters.append(f"customerNumber eq '{str(customer_number).replace(chr(39), chr(39) * 2)}'")
    rows = bc_client.find_entities(
        "salesInvoices",
        filters=" and ".join(filters),
        top=10,
        market=market,
    )
    for invoice in rows:
        invoice_total = _decimal_value(invoice.get("totalAmountIncludingTax"))
        if invoice_total is None or abs(invoice_total - expected_total) >= Decimal("0.01"):
            continue
        invoice_id = str(invoice.get("id") or "").strip()
        if not invoice_id or not hasattr(bc_client, "get_posted_sales_invoice_lines"):
            continue
        lines = bc_client.get_posted_sales_invoice_lines(invoice_id, market=market)
        if not any(str(line.get("lineObjectNumber") or "").strip() == item_number for line in lines):
            continue
        invoice_number = str(invoice.get("number") or "").strip()
        fel_row = (
            bc_client.get_posted_invoice_fel_description_by_number(invoice_number, market=market)
            if invoice_number and hasattr(bc_client, "get_posted_invoice_fel_description_by_number")
            else None
        )
        return {**invoice, "existing_fel_row": fel_row}
    return None


def _recover_stamped_existing_invoice(preview: dict[str, Any]) -> dict[str, Any]:
    invoice = preview.get("existing_invoice") or {}
    fel_row = invoice.get("existing_fel_row") or {}
    if str(fel_row.get("electronicDocumentStatus") or "").strip().lower() != "stamp received":
        return {
            **preview,
            "status": "existing_invoice_requires_recovery",
            "message": "The existing Almacenaje invoice is not FEL-stamped and requires review.",
        }
    return {
        **preview,
        "status": "applied",
        "message": "Reusing the existing stamped manual Almacenaje invoice for delivery.",
        "reused_existing_storage_invoice": True,
        "created_invoices": [{**invoice, "invoice_group": "ALM"}],
        "finalized_invoices": [
            {
                "invoice_group": "ALM",
                "externalDocumentNumber": invoice.get("externalDocumentNumber"),
                "posted_invoice_after_stamp": invoice,
                "custom_api_row_after_stamp": fel_row,
            }
        ],
        "completed_stages": ["reuse_existing_posted_storage_invoice"],
    }


def _label_storage_invoice_result(result: dict[str, Any]) -> dict[str, Any]:
    labeled = dict(result)
    for key in ("created_invoices", "posted_invoices"):
        labeled[key] = [
            {**invoice, "invoice_group": "ALM"}
            for invoice in result.get(key) or []
            if isinstance(invoice, dict)
        ]
    labeled["finalized_invoices"] = [
        {**invoice, "invoice_group": "ALM"}
        for invoice in result.get("finalized_invoices") or []
        if isinstance(invoice, dict)
    ]
    return labeled


def _resolve_invoice_status(
    custom_fields: dict[str, dict[str, Any]],
    clickup_summary: dict[str, Any],
) -> str:
    for field in custom_fields.values():
        if str(field.get("id") or "") != "b436ff28-24d8-4a5a-9f7e-66623401dee1":
            continue
        option = resolve_dropdown_field(field)
        if option and option.get("name"):
            return str(option["name"])
    for name in (
        "Estatus de facturación (USD)/",
        "Estatus de Facturacion (USD)",
        "Invoice Status",
    ):
        option = resolve_dropdown_field(custom_fields.get(name))
        if option and option.get("name"):
            return str(option["name"])
    return str(clickup_summary.get("status") or "")


def _field_by_id_or_name(
    custom_fields: dict[str, dict[str, Any]],
    *,
    field_id: str,
    field_name: str,
) -> dict[str, Any] | None:
    for name, field in custom_fields.items():
        if str(field.get("id") or "") == field_id or name == field_name:
            return field
    return None


def _decimal_value(value: Any) -> Decimal | None:
    if value in {None, ""}:
        return None
    try:
        return Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None


def _positive_integral_value(value: Any) -> int | None:
    parsed = _decimal_value(value)
    if parsed is None or parsed <= 0 or parsed != parsed.to_integral_value():
        return None
    return int(parsed)


def _env_decimal(name: str, *, default: Decimal) -> Decimal:
    parsed = _decimal_value(os.getenv(name, ""))
    return parsed if parsed is not None and parsed > 0 else default


def _normalize(value: Any) -> str:
    return " ".join(str(value or "").strip().casefold().split())
