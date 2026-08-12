from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from business_central_client.client import BusinessCentralClient
from clickup_integration.invoice_sync import InvoiceAutomationSettings
from clickup_integration.storage_invoice_sync import (
    DEFAULT_CONTAINER_COUNT_FIELD_ID,
    StorageInvoiceSettings,
    build_clickup_storage_invoice_context,
    issue_clickup_bc_storage_invoice,
    prepare_clickup_bc_storage_invoice_preview,
)


DEFAULT_DEMURRAGE_AMOUNT_FIELD_ID = "e0dce9a5-00f2-4aa1-b563-b997c29136bc"
DEFAULT_DEMURRAGE_DAYS_FIELD_ID = "d5620363-46c1-433f-b6a1-5643d67dc74f"
DEFAULT_DEMURRAGE_CUT_FIELD_ID = "7cd14623-4ac1-4c03-bcea-50782047f2d6"
DEFAULT_DEMURRAGE_INVOICED_FIELD_ID = "9022ecdb-ff0d-44e2-8e30-d16efd5a89fa"
DEFAULT_DEMURRAGE_ATTACHMENT_FIELD_ID = "323c1843-401d-4ba5-92a1-f6fdc8187da0"
DEFAULT_DEMURRAGE_ITEM_NUMBER = "NAT00000033"


@dataclass(frozen=True)
class DemurrageInvoiceSettings:
    required_invoice_status: str = "Facturada"
    amount_field_id: str = DEFAULT_DEMURRAGE_AMOUNT_FIELD_ID
    amount_field_name: str = "D&D al cliente (USD)"
    days_field_id: str = DEFAULT_DEMURRAGE_DAYS_FIELD_ID
    days_field_name: str = "Días de D&D"
    container_count_field_id: str = DEFAULT_CONTAINER_COUNT_FIELD_ID
    container_count_field_name: str = "Number of Containers"
    cut_field_id: str = DEFAULT_DEMURRAGE_CUT_FIELD_ID
    cut_field_name: str = "Corte de D&D"
    invoiced_field_id: str = DEFAULT_DEMURRAGE_INVOICED_FIELD_ID
    invoice_attachment_field_id: str = DEFAULT_DEMURRAGE_ATTACHMENT_FIELD_ID
    item_number: str = DEFAULT_DEMURRAGE_ITEM_NUMBER
    item_description: str = "DEMORA"
    reference_suffix: str = "DEM"

    @classmethod
    def from_env(cls) -> "DemurrageInvoiceSettings":
        return cls(
            required_invoice_status=_env(
                "CLICKUP_DEMURRAGE_INVOICE_REQUIRED_STATUS", "Facturada"
            ),
            amount_field_id=_env(
                "CLICKUP_DEMURRAGE_AMOUNT_FIELD_ID", DEFAULT_DEMURRAGE_AMOUNT_FIELD_ID
            ),
            amount_field_name=_env(
                "CLICKUP_DEMURRAGE_AMOUNT_FIELD_NAME", "D&D al cliente (USD)"
            ),
            days_field_id=_env(
                "CLICKUP_DEMURRAGE_DAYS_FIELD_ID", DEFAULT_DEMURRAGE_DAYS_FIELD_ID
            ),
            days_field_name=_env("CLICKUP_DEMURRAGE_DAYS_FIELD_NAME", "Días de D&D"),
            container_count_field_id=_env(
                "CLICKUP_DEMURRAGE_CONTAINER_COUNT_FIELD_ID",
                DEFAULT_CONTAINER_COUNT_FIELD_ID,
            ),
            container_count_field_name=_env(
                "CLICKUP_DEMURRAGE_CONTAINER_COUNT_FIELD_NAME", "Number of Containers"
            ),
            cut_field_id=_env(
                "CLICKUP_DEMURRAGE_CUT_FIELD_ID", DEFAULT_DEMURRAGE_CUT_FIELD_ID
            ),
            cut_field_name=_env("CLICKUP_DEMURRAGE_CUT_FIELD_NAME", "Corte de D&D"),
            invoiced_field_id=_env(
                "CLICKUP_DEMURRAGE_INVOICED_FIELD_ID",
                DEFAULT_DEMURRAGE_INVOICED_FIELD_ID,
            ),
            invoice_attachment_field_id=_env(
                "CLICKUP_DEMURRAGE_INVOICE_ATTACHMENT_FIELD_ID",
                DEFAULT_DEMURRAGE_ATTACHMENT_FIELD_ID,
            ),
            item_number=_env(
                "CLICKUP_DEMURRAGE_BC_ITEM_NUMBER", DEFAULT_DEMURRAGE_ITEM_NUMBER
            ),
            item_description=_env("CLICKUP_DEMURRAGE_BC_ITEM_DESCRIPTION", "DEMORA"),
            reference_suffix=_env("CLICKUP_DEMURRAGE_REFERENCE_SUFFIX", "DEM"),
        )

    def as_storage_settings(self, *, daily_rate: Decimal = Decimal("1")) -> StorageInvoiceSettings:
        return StorageInvoiceSettings(
            required_invoice_status=self.required_invoice_status,
            amount_field_id=self.amount_field_id,
            amount_field_name=self.amount_field_name,
            days_field_id=self.days_field_id,
            days_field_name=self.days_field_name,
            container_count_field_id=self.container_count_field_id,
            container_count_field_name=self.container_count_field_name,
            cut_field_id=self.cut_field_id,
            invoiced_field_id=self.invoiced_field_id,
            item_number=self.item_number,
            item_description=self.item_description,
            daily_rate=daily_rate,
            reference_suffix=self.reference_suffix,
            invoice_group="DEM",
            charge_label="Demurrage & Detention",
            invoice_attachment_field_id=self.invoice_attachment_field_id,
            allow_attached_history_customer_mismatch=True,
        )


def build_clickup_demurrage_invoice_context(
    *,
    requested_task: dict[str, Any],
    invoice_task: dict[str, Any],
    demurrage_settings: DemurrageInvoiceSettings | None = None,
) -> dict[str, Any]:
    config = demurrage_settings or DemurrageInvoiceSettings.from_env()
    summary = build_clickup_storage_invoice_context(
        requested_task=requested_task,
        invoice_task=invoice_task,
        storage_settings=config.as_storage_settings(),
    )
    return {
        **summary,
        "demurrage_context_mode": summary.get("storage_context_mode"),
        "invoice_type": "DEM",
    }


def prepare_clickup_bc_demurrage_invoice_preview(
    *,
    clickup_summary: dict[str, Any],
    bc_client: BusinessCentralClient,
    invoice_settings: InvoiceAutomationSettings | None = None,
    demurrage_settings: DemurrageInvoiceSettings | None = None,
) -> dict[str, Any]:
    config = demurrage_settings or DemurrageInvoiceSettings.from_env()
    derived = _derive_daily_rate(clickup_summary=clickup_summary, settings=config)
    if derived.get("status") != "passed":
        return derived
    result = prepare_clickup_bc_storage_invoice_preview(
        clickup_summary=clickup_summary,
        bc_client=bc_client,
        invoice_settings=invoice_settings,
        storage_settings=config.as_storage_settings(
            daily_rate=Decimal(str(derived["daily_rate"]))
        ),
    )
    return _label_demurrage_result(result, derived_rate=derived)


def issue_clickup_bc_demurrage_invoice(
    *,
    clickup_summary: dict[str, Any],
    bc_client: BusinessCentralClient,
    invoice_settings: InvoiceAutomationSettings | None = None,
    demurrage_settings: DemurrageInvoiceSettings | None = None,
) -> dict[str, Any]:
    config = demurrage_settings or DemurrageInvoiceSettings.from_env()
    derived = _derive_daily_rate(clickup_summary=clickup_summary, settings=config)
    if derived.get("status") != "passed":
        return derived
    result = issue_clickup_bc_storage_invoice(
        clickup_summary=clickup_summary,
        bc_client=bc_client,
        invoice_settings=invoice_settings,
        storage_settings=config.as_storage_settings(
            daily_rate=Decimal(str(derived["daily_rate"]))
        ),
    )
    return _label_demurrage_result(result, derived_rate=derived)


def _derive_daily_rate(
    *,
    clickup_summary: dict[str, Any],
    settings: DemurrageInvoiceSettings,
) -> dict[str, Any]:
    entries = clickup_summary.get("storage_entries") or []
    rates: list[Decimal] = []
    if entries:
        for entry in entries:
            amount = _decimal(entry.get("amount"))
            days = _positive_integer(entry.get("days"))
            if amount is None or amount <= 0 or days is None:
                return {
                    "status": "missing_demurrage_data",
                    "message": "A D&D amount and positive D&D days are required for each container.",
                }
            rates.append(amount / Decimal(days))
    else:
        fields = clickup_summary.get("custom_fields") or {}
        cut = _field_value(fields, settings.cut_field_id, settings.cut_field_name)
        if not _truthy(cut):
            return {
                "status": "demurrage_cut_not_ready",
                "message": "Corte de D&D must be checked before DEM invoicing.",
            }
        amount = _decimal(_field_value(fields, settings.amount_field_id, settings.amount_field_name))
        days = _positive_integer(_field_value(fields, settings.days_field_id, settings.days_field_name))
        containers = _positive_integer(
            _field_value(
                fields,
                settings.container_count_field_id,
                settings.container_count_field_name,
            )
        )
        if amount is None or amount <= 0 or days is None or containers is None:
            return {
                "status": "missing_demurrage_data",
                "message": "D&D amount, D&D days, and container count are required.",
            }
        rates.append(amount / (Decimal(days) * Decimal(containers)))

    first = rates[0]
    if any(abs(rate - first) >= Decimal("0.00001") for rate in rates[1:]):
        return {
            "status": "ambiguous_demurrage_rate",
            "message": "The D&D entries use different daily rates and require separate invoices.",
            "daily_rates": [float(rate) for rate in rates],
        }
    if first <= 0:
        return {"status": "invalid_demurrage_rate", "message": "The derived D&D rate must be positive."}
    return {
        "status": "passed",
        "rate_source": "clickup_amount_divided_by_container_days",
        "daily_rate": float(first),
    }


def _field_value(fields: dict[str, Any], field_id: str, field_name: str) -> Any:
    for name, field in fields.items():
        if str(field.get("id") or "") == field_id or name == field_name:
            return field.get("value")
    return None


def _decimal(value: Any) -> Decimal | None:
    if value in {None, ""}:
        return None
    try:
        return Decimal(str(value).replace(",", ""))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _positive_integer(value: Any) -> int | None:
    parsed = _decimal(value)
    if parsed is None or parsed <= 0 or parsed != parsed.to_integral_value():
        return None
    return int(parsed)


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "si", "sí", "checked"}


def _label_demurrage_result(
    result: dict[str, Any],
    *,
    derived_rate: dict[str, Any],
) -> dict[str, Any]:
    labeled = _replace_messages(result)
    validation = labeled.get("storage_validation")
    return {
        **labeled,
        "invoice_type": "DEM",
        "derived_rate": derived_rate,
        "demurrage_validation": validation,
    }


def _replace_messages(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _replace_messages(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_messages(item) for item in value]
    if isinstance(value, str):
        return value.replace("Almacenaje", "Demurrage & Detention").replace(
            "storage invoice", "D&D invoice"
        )
    return value


def _env(name: str, default: str) -> str:
    return os.getenv(name, default).strip() or default
