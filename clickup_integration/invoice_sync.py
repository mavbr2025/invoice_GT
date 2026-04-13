from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from business_central_client.client import BusinessCentralClient
from clickup_integration.customer_rules import field_value
from clickup_integration.mapping import resolve_dropdown_field
from clickup_integration.writeback import prepare_clickup_bc_invoice_writeback


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InvoiceAutomationSettings:
    ready_status: str
    ok_finops_status: str
    eta_horizon_days: int
    supported_market: str
    supported_currency: str
    eta_field_names: tuple[str, ...]
    currency_field_names: tuple[str, ...]
    reference_field_names: tuple[str, ...]
    invoice_date_field_names: tuple[str, ...]
    posting_date_field_names: tuple[str, ...]
    due_date_field_names: tuple[str, ...]
    freight_field_names: tuple[str, ...]
    inland_field_names: tuple[str, ...]
    destination_field_names: tuple[str, ...]
    bc_customer_id_field_names: tuple[str, ...]
    bc_customer_number_field_names: tuple[str, ...]
    bc_invoice_number_field_names: tuple[str, ...]
    bc_invoice_id_field_names: tuple[str, ...]
    freight_account_number: str | None
    inland_account_number: str | None
    destination_account_number: str | None

    @classmethod
    def from_env(cls) -> "InvoiceAutomationSettings":
        supported_market = os.getenv("CLICKUP_INVOICE_MARKET", "GT").strip().upper() or "GT"
        return cls(
            ready_status=os.getenv("CLICKUP_INVOICE_READY_STATUS", "Listo para facturar").strip()
            or "Listo para facturar",
            ok_finops_status=os.getenv("CLICKUP_INVOICE_OK_FINOPS_STATUS", "OK Finops").strip()
            or "OK Finops",
            eta_horizon_days=_env_int("CLICKUP_INVOICE_ETA_HORIZON_DAYS", default=10),
            supported_market=supported_market,
            supported_currency=os.getenv("CLICKUP_INVOICE_CURRENCY", "USD").strip().upper() or "USD",
            eta_field_names=_env_csv("CLICKUP_INVOICE_ETA_FIELD_NAMES", default=("ETA",)),
            currency_field_names=_env_csv(
                "CLICKUP_INVOICE_CURRENCY_FIELD_NAMES",
                default=("Invoice Currency", "Currency"),
            ),
            reference_field_names=_env_csv(
                "CLICKUP_INVOICE_REFERENCE_FIELD_NAMES",
                default=("Reference", "Customer Reference", "PO Number"),
            ),
            invoice_date_field_names=_env_csv(
                "CLICKUP_INVOICE_DATE_FIELD_NAMES",
                default=("Invoice Date",),
            ),
            posting_date_field_names=_env_csv(
                "CLICKUP_INVOICE_POSTING_DATE_FIELD_NAMES",
                default=("Posting Date",),
            ),
            due_date_field_names=_env_csv(
                "CLICKUP_INVOICE_DUE_DATE_FIELD_NAMES",
                default=("Due Date",),
            ),
            freight_field_names=_env_csv(
                "CLICKUP_INVOICE_FREIGHT_FIELD_NAMES",
                default=("Freight",),
            ),
            inland_field_names=_env_csv(
                "CLICKUP_INVOICE_INLAND_FIELD_NAMES",
                default=("Inland",),
            ),
            destination_field_names=_env_csv(
                "CLICKUP_INVOICE_DESTINATION_FIELD_NAMES",
                default=("Destination Charges", "Destination Charge"),
            ),
            bc_customer_id_field_names=_env_csv(
                "CLICKUP_INVOICE_BC_CUSTOMER_ID_FIELD_NAMES",
                default=("Business Central Customer ID",),
            ),
            bc_customer_number_field_names=_env_csv(
                "CLICKUP_INVOICE_BC_CUSTOMER_NUMBER_FIELD_NAMES",
                default=("Business Central Customer Number",),
            ),
            bc_invoice_number_field_names=_env_csv(
                "CLICKUP_INVOICE_BC_INVOICE_NUMBER_FIELD_NAMES",
                default=("Business Central Invoice Number",),
            ),
            bc_invoice_id_field_names=_env_csv(
                "CLICKUP_INVOICE_BC_INVOICE_ID_FIELD_NAMES",
                default=("Business Central Invoice ID",),
            ),
            freight_account_number=os.getenv(
                f"BC_MARKET_{supported_market}_FREIGHT_ACCOUNT_NUMBER",
                "",
            ).strip()
            or None,
            inland_account_number=os.getenv(
                f"BC_MARKET_{supported_market}_INLAND_ACCOUNT_NUMBER",
                "",
            ).strip()
            or None,
            destination_account_number=os.getenv(
                f"BC_MARKET_{supported_market}_DESTINATION_ACCOUNT_NUMBER",
                "",
            ).strip()
            or None,
        )


def prepare_clickup_invoice_status_transition(
    *,
    clickup_summary: dict[str, Any],
    settings: InvoiceAutomationSettings | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    config = settings or InvoiceAutomationSettings.from_env()
    as_of = today or date.today()
    task_status = clickup_summary.get("status")
    market = (clickup_summary.get("market") or "").strip().upper()
    if market != config.supported_market:
        return {
            "status": "ignored_market",
            "message": f"Invoice automation only runs for market {config.supported_market}.",
            "market": market or None,
            "task_status": task_status,
        }

    currency = _resolve_currency_code(clickup_summary.get("custom_fields") or {}, config)
    if currency != config.supported_currency:
        return {
            "status": "ignored_currency",
            "message": (
                f"Invoice automation only runs for currency {config.supported_currency}."
            ),
            "market": market,
            "currency": currency,
            "task_status": task_status,
        }

    if not _status_equals(task_status, config.ok_finops_status):
        return {
            "status": "ignored_status",
            "message": f"Task status is not {config.ok_finops_status}.",
            "market": market,
            "currency": currency,
            "task_status": task_status,
        }

    eta_date = _resolve_eta_date(clickup_summary, config)
    if eta_date is None:
        return {
            "status": "missing_eta",
            "message": "ETA is required before the task can move to invoicing readiness.",
            "market": market,
            "currency": currency,
            "task_status": task_status,
        }

    if eta_date > as_of + timedelta(days=config.eta_horizon_days):
        return {
            "status": "eta_outside_window",
            "message": (
                f"ETA is outside the {config.eta_horizon_days}-day invoicing window."
            ),
            "market": market,
            "currency": currency,
            "task_status": task_status,
            "eta_date": eta_date.isoformat(),
        }

    return {
        "status": "ready_to_update",
        "action": "set_ready_to_invoice",
        "market": market,
        "currency": currency,
        "task_status": task_status,
        "target_status": config.ready_status,
        "eta_date": eta_date.isoformat(),
    }


def prepare_clickup_bc_sales_invoice_preview(
    *,
    clickup_summary: dict[str, Any],
    bc_client: BusinessCentralClient,
    settings: InvoiceAutomationSettings | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    config = settings or InvoiceAutomationSettings.from_env()
    as_of = today or date.today()
    task_status = clickup_summary.get("status")
    custom_fields = clickup_summary.get("custom_fields") or {}
    market = (clickup_summary.get("market") or "").strip().upper()

    if market != config.supported_market:
        return {
            "status": "unsupported_market",
            "message": f"Invoice creation only supports market {config.supported_market}.",
            "market": market or None,
            "task_status": task_status,
        }

    currency = _resolve_currency_code(custom_fields, config)
    if currency != config.supported_currency:
        return {
            "status": "unsupported_currency",
            "message": f"Invoice creation only supports currency {config.supported_currency}.",
            "market": market,
            "currency": currency,
            "task_status": task_status,
        }

    if not _status_equals(task_status, config.ready_status):
        return {
            "status": "not_ready_to_invoice",
            "message": f"Task status must be {config.ready_status} before creating the invoice.",
            "market": market,
            "currency": currency,
            "task_status": task_status,
        }

    customer_id = _first_present_field(custom_fields, config.bc_customer_id_field_names)
    customer_number = _first_present_field(custom_fields, config.bc_customer_number_field_names)
    reference = _resolve_reference(clickup_summary, custom_fields, config)
    eta_date = _resolve_eta_date(clickup_summary, config)
    invoice_date = _resolve_date_from_fields(custom_fields, config.invoice_date_field_names) or as_of
    posting_date = _resolve_date_from_fields(custom_fields, config.posting_date_field_names) or invoice_date
    due_date = _resolve_date_from_fields(custom_fields, config.due_date_field_names) or eta_date

    missing_fields: list[str] = []
    if not customer_id and not customer_number:
        missing_fields.append("Business Central Customer ID or Business Central Customer Number")
    if not reference:
        missing_fields.append("Reference/custom_id/task_id")
    if due_date is None:
        missing_fields.append("Due Date or ETA")

    charge_inputs = [
        _build_charge_input(
            custom_fields=custom_fields,
            amount_field_names=config.freight_field_names,
            charge_name="freight",
            account_number=config.freight_account_number,
            description="Freight",
        ),
        _build_charge_input(
            custom_fields=custom_fields,
            amount_field_names=config.inland_field_names,
            charge_name="inland",
            account_number=config.inland_account_number,
            description="Inland",
        ),
        _build_charge_input(
            custom_fields=custom_fields,
            amount_field_names=config.destination_field_names,
            charge_name="destination_charges",
            account_number=config.destination_account_number,
            description="Destination charges",
        ),
    ]

    parse_errors = [charge["error"] for charge in charge_inputs if charge.get("error")]
    if parse_errors:
        return {
            "status": "invalid_charge_data",
            "message": "; ".join(parse_errors),
            "market": market,
            "currency": currency,
            "task_status": task_status,
        }

    active_charges = [charge for charge in charge_inputs if charge.get("amount") is not None and charge["amount"] > 0]
    if not active_charges:
        missing_fields.append("At least one non-zero charge line (freight, inland, or destination charges)")

    if missing_fields:
        return {
            "status": "missing_required_fields",
            "message": "Missing required invoice fields.",
            "missing_fields": missing_fields,
            "market": market,
            "currency": currency,
            "task_status": task_status,
        }

    duplicate_check = _find_existing_invoice(
        bc_client=bc_client,
        market=market,
        reference=reference,
        customer_number=customer_number or None,
    )
    if duplicate_check:
        return {
            "status": "duplicate_invoice",
            "message": "A Business Central sales invoice already exists for this reference.",
            "market": market,
            "currency": currency,
            "task_status": task_status,
            "reference": reference,
            "existing_invoice": duplicate_check,
        }

    line_payloads: list[dict[str, Any]] = []
    line_sources: list[dict[str, Any]] = []
    for charge in active_charges:
        account_number = charge.get("account_number")
        if not account_number:
            return {
                "status": "missing_account_mapping",
                "message": f"No BC account number is configured for {charge['charge_name']}.",
                "market": market,
                "currency": currency,
                "task_status": task_status,
            }

        account = bc_client.resolve_account_by_number(account_number, market=market)
        if not account:
            return {
                "status": "missing_bc_account",
                "message": (
                    f"BC account {account_number} for {charge['charge_name']} was not found in market {market}."
                ),
                "market": market,
                "currency": currency,
                "task_status": task_status,
            }

        amount = float(charge["amount"])
        line_payloads.append(
            {
                "lineType": "Account",
                "lineObjectNumber": account.get("number") or account_number,
                "accountId": account["id"],
                "description": charge["description"],
                "quantity": 1,
                "unitPrice": amount,
            }
        )
        line_sources.append(
            {
                "charge_name": charge["charge_name"],
                "amount": amount,
                "source_field": charge["source_field"],
                "account_number": account.get("number") or account_number,
                "description": charge["description"],
            }
        )

    header_payload = {
        "currencyCode": currency,
        "externalDocumentNumber": reference,
        "customerPurchaseOrderReference": reference,
        "invoiceDate": invoice_date.isoformat(),
        "postingDate": posting_date.isoformat(),
        "dueDate": due_date.isoformat(),
    }
    if customer_id:
        header_payload["customerId"] = customer_id
    if customer_number:
        header_payload["customerNumber"] = customer_number

    return {
        "status": "dry_run_ready",
        "market": market,
        "currency": currency,
        "task_status": task_status,
        "reference": reference,
        "customer_id": customer_id or None,
        "customer_number": customer_number or None,
        "eta_date": eta_date.isoformat() if eta_date else None,
        "proposed_bc_payload": header_payload,
        "proposed_bc_line_payloads": line_payloads,
        "line_sources": line_sources,
    }


def apply_clickup_bc_sales_invoice(
    *,
    clickup_summary: dict[str, Any],
    bc_client: BusinessCentralClient,
    settings: InvoiceAutomationSettings | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    config = settings or InvoiceAutomationSettings.from_env()
    preview = prepare_clickup_bc_sales_invoice_preview(
        clickup_summary=clickup_summary,
        bc_client=bc_client,
        settings=config,
        today=today,
    )
    if preview.get("status") != "dry_run_ready":
        logger.info(
            "Invoice creation skipped task_id=%s status=%s message=%s",
            clickup_summary.get("task_id"),
            preview.get("status"),
            preview.get("message"),
        )
        return preview

    try:
        created_invoice = bc_client.create_sales_invoice(
            preview["proposed_bc_payload"],
            market=preview["market"],
        )
    except Exception as exc:
        logger.exception(
            "BC sales invoice header creation failed task_id=%s reference=%s",
            clickup_summary.get("task_id"),
            preview.get("reference"),
        )
        return {
            **preview,
            "status": "failed",
            "message": str(exc),
        }

    created_lines: list[dict[str, Any]] = []
    try:
        for line_payload in preview["proposed_bc_line_payloads"]:
            created_lines.append(
                bc_client.create_sales_invoice_line(
                    created_invoice["id"],
                    line_payload,
                    market=preview["market"],
                )
            )
    except Exception as exc:
        logger.exception(
            "BC sales invoice line creation failed task_id=%s invoice_id=%s",
            clickup_summary.get("task_id"),
            created_invoice.get("id"),
        )
        return {
            **preview,
            "status": "failed_partial",
            "message": str(exc),
            "created_invoice": created_invoice,
            "created_lines": created_lines,
        }

    logger.info(
        "Created BC sales invoice task_id=%s reference=%s invoice_id=%s invoice_number=%s",
        clickup_summary.get("task_id"),
        preview.get("reference"),
        created_invoice.get("id"),
        created_invoice.get("number"),
    )
    invoice_writeback = prepare_clickup_bc_invoice_writeback(
        clickup_summary=clickup_summary,
        created_invoice=created_invoice,
        invoice_field_names={
            "invoice_number": config.bc_invoice_number_field_names[0],
            "invoice_id": config.bc_invoice_id_field_names[0],
        },
        require_all_fields=False,
    )
    return {
        **preview,
        "status": "applied",
        "created_invoice": created_invoice,
        "created_lines": created_lines,
        "invoice_writeback": invoice_writeback,
    }


def _build_charge_input(
    *,
    custom_fields: dict[str, dict[str, Any]],
    amount_field_names: tuple[str, ...],
    charge_name: str,
    account_number: str | None,
    description: str,
) -> dict[str, Any]:
    raw_value, source_field = _first_present_field_with_name(custom_fields, amount_field_names)
    if not raw_value:
        return {
            "charge_name": charge_name,
            "amount": None,
            "account_number": account_number,
            "description": description,
            "source_field": source_field,
        }

    amount = _parse_decimal(raw_value)
    if amount is None:
        return {
            "charge_name": charge_name,
            "amount": None,
            "account_number": account_number,
            "description": description,
            "source_field": source_field,
            "error": f"Charge field {source_field or charge_name} has an invalid numeric value.",
        }

    return {
        "charge_name": charge_name,
        "amount": amount,
        "account_number": account_number,
        "description": description,
        "source_field": source_field,
    }


def _find_existing_invoice(
    *,
    bc_client: BusinessCentralClient,
    market: str,
    reference: str,
    customer_number: str | None,
) -> dict[str, Any] | None:
    escaped_reference = reference.replace("'", "''")
    filters = [f"externalDocumentNumber eq '{escaped_reference}'"]
    if customer_number:
        escaped_customer_number = customer_number.replace("'", "''")
        filters.append(f"customerNumber eq '{escaped_customer_number}'")
    rows = bc_client.find_entities(
        "salesInvoices",
        filters=" and ".join(filters),
        top=5,
        market=market,
    )
    if not rows and customer_number is not None:
        rows = bc_client.find_entities(
            "salesInvoices",
            filters=f"externalDocumentNumber eq '{escaped_reference}'",
            top=5,
            market=market,
        )
    if not rows:
        return None
    return rows[0]


def _resolve_reference(
    clickup_summary: dict[str, Any],
    custom_fields: dict[str, dict[str, Any]],
    config: InvoiceAutomationSettings,
) -> str:
    explicit = _first_present_field(custom_fields, config.reference_field_names)
    if explicit:
        return explicit
    for fallback in (clickup_summary.get("custom_id"), clickup_summary.get("task_id")):
        if fallback is not None and str(fallback).strip():
            return str(fallback).strip()
    return ""


def _resolve_currency_code(
    custom_fields: dict[str, dict[str, Any]],
    config: InvoiceAutomationSettings,
) -> str:
    for field_name in config.currency_field_names:
        field = custom_fields.get(field_name)
        if not field:
            continue
        label = ((resolve_dropdown_field(field) or {}).get("name") or "").strip()
        if label:
            return label.upper()
        raw = field_value(custom_fields, field_name=field_name)
        if raw:
            return raw.upper()
    return ""


def _resolve_eta_date(
    clickup_summary: dict[str, Any],
    config: InvoiceAutomationSettings,
) -> date | None:
    custom_fields = clickup_summary.get("custom_fields") or {}
    eta = _resolve_date_from_fields(custom_fields, config.eta_field_names)
    if eta is not None:
        return eta
    return _parse_date(clickup_summary.get("due_date"))


def _resolve_date_from_fields(
    custom_fields: dict[str, dict[str, Any]],
    field_names: tuple[str, ...],
) -> date | None:
    for field_name in field_names:
        field = custom_fields.get(field_name) or {}
        value = field.get("value")
        parsed = _parse_date(value)
        if parsed is not None:
            return parsed
    return None


def _first_present_field(custom_fields: dict[str, dict[str, Any]], field_names: tuple[str, ...]) -> str:
    for field_name in field_names:
        value = field_value(custom_fields, field_name=field_name)
        if value:
            return value
    return ""


def _first_present_field_with_name(
    custom_fields: dict[str, dict[str, Any]],
    field_names: tuple[str, ...],
) -> tuple[str, str | None]:
    for field_name in field_names:
        value = field_value(custom_fields, field_name=field_name)
        if value:
            return value, field_name
    return "", None


def _status_equals(left: str | None, right: str | None) -> bool:
    return _normalize_status(left) == _normalize_status(right)


def _normalize_status(value: str | None) -> str:
    return " ".join((value or "").strip().lower().split())


def _parse_date(value: Any) -> date | None:
    if value in {None, ""}:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, (int, float)):
        timestamp = float(value)
        if timestamp > 1_000_000_000_000:
            timestamp /= 1000.0
        return datetime.fromtimestamp(timestamp, tz=UTC).date()

    raw = str(value).strip()
    if not raw:
        return None
    if raw.isdigit():
        timestamp = int(raw)
        if timestamp > 1_000_000_000_000:
            timestamp /= 1000
        return datetime.fromtimestamp(timestamp, tz=UTC).date()
    for parser in (date.fromisoformat,):
        try:
            return parser(raw)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _parse_decimal(value: Any) -> Decimal | None:
    cleaned = str(value).strip()
    if not cleaned:
        return None
    normalized = cleaned.replace(",", "")
    try:
        return Decimal(normalized)
    except InvalidOperation:
        return None


def _env_csv(name: str, *, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.getenv(name, "")
    values = tuple(value.strip() for value in raw.split(",") if value.strip())
    return values or default


def _env_int(name: str, *, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default
