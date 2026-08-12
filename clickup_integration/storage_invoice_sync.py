from __future__ import annotations

import os
import re
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
from clickup_integration.mapping import summarize_task_for_customer_mapping


DEFAULT_STORAGE_AMOUNT_FIELD_ID = "16edb6b2-ba0c-4a1e-94f0-f3f511d2f647"
DEFAULT_STORAGE_DAYS_FIELD_ID = "edcdf91d-ff83-44a9-a869-dbeaff186ce4"
DEFAULT_CONTAINER_COUNT_FIELD_ID = "a05a2c81-2079-4467-9bfe-3723537bd350"
DEFAULT_STORAGE_CUT_FIELD_ID = "f8bb0632-c52d-43ed-b9a8-02c8d3635e9a"
DEFAULT_STORAGE_INVOICED_FIELD_ID = "2ead1265-65a3-4409-9f77-2af138421dcb"
DEFAULT_STORAGE_ITEM_NUMBER = "NAT00000034"
DEFAULT_STORAGE_INVOICE_ATTACHMENT_FIELD_ID = "c4994b71-cff2-46a3-b169-08f5019e0a93"
DEFAULT_INVOICE_TO_CLIENT_FIELD_ID = "5d67859a-1ae0-4cda-9f57-2a89bf1ff259"
SUPPLEMENTAL_REFERENCE_FIELD_NAME = "Almacenaje supplemental invoice reference"
STORAGE_DAYS_FIELD_NAME = "Almacenaje days per container"


@dataclass(frozen=True)
class StorageInvoiceSettings:
    required_invoice_status: str = "Facturada"
    amount_field_id: str = DEFAULT_STORAGE_AMOUNT_FIELD_ID
    amount_field_name: str = "Almacenaje al cliente (USD)"
    days_field_id: str = DEFAULT_STORAGE_DAYS_FIELD_ID
    days_field_name: str = "Días de almacenaje incurridos"
    container_count_field_id: str = DEFAULT_CONTAINER_COUNT_FIELD_ID
    container_count_field_name: str = "Number of Containers"
    cut_field_id: str = DEFAULT_STORAGE_CUT_FIELD_ID
    invoiced_field_id: str = DEFAULT_STORAGE_INVOICED_FIELD_ID
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
            cut_field_id=os.getenv(
                "CLICKUP_STORAGE_CUT_FIELD_ID", DEFAULT_STORAGE_CUT_FIELD_ID
            ).strip()
            or DEFAULT_STORAGE_CUT_FIELD_ID,
            invoiced_field_id=os.getenv(
                "CLICKUP_STORAGE_INVOICED_FIELD_ID", DEFAULT_STORAGE_INVOICED_FIELD_ID
            ).strip()
            or DEFAULT_STORAGE_INVOICED_FIELD_ID,
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


def build_clickup_storage_invoice_context(
    *,
    requested_task: dict[str, Any],
    invoice_task: dict[str, Any],
    storage_settings: StorageInvoiceSettings | None = None,
) -> dict[str, Any]:
    """Build one parent-owned invoice context from per-container ClickUp subtasks."""
    config = storage_settings or StorageInvoiceSettings.from_env()
    requested_summary = summarize_task_for_customer_mapping(requested_task)
    invoice_summary = summarize_task_for_customer_mapping(invoice_task)
    entries: list[dict[str, Any]] = []
    for child in invoice_task.get("subtasks") or []:
        child_summary = summarize_task_for_customer_mapping(child)
        fields = child_summary.get("custom_fields") or {}
        amount_field = _field_by_id_or_name(
            fields, field_id=config.amount_field_id, field_name=config.amount_field_name
        )
        days_field = _field_by_id_or_name(
            fields, field_id=config.days_field_id, field_name=config.days_field_name
        )
        count_field = _field_by_id_or_name(
            fields,
            field_id=config.container_count_field_id,
            field_name=config.container_count_field_name,
        )
        cut_field = _field_by_id_or_name(fields, field_id=config.cut_field_id, field_name="")
        invoiced_field = _field_by_id_or_name(
            fields, field_id=config.invoiced_field_id, field_name=""
        )
        amount = _decimal_value((amount_field or {}).get("value"))
        days = _positive_integral_value((days_field or {}).get("value"))
        containers = _positive_integral_value((count_field or {}).get("value"))
        already_invoiced = _truthy((invoiced_field or {}).get("value"))
        if (
            not _truthy((cut_field or {}).get("value"))
            or amount is None
            or amount <= 0
            or days is None
        ):
            continue
        if containers != 1:
            continue
        entries.append(
            {
                "task_id": child_summary.get("task_id"),
                "custom_id": child_summary.get("custom_id"),
                "container": str(child_summary.get("name") or "").strip(),
                "amount": float(amount),
                "days": days,
                "containers": containers,
                "cut": True,
                "already_marked_invoiced": already_invoiced,
                "amount_formula_state": str(
                    ((amount_field or {}).get("type_config") or {}).get("calculation_state") or ""
                ).strip().lower()
                or None,
            }
        )

    requested_has_parent = bool(requested_task.get("parent"))
    if not entries and not requested_has_parent:
        return {
            **requested_summary,
            "storage_context_mode": "legacy_task",
            "storage_requested_task_id": requested_summary.get("task_id"),
        }
    return {
        **invoice_summary,
        "storage_context_mode": "parent_subtasks",
        "storage_requested_task_id": requested_summary.get("task_id"),
        "storage_requested_custom_id": requested_summary.get("custom_id"),
        "storage_entries": entries,
    }


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
    validation = _reconcile_storage_invoice_history(
        clickup_summary=clickup_summary,
        bc_client=bc_client,
        validation=validation,
        settings=config,
    )
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
    customer_guard = _validate_storage_history_customer(
        validation=validation,
        customer_number=preview.get("customer_number"),
    )
    if customer_guard:
        return customer_guard
    if preview.get("status") == "dry_run_ready":
        split_invoices = _find_active_split_storage_invoices(
            bc_client=bc_client,
            market=str(preview.get("market") or "GT"),
            customer_number=preview.get("customer_number"),
            entries=validation.get("entries") or [],
            item_number=config.item_number,
            reference_suffix=config.reference_suffix,
        )
        if split_invoices:
            return {
                **preview,
                "status": "replacement_required",
                "message": (
                    "Active per-container Almacenaje invoices must be cancelled before the "
                    "consolidated parent invoice can be issued."
                ),
                "invoice_group": "ALM",
                "replacement_reference": validation["supplemental_reference"],
                "invoices_to_cancel": split_invoices,
                "storage_validation": validation,
                "supplemental_invoice": True,
            }
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

    entries = clickup_summary.get("storage_entries") or []
    base_reference = str(
        clickup_summary.get("custom_id") or clickup_summary.get("task_id") or ""
    ).strip()
    if not base_reference:
        return {
            "status": "missing_reference",
            "message": "A ClickUp custom task ID or task ID is required for Almacenaje invoicing.",
        }
    if entries:
        return _validate_storage_entries(
            entries=entries,
            invoice_status=invoice_status,
            base_reference=base_reference,
            settings=settings,
        )
    if clickup_summary.get("storage_context_mode") == "parent_subtasks":
        return {
            "status": "missing_storage_entries",
            "message": (
                "No uninvoiced per-container subtasks are ready for consolidated Almacenaje billing."
            ),
            "base_reference": base_reference,
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
        "entries": _legacy_storage_entries(
            custom_fields=custom_fields,
            days=days,
            containers=containers,
            settings=settings,
        ),
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
    custom_fields[STORAGE_DAYS_FIELD_NAME] = {
        "id": "storage-days-per-container",
        "type": "number",
        "value": validation["days"],
    }
    charge_mappings = []
    entries = validation.get("entries") or [
        {
            "container": f"Container {container_index}",
            "days": validation["days"],
            "amount": float(storage_settings.daily_rate * Decimal(validation["days"])),
        }
        for container_index in range(1, int(validation["containers"]) + 1)
    ]
    for container_index, entry in enumerate(entries, start=1):
        field_name = f"Almacenaje container {container_index}"
        field_id = f"storage-container-{container_index}"
        quantity_field_name = f"Almacenaje days container {container_index}"
        quantity_field_id = f"storage-days-container-{container_index}"
        custom_fields[field_name] = {
            "id": field_id,
            "type": "number",
            "value": entry["amount"],
        }
        custom_fields[quantity_field_name] = {
            "id": quantity_field_id,
            "type": "number",
            "value": entry["days"],
        }
        charge_mappings.append(
            InvoiceChargeMapping(
                charge_name=field_name,
                clickup_field_name=field_name,
                clickup_field_id=field_id,
                bc_item_number=storage_settings.item_number,
                bc_description=(
                    f"{storage_settings.item_description} - {entry['container']}"
                    if entry.get("container")
                    else storage_settings.item_description
                ),
                tax_group="IVA 12",
                quantity_basis="container_count",
                quantity_field_name=quantity_field_name,
                quantity_field_id=quantity_field_id,
            )
        )
    synthetic_summary = {**clickup_summary, "custom_fields": custom_fields}
    synthetic_settings = replace(
        invoice_settings,
        ready_status=storage_settings.required_invoice_status,
        reference_field_names=(SUPPLEMENTAL_REFERENCE_FIELD_NAME,),
        charge_mappings=tuple(charge_mappings),
        split_invoice_by_item_prefix=False,
        int_split_customer_numbers=(),
        shipment_container_count_field_names=(STORAGE_DAYS_FIELD_NAME,),
    )
    return synthetic_summary, synthetic_settings


def _validate_storage_entries(
    *,
    entries: list[dict[str, Any]],
    invoice_status: str,
    base_reference: str,
    settings: StorageInvoiceSettings,
) -> dict[str, Any]:
    seen_containers: set[str] = set()
    normalized_entries: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for entry in entries:
        container = str(entry.get("container") or "").strip()
        amount = _decimal_value(entry.get("amount"))
        days = _positive_integral_value(entry.get("days"))
        if not container or _normalize(container) in seen_containers:
            return {
                "status": "invalid_storage_entries",
                "message": "Each Almacenaje subtask must identify one unique container.",
            }
        seen_containers.add(_normalize(container))
        expected_amount = settings.daily_rate * Decimal(days or 0)
        if amount is None or days is None or abs(amount - expected_amount) >= Decimal("0.01"):
            return {
                "status": "storage_amount_mismatch",
                "message": f"Almacenaje for container {container} does not reconcile.",
                "container": container,
                "amount": float(amount) if amount is not None else None,
                "expected_amount": float(expected_amount),
                "days": days,
                "daily_rate": float(settings.daily_rate),
            }
        normalized = {**entry, "container": container, "amount": float(amount), "days": days}
        normalized_entries.append(normalized)
        formula_state = str(entry.get("amount_formula_state") or "").strip().lower()
        if formula_state and formula_state != "ready":
            warnings.append(
                {
                    "reason": "amount_formula_not_ready",
                    "container": container,
                    "calculation_state": formula_state,
                    "accepted_because": "component_recalculation_matches",
                }
            )
    total = sum(Decimal(str(entry["amount"])) for entry in normalized_entries)
    container_days = sum(int(entry["days"]) for entry in normalized_entries)
    return {
        "status": "passed",
        "message": "Per-container Almacenaje source values reconcile.",
        "task_status": invoice_status,
        "base_reference": base_reference,
        "supplemental_reference": f"{base_reference}-{settings.reference_suffix}",
        "amount": float(total),
        "days": None,
        "containers": len(normalized_entries),
        "container_days": container_days,
        "daily_rate": float(settings.daily_rate),
        "item_number": settings.item_number,
        "aggregation_mode": "parent_subtasks",
        "entries": normalized_entries,
        "warnings": warnings,
    }


def _reconcile_storage_invoice_history(
    *,
    clickup_summary: dict[str, Any],
    bc_client: BusinessCentralClient,
    validation: dict[str, Any],
    settings: StorageInvoiceSettings,
) -> dict[str, Any]:
    market = str(clickup_summary.get("market") or "GT").strip().upper() or "GT"
    history = _discover_storage_invoice_history(
        clickup_summary=clickup_summary,
        bc_client=bc_client,
        base_reference=str(validation["base_reference"]),
        market=market,
        settings=settings,
    )
    if history.get("status") != "passed":
        return {**validation, **history}

    active_invoices = history["active_storage_invoices"]
    invoiced_amount = Decimal(str(history["invoiced_amount"]))
    invoiced_days = int(history["invoiced_container_days"])
    gross_amount = Decimal(str(validation["amount"]))
    gross_days = int(validation["container_days"])
    pending_amount = gross_amount - invoiced_amount
    pending_days = gross_days - invoiced_days
    reconciliation = {
        "billable_to_date": float(gross_amount),
        "billable_container_days": gross_days,
        "active_invoiced": float(invoiced_amount),
        "active_invoiced_container_days": invoiced_days,
        "pending_to_invoice": float(pending_amount),
        "pending_container_days": pending_days,
        "daily_rate": float(settings.daily_rate),
        "active_storage_invoices": active_invoices,
        "canceled_storage_invoices": history["canceled_storage_invoices"],
    }
    child_references = {
        f"{str(entry.get('custom_id') or entry.get('task_id') or '').strip()}-{settings.reference_suffix}"
        for entry in validation.get("entries") or []
        if str(entry.get("custom_id") or entry.get("task_id") or "").strip()
    }
    if child_references and any(
        str(invoice.get("externalDocumentNumber") or "").strip() in child_references
        for invoice in active_invoices
    ):
        return {
            **validation,
            "storage_reconciliation": reconciliation,
            "split_invoice_replacement_detected": True,
        }
    if pending_amount < Decimal("-0.01") or pending_days < 0:
        return {
            **validation,
            "status": "storage_overinvoiced",
            "message": "Active Business Central Almacenaje invoices exceed the ClickUp billable total.",
            "storage_reconciliation": reconciliation,
        }
    expected_pending = settings.daily_rate * Decimal(pending_days)
    if abs(pending_amount - expected_pending) >= Decimal("0.01"):
        return {
            **validation,
            "status": "storage_history_mismatch",
            "message": (
                "The remaining Almacenaje amount does not reconcile to remaining container-days "
                "at the configured daily rate."
            ),
            "expected_pending_amount": float(expected_pending),
            "storage_reconciliation": reconciliation,
        }
    if abs(pending_amount) < Decimal("0.01") and pending_days == 0:
        return {
            **validation,
            "status": "fully_invoiced",
            "message": "Almacenaje is fully invoiced through the current ClickUp cut.",
            "amount": 0.0,
            "container_days": 0,
            "storage_reconciliation": reconciliation,
        }

    pending_entries = _allocate_pending_storage_entries(
        entries=validation.get("entries") or [],
        invoice_lines=history["active_storage_lines"],
        settings=settings,
    )
    if pending_entries.get("status") != "passed":
        return {
            **validation,
            **pending_entries,
            "storage_reconciliation": reconciliation,
        }

    invoice_sequence = len(active_invoices) + 1
    base_supplemental_reference = f"{validation['base_reference']}-{settings.reference_suffix}"
    supplemental_reference = (
        base_supplemental_reference
        if invoice_sequence == 1
        else f"{base_supplemental_reference}-{invoice_sequence:02d}"
    )
    reconciled = {
        **validation,
        "supplemental_reference": supplemental_reference,
        "billable_amount": float(gross_amount),
        "billable_container_days": gross_days,
        "amount": float(pending_amount),
        "container_days": pending_days,
        "invoice_sequence": invoice_sequence,
        "storage_reconciliation": reconciliation,
        "message": "Almacenaje pending amount reconciles after active Business Central invoices.",
    }
    if validation.get("entries"):
        reconciled["entries"] = pending_entries["entries"]
        reconciled["containers"] = len(pending_entries["entries"])
        reconciled["days"] = None
    else:
        containers = int(validation["containers"])
        if pending_days % containers:
            return {
                **reconciled,
                "status": "ambiguous_storage_history",
                "message": "Pending Almacenaje container-days cannot be distributed evenly.",
            }
        reconciled["days"] = pending_days // containers
    return reconciled


def _discover_storage_invoice_history(
    *,
    clickup_summary: dict[str, Any],
    bc_client: BusinessCentralClient,
    base_reference: str,
    market: str,
    settings: StorageInvoiceSettings,
) -> dict[str, Any]:
    references = {base_reference}
    task_name = str(clickup_summary.get("name") or "").strip()
    if task_name:
        references.add(task_name)
    for entry in clickup_summary.get("storage_entries") or []:
        for key in ("custom_id", "task_id"):
            value = str(entry.get(key) or "").strip()
            if value:
                references.add(value)

    rows_by_id: dict[str, dict[str, Any]] = {}
    for reference in sorted(references):
        escaped = reference.replace("'", "''")
        rows = bc_client.find_entities(
            "salesInvoices",
            filters=f"contains(externalDocumentNumber, '{escaped}')",
            top=100,
            market=market,
        )
        for row in rows:
            invoice_id = str(row.get("id") or "").strip()
            if invoice_id:
                rows_by_id[invoice_id] = row

    for invoice_number in _attached_storage_invoice_numbers(clickup_summary):
        if not hasattr(bc_client, "get_posted_sales_invoice_by_number"):
            continue
        row = bc_client.get_posted_sales_invoice_by_number(invoice_number, market=market)
        invoice_id = str((row or {}).get("id") or "").strip()
        if invoice_id:
            rows_by_id[invoice_id] = row or {}

    active_invoices: list[dict[str, Any]] = []
    canceled_invoices: list[dict[str, Any]] = []
    active_lines: list[dict[str, Any]] = []
    invoiced_amount = Decimal("0")
    invoiced_days = 0
    for invoice in rows_by_id.values():
        invoice_id = str(invoice.get("id") or "").strip()
        lines = bc_client.get_posted_sales_invoice_lines(invoice_id, market=market)
        storage_lines = [
            line
            for line in lines
            if str(line.get("lineObjectNumber") or "").strip() == settings.item_number
        ]
        if not storage_lines:
            continue
        invoice_number = str(invoice.get("number") or "").strip()
        fel_row = (
            bc_client.get_posted_invoice_fel_description_by_number(invoice_number, market=market)
            if invoice_number
            and hasattr(bc_client, "get_posted_invoice_fel_description_by_number")
            else None
        ) or {}
        canceled = _invoice_is_canceled(invoice=invoice, fel_row=fel_row)
        invoice_summary = {
            "id": invoice_id,
            "number": invoice_number,
            "externalDocumentNumber": invoice.get("externalDocumentNumber"),
            "customerNumber": invoice.get("customerNumber"),
            "customerName": invoice.get("customerName"),
            "currencyCode": invoice.get("currencyCode"),
            "status": invoice.get("status"),
            "fel_status": fel_row.get("electronicDocumentStatus"),
            "storage_lines": [],
        }
        for line in storage_lines:
            quantity = _positive_integral_value(line.get("quantity"))
            unit_price = _decimal_value(line.get("unitPrice"))
            amount = _decimal_value(line.get("amountIncludingTax"))
            if quantity is None or unit_price is None or amount is None:
                return {
                    "status": "storage_history_requires_review",
                    "message": f"Storage line data is incomplete on Business Central invoice {invoice_number}.",
                }
            if abs(unit_price - settings.daily_rate) >= Decimal("0.00001"):
                return {
                    "status": "storage_history_rate_mismatch",
                    "message": f"Business Central invoice {invoice_number} uses an unexpected storage rate.",
                    "invoice_number": invoice_number,
                    "unit_price": float(unit_price),
                    "expected_daily_rate": float(settings.daily_rate),
                }
            if abs(amount - (settings.daily_rate * Decimal(quantity))) >= Decimal("0.01"):
                return {
                    "status": "storage_history_amount_mismatch",
                    "message": f"Storage line amount does not reconcile on invoice {invoice_number}.",
                }
            line_summary = {
                "invoice_number": invoice_number,
                "description": line.get("description"),
                "quantity": quantity,
                "unit_price": float(unit_price),
                "amount": float(amount),
            }
            invoice_summary["storage_lines"].append(line_summary)
            if not canceled:
                invoiced_days += quantity
                invoiced_amount += amount
                active_lines.append(line_summary)
        if canceled:
            canceled_invoices.append(invoice_summary)
        else:
            fel_status = _normalize(fel_row.get("electronicDocumentStatus"))
            if fel_status and fel_status != "stamp received":
                return {
                    "status": "storage_history_requires_review",
                    "message": (
                        f"Active storage invoice {invoice_number} is not FEL stamped and requires review."
                    ),
                    "invoice": invoice_summary,
                }
            active_invoices.append(invoice_summary)
    return {
        "status": "passed",
        "active_storage_invoices": active_invoices,
        "canceled_storage_invoices": canceled_invoices,
        "active_storage_lines": active_lines,
        "invoiced_amount": float(invoiced_amount),
        "invoiced_container_days": invoiced_days,
    }


def _allocate_pending_storage_entries(
    *,
    entries: list[dict[str, Any]],
    invoice_lines: list[dict[str, Any]],
    settings: StorageInvoiceSettings,
) -> dict[str, Any]:
    if not entries:
        return {"status": "passed", "entries": []}
    invoiced_by_container = {_container_key(entry["container"]): 0 for entry in entries}
    for line in invoice_lines:
        description_key = _container_key(line.get("description"))
        matches = [key for key in invoiced_by_container if key and key in description_key]
        if len(entries) == 1 and not matches:
            matches = [next(iter(invoiced_by_container))]
        if len(matches) != 1:
            return {
                "status": "ambiguous_storage_history",
                "message": (
                    f"Storage invoice {line.get('invoice_number')} cannot be attributed to exactly one container."
                ),
                "line": line,
            }
        invoiced_by_container[matches[0]] += int(line["quantity"])

    pending_entries = []
    for entry in entries:
        container_key = _container_key(entry["container"])
        pending_days = int(entry["days"]) - invoiced_by_container[container_key]
        if pending_days < 0:
            return {
                "status": "storage_overinvoiced",
                "message": f"Container {entry['container']} has more invoiced days than billable days.",
            }
        if pending_days == 0:
            continue
        pending_entries.append(
            {
                **entry,
                "billable_days": int(entry["days"]),
                "invoiced_days": invoiced_by_container[container_key],
                "days": pending_days,
                "amount": float(settings.daily_rate * Decimal(pending_days)),
            }
        )
    return {"status": "passed", "entries": pending_entries}


def _validate_storage_history_customer(
    *,
    validation: dict[str, Any],
    customer_number: Any,
) -> dict[str, Any] | None:
    expected = str(customer_number or "").strip()
    if not expected:
        return None
    mismatches = [
        invoice
        for invoice in (validation.get("storage_reconciliation") or {}).get(
            "active_storage_invoices", []
        )
        if str(invoice.get("customerNumber") or "").strip() != expected
    ]
    if not mismatches:
        return None
    return {
        **validation,
        "status": "storage_history_customer_mismatch",
        "message": "Historical Almacenaje invoices do not match the currently resolved BC customer.",
        "expected_customer_number": expected,
        "mismatched_invoices": mismatches,
    }


def _attached_storage_invoice_numbers(clickup_summary: dict[str, Any]) -> set[str]:
    numbers: set[str] = set()
    for field in (clickup_summary.get("custom_fields") or {}).values():
        if str(field.get("id") or "") not in {
            DEFAULT_STORAGE_INVOICE_ATTACHMENT_FIELD_ID,
            DEFAULT_INVOICE_TO_CLIENT_FIELD_ID,
        }:
            continue
        for attachment in field.get("value") or []:
            if not isinstance(attachment, dict):
                continue
            title = str(attachment.get("title") or "")
            numbers.update(match.upper() for match in re.findall(r"GTFVR\d+", title, re.I))
    return numbers


def _invoice_is_canceled(*, invoice: dict[str, Any], fel_row: dict[str, Any]) -> bool:
    return (
        _truthy(invoice.get("cancelled"))
        or _truthy(fel_row.get("cancelled"))
        or _normalize(invoice.get("status")) in {"canceled", "cancelled"}
        or _normalize(fel_row.get("electronicDocumentStatus")) in {"canceled", "cancelled"}
    )


def _container_key(value: Any) -> str:
    return "".join(character for character in str(value or "").upper() if character.isalnum())


def _legacy_storage_entries(
    *,
    custom_fields: dict[str, dict[str, Any]],
    days: int,
    containers: int,
    settings: StorageInvoiceSettings,
) -> list[dict[str, Any]]:
    raw_value = None
    for name in (
        "Container(s) number(s)/",
        "Container Numbers",
        "Containers",
        "Container",
    ):
        field = custom_fields.get(name) or {}
        if field.get("value") not in {None, ""}:
            raw_value = field.get("value")
            break
    if raw_value is None:
        return []
    identifiers = [
        part.strip()
        for part in re.split(r"[,;\n]+", str(raw_value))
        if part.strip()
    ]
    if len(identifiers) != containers or len({_container_key(value) for value in identifiers}) != containers:
        return []
    amount = float(settings.daily_rate * Decimal(days))
    return [
        {
            "container": identifier,
            "days": days,
            "amount": amount,
            "containers": 1,
        }
        for identifier in identifiers
    ]


def _find_active_split_storage_invoices(
    *,
    bc_client: BusinessCentralClient,
    market: str,
    customer_number: str | None,
    entries: list[dict[str, Any]],
    item_number: str,
    reference_suffix: str,
) -> list[dict[str, Any]]:
    matches = []
    for entry in entries:
        child_reference = str(entry.get("custom_id") or entry.get("task_id") or "").strip()
        if not child_reference:
            continue
        invoice = _find_legacy_storage_invoice(
            bc_client=bc_client,
            market=market,
            base_reference=f"{child_reference}-{reference_suffix}",
            customer_number=customer_number,
            item_number=item_number,
            expected_total=Decimal(str(entry["amount"])),
        )
        if invoice:
            matches.append({**invoice, "container": entry.get("container")})
    return matches


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
        if _truthy(invoice.get("cancelled")) or _normalize(invoice.get("status")) in {
            "canceled",
            "cancelled",
        }:
            continue
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


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().casefold() in {"1", "true", "yes", "si", "sí"}


def _normalize(value: Any) -> str:
    return " ".join(str(value or "").strip().casefold().split())
