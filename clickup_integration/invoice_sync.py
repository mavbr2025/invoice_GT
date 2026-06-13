from __future__ import annotations

import logging
import os
import json
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from business_central_client.client import BusinessCentralClient
from clickup_integration.customer_rules import field_value
from clickup_integration.mapping import resolve_dropdown_field
from clickup_integration.writeback import prepare_clickup_bc_invoice_writeback


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InvoiceChargeMapping:
    charge_name: str
    clickup_field_name: str
    clickup_field_id: str
    bc_item_number: str
    bc_description: str
    tax_group: str | None = None


@dataclass(frozen=True)
class InvoiceAutomationSettings:
    ready_status: str
    ok_finops_status: str
    eta_horizon_days: int
    supported_market: str
    supported_currency: str
    invoice_status_field_names: tuple[str, ...]
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
    charge_mappings: tuple[InvoiceChargeMapping, ...] = ()
    eta_field_ids: tuple[str, ...] = ()
    bc_customer_name_field_names: tuple[str, ...] = ()
    bc_customer_name_field_ids: tuple[str, ...] = ()
    shipment_booking_field_names: tuple[str, ...] = ("Booking number/", "Booking Number", "Booking")
    shipment_container_field_names: tuple[str, ...] = (
        "Container(s) number(s)/",
        "Container Numbers",
        "Containers",
        "Container",
    )

    @classmethod
    def from_env(cls) -> "InvoiceAutomationSettings":
        supported_market = os.getenv("CLICKUP_INVOICE_MARKET", "GT").strip().upper() or "GT"
        charge_mapping_path = _env_invoice_charge_mapping_path(supported_market)
        return cls(
            ready_status=os.getenv("CLICKUP_INVOICE_READY_STATUS", "Listo para facturar").strip()
            or "Listo para facturar",
            ok_finops_status=os.getenv("CLICKUP_INVOICE_OK_FINOPS_STATUS", "OK Finops").strip()
            or "OK Finops",
            eta_horizon_days=_env_int("CLICKUP_INVOICE_ETA_HORIZON_DAYS", default=10),
            supported_market=supported_market,
            supported_currency=os.getenv("CLICKUP_INVOICE_CURRENCY", "USD").strip().upper() or "USD",
            invoice_status_field_names=_env_csv(
                "CLICKUP_INVOICE_STATUS_FIELD_NAMES",
                default=(
                    "Estatus de facturación (USD)/",
                    "Estatus de Facturacion (USD)",
                    "Estatus de Facturacion",
                    "Invoice Status",
                ),
            ),
            eta_field_names=_env_csv("CLICKUP_INVOICE_ETA_FIELD_NAMES", default=("ETA",)),
            eta_field_ids=_env_csv(
                "CLICKUP_INVOICE_ETA_FIELD_IDS",
                default=("736ddd1d-33da-4ff8-a128-f7f3f738987d",),
            ),
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
            bc_customer_name_field_names=_env_csv(
                "CLICKUP_INVOICE_CUSTOMER_NAME_FIELD_NAMES",
                default=("Invoice to (Consignee's name)",),
            ),
            bc_customer_name_field_ids=_env_csv(
                "CLICKUP_INVOICE_CUSTOMER_NAME_FIELD_IDS",
                default=("729c2b40-6a61-4908-b0ed-3d6f92e72bcd",),
            ),
            bc_invoice_number_field_names=_env_csv(
                "CLICKUP_INVOICE_BC_INVOICE_NUMBER_FIELD_NAMES",
                default=("Business Central Invoice Number",),
            ),
            bc_invoice_id_field_names=_env_csv(
                "CLICKUP_INVOICE_BC_INVOICE_ID_FIELD_NAMES",
                default=("Business Central Invoice ID",),
            ),
            shipment_booking_field_names=_env_csv(
                "CLICKUP_INVOICE_SHIPMENT_BOOKING_FIELD_NAMES",
                default=("Booking number/", "Booking Number", "Booking"),
            ),
            shipment_container_field_names=_env_csv(
                "CLICKUP_INVOICE_SHIPMENT_CONTAINER_FIELD_NAMES",
                default=("Container(s) number(s)/", "Container Numbers", "Containers", "Container"),
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
            charge_mappings=load_invoice_charge_mappings(charge_mapping_path)
            if charge_mapping_path
            else (),
        )


def prepare_clickup_invoice_status_transition(
    *,
    clickup_summary: dict[str, Any],
    settings: InvoiceAutomationSettings | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    config = settings or InvoiceAutomationSettings.from_env()
    as_of = today or date.today()
    custom_fields = clickup_summary.get("custom_fields") or {}
    invoice_status = _resolve_invoice_status(custom_fields, config, fallback=clickup_summary.get("status"))
    task_status = invoice_status["status"]
    market = (clickup_summary.get("market") or "").strip().upper()
    if market != config.supported_market:
        return {
            "status": "ignored_market",
            "message": f"Invoice automation only runs for market {config.supported_market}.",
            "market": market or None,
            "task_status": task_status,
        }

    currency = _resolve_currency_code(custom_fields, config)
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

    if _status_equals(task_status, config.ready_status):
        return {
            "status": "already_ready_to_invoice",
            "message": f"Invoice status is already {config.ready_status}.",
            "market": market,
            "currency": currency,
            "task_status": task_status,
            "status_source": invoice_status["source"],
        }

    if not _status_equals(task_status, config.ok_finops_status):
        return {
            "status": "ignored_status",
            "message": f"Task status is not {config.ok_finops_status}.",
            "market": market,
            "currency": currency,
            "task_status": task_status,
            "status_source": invoice_status["source"],
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
        "status_source": invoice_status["source"],
        "target_status": config.ready_status,
        "status_field_id": invoice_status.get("field_id"),
        "target_status_option_id": invoice_status.get("ready_option_id"),
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
    custom_fields = clickup_summary.get("custom_fields") or {}
    invoice_status = _resolve_invoice_status(custom_fields, config, fallback=clickup_summary.get("status"))
    task_status = invoice_status["status"]
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
            "status_source": invoice_status["source"],
        }

    if not _status_equals(task_status, config.ready_status):
        return {
            "status": "not_ready_to_invoice",
            "message": f"Task status must be {config.ready_status} before creating the invoice.",
            "market": market,
            "currency": currency,
            "task_status": task_status,
            "status_source": invoice_status["source"],
        }

    customer_id = _first_present_field(custom_fields, config.bc_customer_id_field_names)
    customer_number = _first_present_field(custom_fields, config.bc_customer_number_field_names)
    customer_resolution = _resolve_invoice_customer(
        custom_fields=custom_fields,
        bc_client=bc_client,
        market=market,
        config=config,
        customer_id=customer_id,
        customer_number=customer_number,
    )
    if customer_resolution["status"] == "ambiguous":
        return {
            "status": "ambiguous_customer",
            "message": customer_resolution["message"],
            "market": market,
            "currency": currency,
            "task_status": task_status,
            "customer_resolution": customer_resolution,
        }
    if customer_resolution["customer_id"]:
        customer_id = customer_resolution["customer_id"]
    if customer_resolution["customer_number"]:
        customer_number = customer_resolution["customer_number"]

    reference = _resolve_reference(clickup_summary, custom_fields, config)
    shipment_metadata = _resolve_shipment_metadata(clickup_summary, custom_fields, config)
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

    if config.charge_mappings:
        charge_inputs = [
            _build_mapped_charge_input(custom_fields=custom_fields, mapping=mapping)
            for mapping in config.charge_mappings
        ]
        missing_charge_label = "At least one non-zero mapped charge line"
    else:
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
        missing_charge_label = "At least one non-zero charge line (freight, inland, or destination charges)"

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
        missing_fields.append(missing_charge_label)

    if missing_fields:
        return {
            "status": "missing_required_fields",
            "message": "Missing required invoice fields.",
            "missing_fields": missing_fields,
            "market": market,
            "currency": currency,
            "task_status": task_status,
        }

    line_payloads: list[dict[str, Any]] = []
    line_sources: list[dict[str, Any]] = []
    for charge in active_charges:
        item_number = charge.get("item_number")
        if item_number:
            item = bc_client.resolve_item_by_number(item_number, market=market)
            if not item:
                return {
                    "status": "missing_bc_item",
                    "message": (
                        f"BC item {item_number} for {charge['charge_name']} was not found in market {market}."
                    ),
                    "market": market,
                    "currency": currency,
                    "task_status": task_status,
                }

            amount = float(charge["amount"])
            line_payloads.append(
                {
                    "lineType": "Item",
                    "lineObjectNumber": item.get("number") or item_number,
                    "itemId": item["id"],
                    "description": charge["description"],
                    "quantity": 1,
                    "unitPrice": amount,
                }
            )
            line_sources.append(
                {
                    "charge_name": charge["charge_name"],
                    "invoice_group": _invoice_group_from_item_number(item.get("number") or item_number),
                    "amount": amount,
                    "source_field": charge["source_field"],
                    "source_field_id": charge.get("source_field_id"),
                    "item_number": item.get("number") or item_number,
                    "description": charge["description"],
                    "tax_group": charge.get("tax_group"),
                }
            )
            continue

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
                "invoice_group": "ACCOUNT",
                "amount": amount,
                "source_field": charge["source_field"],
                "account_number": account.get("number") or account_number,
                "description": charge["description"],
            }
        )

    header_payload = {
        "currencyCode": currency,
        "externalDocumentNumber": reference,
        "customerPurchaseOrderReference": shipment_metadata["shipment_number"] or reference,
        "invoiceDate": invoice_date.isoformat(),
        "postingDate": posting_date.isoformat(),
        "dueDate": due_date.isoformat(),
    }
    if customer_id:
        header_payload["customerId"] = customer_id
    if customer_number:
        header_payload["customerNumber"] = customer_number

    proposed_invoices = _build_proposed_invoice_groups(
        header_payload=header_payload,
        line_payloads=line_payloads,
        line_sources=line_sources,
        split_by_item_prefix=bool(config.charge_mappings),
        shipment_metadata=shipment_metadata,
    )
    for proposed_invoice in proposed_invoices:
        duplicate_check = _find_existing_invoice(
            bc_client=bc_client,
            market=market,
            reference=proposed_invoice["proposed_bc_payload"]["externalDocumentNumber"],
            customer_number=customer_number or None,
        )
        if duplicate_check:
            return {
                "status": "duplicate_invoice",
                "message": "A Business Central sales invoice already exists for this invoice group reference.",
                "market": market,
                "currency": currency,
                "task_status": task_status,
                "reference": proposed_invoice["proposed_bc_payload"]["externalDocumentNumber"],
                "invoice_group": proposed_invoice["invoice_group"],
                "existing_invoice": duplicate_check,
            }

    return {
        "status": "dry_run_ready",
        "market": market,
        "currency": currency,
        "task_status": task_status,
        "status_source": invoice_status["source"],
        "reference": reference,
        "invoice_count": len(proposed_invoices),
        "invoice_groups": [invoice["invoice_group"] for invoice in proposed_invoices],
        "customer_id": customer_id or None,
        "customer_number": customer_number or None,
        "customer_resolution": customer_resolution,
        "shipment_metadata": shipment_metadata,
        "eta_date": eta_date.isoformat() if eta_date else None,
        "proposed_bc_payload": proposed_invoices[0]["proposed_bc_payload"],
        "proposed_bc_line_payloads": line_payloads,
        "line_sources": line_sources,
        "proposed_bc_invoices": proposed_invoices,
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

    proposed_invoices = preview.get("proposed_bc_invoices") or [
        {
            "invoice_group": "ALL",
            "proposed_bc_payload": preview["proposed_bc_payload"],
            "proposed_bc_line_payloads": preview["proposed_bc_line_payloads"],
        }
    ]
    created_invoices: list[dict[str, Any]] = []
    created_lines: list[dict[str, Any]] = []
    for proposed_invoice in proposed_invoices:
        try:
            created_invoice = bc_client.create_sales_invoice(
                proposed_invoice["proposed_bc_payload"],
                market=preview["market"],
            )
        except Exception as exc:
            logger.exception(
                "BC sales invoice header creation failed task_id=%s reference=%s invoice_group=%s",
                clickup_summary.get("task_id"),
                proposed_invoice["proposed_bc_payload"].get("externalDocumentNumber"),
                proposed_invoice.get("invoice_group"),
            )
            return {
                **preview,
                "status": "failed",
                "message": str(exc),
                "created_invoices": created_invoices,
                "created_lines": created_lines,
            }

        created_invoices.append(
            {
                "invoice_group": proposed_invoice.get("invoice_group"),
                **created_invoice,
            }
        )
        try:
            for line_payload in proposed_invoice["proposed_bc_line_payloads"]:
                created_line = bc_client.create_sales_invoice_line(
                    created_invoice["id"],
                    line_payload,
                    market=preview["market"],
                )
                created_lines.append(
                    {
                        "invoice_group": proposed_invoice.get("invoice_group"),
                        "invoice_id": created_invoice.get("id"),
                        **created_line,
                    }
                )
        except Exception as exc:
            logger.exception(
                "BC sales invoice line creation failed task_id=%s invoice_id=%s invoice_group=%s",
                clickup_summary.get("task_id"),
                created_invoice.get("id"),
                proposed_invoice.get("invoice_group"),
            )
            return {
                **preview,
                "status": "failed_partial",
                "message": str(exc),
                "created_invoice": created_invoices[0] if created_invoices else None,
                "created_invoices": created_invoices,
                "created_lines": created_lines,
            }

        logger.info(
            "Created BC sales invoice task_id=%s reference=%s invoice_group=%s invoice_id=%s invoice_number=%s",
            clickup_summary.get("task_id"),
            proposed_invoice["proposed_bc_payload"].get("externalDocumentNumber"),
            proposed_invoice.get("invoice_group"),
            created_invoice.get("id"),
            created_invoice.get("number"),
        )

    writeback_invoice = _combined_created_invoice_for_writeback(created_invoices)
    invoice_writeback = prepare_clickup_bc_invoice_writeback(
        clickup_summary=clickup_summary,
        created_invoice=writeback_invoice,
        invoice_field_names={
            "invoice_number": config.bc_invoice_number_field_names[0],
            "invoice_id": config.bc_invoice_id_field_names[0],
        },
        require_all_fields=False,
    )
    return {
        **preview,
        "status": "applied",
        "created_invoice": writeback_invoice,
        "created_invoices": created_invoices,
        "created_lines": created_lines,
        "invoice_writeback": invoice_writeback,
    }


def issue_clickup_bc_sales_invoice(
    *,
    clickup_summary: dict[str, Any],
    bc_client: BusinessCentralClient,
    settings: InvoiceAutomationSettings | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    result = apply_clickup_bc_sales_invoice(
        clickup_summary=clickup_summary,
        bc_client=bc_client,
        settings=settings,
        today=today,
    )
    completed_stages: list[str] = []
    if result.get("status") != "applied":
        return {**result, "completed_stages": completed_stages, "failed_stage": "create_sales_invoice"}

    config = settings or InvoiceAutomationSettings.from_env()
    market = result["market"]
    completed_stages.append("create_sales_invoice")
    posted_invoices: list[dict[str, Any]] = []
    finalized_invoices: list[dict[str, Any]] = []
    current_stage = "post_sales_invoice"

    try:
        for created_invoice in result.get("created_invoices") or []:
            invoice_group = created_invoice.get("invoice_group")
            invoice_id = str(created_invoice.get("id") or "").strip()
            if not invoice_id:
                raise ValueError("Created invoice is missing its Business Central id.")

            post_response = bc_client.post_sales_invoice(invoice_id, market=market)
            posted_invoice = _resolve_posted_sales_invoice_after_post(
                bc_client=bc_client,
                created_invoice=created_invoice,
                market=market,
            )
            posted_invoices.append(
                {
                    **posted_invoice,
                    "invoice_group": invoice_group,
                    "post_response": post_response,
                }
            )

        completed_stages.append("post_sales_invoice")

        for posted_invoice in posted_invoices:
            current_stage = "sync_fel_descriptions"
            invoice_number = str(posted_invoice.get("number") or "").strip()
            if not invoice_number:
                raise ValueError("Posted invoice is missing its Business Central number.")

            fel_row = _wait_for_posted_invoice_fel_row(
                bc_client=bc_client,
                invoice_number=invoice_number,
                market=market,
            )
            sync_response = bc_client.sync_posted_invoice_fel_line_descriptions(
                fel_row["id"],
                market=market,
            )
            fel_row_after_sync = (
                bc_client.get_posted_invoice_fel_description_by_number(invoice_number, market=market)
                or fel_row
            )
            if "sync_fel_descriptions" not in completed_stages:
                completed_stages.append("sync_fel_descriptions")
            current_stage = "stamp_fel_invoice"
            stamp_response = bc_client.stamp_posted_invoice_fel(fel_row["id"], market=market)
            fel_row_after_stamp = _wait_for_stamp_received(
                bc_client=bc_client,
                invoice_number=invoice_number,
                market=market,
            )
            posted_invoice_after_stamp = (
                bc_client.get_entity("salesInvoices", posted_invoice["id"], market=market)
                or posted_invoice
            )
            gt_registered_invoice = bc_client.get_gt_registered_invoice_by_number(
                invoice_number,
                market=market,
            )
            finalized_invoices.append(
                {
                    "invoice_group": posted_invoice.get("invoice_group"),
                    "number": invoice_number,
                    "externalDocumentNumber": posted_invoice.get("externalDocumentNumber"),
                    "posted_invoice_after_stamp": posted_invoice_after_stamp,
                    "custom_api_row_after_sync": fel_row_after_sync,
                    "custom_api_row_after_stamp": fel_row_after_stamp,
                    "gt_registered_invoice_after_stamp": gt_registered_invoice,
                    "sync_descriptions_response": sync_response,
                    "stamp_response": stamp_response,
                }
            )
            if "stamp_fel_invoice" not in completed_stages:
                completed_stages.append("stamp_fel_invoice")
    except Exception as exc:
        logger.exception(
            "BC invoice post/FEL issue failed task_id=%s stage=%s",
            clickup_summary.get("task_id"),
            current_stage,
        )
        return {
            **result,
            "status": "failed_post_creation",
            "message": str(exc),
            "completed_stages": completed_stages,
            "failed_stage": current_stage,
            "posted_invoices": posted_invoices,
            "finalized_invoices": finalized_invoices,
        }

    writeback_invoice = _combined_created_invoice_for_writeback(
        [
            {
                "invoice_group": invoice.get("invoice_group"),
                **(invoice.get("posted_invoice_after_stamp") or {}),
            }
            for invoice in finalized_invoices
        ]
    )
    invoice_writeback = prepare_clickup_bc_invoice_writeback(
        clickup_summary=clickup_summary,
        created_invoice=writeback_invoice,
        invoice_field_names={
            "invoice_number": config.bc_invoice_number_field_names[0],
            "invoice_id": config.bc_invoice_id_field_names[0],
        },
        require_all_fields=False,
    )
    return {
        **result,
        "status": "applied",
        "created_invoice": writeback_invoice,
        "invoice_writeback": invoice_writeback,
        "completed_stages": completed_stages,
        "posted_invoices": posted_invoices,
        "finalized_invoices": finalized_invoices,
    }


def _resolve_posted_sales_invoice_after_post(
    *,
    bc_client: BusinessCentralClient,
    created_invoice: dict[str, Any],
    market: str,
) -> dict[str, Any]:
    invoice_id = str(created_invoice.get("id") or "").strip()
    external_document_number = str(created_invoice.get("externalDocumentNumber") or "").strip()
    for _attempt in range(3):
        posted_invoice = bc_client.get_entity("salesInvoices", invoice_id, market=market)
        if posted_invoice and _looks_posted_invoice_number(posted_invoice.get("number")):
            return posted_invoice
        if external_document_number:
            posted_invoice = bc_client.get_posted_sales_invoice_by_external_document_number(
                external_document_number,
                market=market,
            )
            if posted_invoice and _looks_posted_invoice_number(posted_invoice.get("number")):
                return posted_invoice
        time.sleep(2)
    raise ValueError(
        f"Business Central did not return a posted sales invoice after posting draft {created_invoice.get('number')}."
    )


def _wait_for_posted_invoice_fel_row(
    *,
    bc_client: BusinessCentralClient,
    invoice_number: str,
    market: str,
) -> dict[str, Any]:
    for _attempt in range(5):
        row = bc_client.get_posted_invoice_fel_description_by_number(invoice_number, market=market)
        if row:
            return row
        time.sleep(2)
    raise ValueError(f"Business Central FEL API row was not available for posted invoice {invoice_number}.")


def _wait_for_stamp_received(
    *,
    bc_client: BusinessCentralClient,
    invoice_number: str,
    market: str,
) -> dict[str, Any]:
    last_row: dict[str, Any] | None = None
    for _attempt in range(6):
        row = bc_client.get_posted_invoice_fel_description_by_number(invoice_number, market=market)
        if row:
            last_row = row
            if _is_stamp_received(row):
                return row
        time.sleep(2)
    status = (last_row or {}).get("electronicDocumentStatus")
    error = (last_row or {}).get("errorDescription")
    raise ValueError(
        f"FEL stamp was not received for invoice {invoice_number}. "
        f"Status: {status or 'unknown'}. Error: {error or 'none'}."
    )


def _is_stamp_received(row: dict[str, Any]) -> bool:
    return " ".join(str(row.get("electronicDocumentStatus") or "").strip().lower().split()) == "stamp received"


def _looks_posted_invoice_number(value: Any) -> bool:
    return str(value or "").strip().upper().startswith("GTFVR")




def _build_proposed_invoice_groups(
    *,
    header_payload: dict[str, Any],
    line_payloads: list[dict[str, Any]],
    line_sources: list[dict[str, Any]],
    split_by_item_prefix: bool,
    shipment_metadata: dict[str, str],
) -> list[dict[str, Any]]:
    metadata_line = _build_shipment_metadata_line(shipment_metadata)
    if not split_by_item_prefix:
        return [
            {
                "invoice_group": "ALL",
                "reference": header_payload["externalDocumentNumber"],
                "proposed_bc_payload": dict(header_payload),
                "proposed_bc_line_payloads": [metadata_line, *line_payloads]
                if metadata_line
                else line_payloads,
                "line_sources": line_sources,
                "total": _sum_line_amounts(line_payloads),
            }
        ]

    grouped_payloads: dict[str, list[dict[str, Any]]] = {}
    grouped_sources: dict[str, list[dict[str, Any]]] = {}
    for line_payload, line_source in zip(line_payloads, line_sources, strict=True):
        group = str(line_source.get("invoice_group") or "OTHER").upper()
        grouped_payloads.setdefault(group, []).append(line_payload)
        grouped_sources.setdefault(group, []).append(line_source)

    proposed_invoices: list[dict[str, Any]] = []
    for group in sorted(grouped_payloads, key=_invoice_group_sort_key):
        group_reference = _invoice_group_reference(header_payload["externalDocumentNumber"], group)
        group_header = {
            **header_payload,
            "externalDocumentNumber": group_reference,
            "customerPurchaseOrderReference": header_payload.get("customerPurchaseOrderReference")
            or header_payload["externalDocumentNumber"],
        }
        proposed_invoices.append(
            {
                "invoice_group": group,
                "reference": group_reference,
                "proposed_bc_payload": group_header,
                "proposed_bc_line_payloads": [metadata_line, *grouped_payloads[group]]
                if metadata_line
                else grouped_payloads[group],
                "line_sources": grouped_sources[group],
                "total": _sum_line_amounts(grouped_payloads[group]),
            }
        )
    return proposed_invoices


def _invoice_group_from_item_number(item_number: str) -> str:
    normalized = (item_number or "").strip().upper()
    if normalized.startswith("INT"):
        return "INT"
    if normalized.startswith("NAT"):
        return "NAT"
    return "OTHER"


def _invoice_group_reference(reference: str, group: str) -> str:
    normalized_group = (group or "").strip().upper()
    if normalized_group in {"", "ALL"}:
        return reference
    suffix = f"-{normalized_group}"
    if reference.upper().endswith(suffix):
        return reference
    return f"{reference}{suffix}"


def _invoice_group_sort_key(group: str) -> tuple[int, str]:
    priority = {"INT": 0, "NAT": 1, "OTHER": 2, "ACCOUNT": 3}
    normalized = (group or "").strip().upper()
    return priority.get(normalized, 9), normalized


def _sum_line_amounts(line_payloads: list[dict[str, Any]]) -> float:
    return round(sum(float(line.get("unitPrice") or 0) for line in line_payloads), 2)


def _resolve_shipment_metadata(
    clickup_summary: dict[str, Any],
    custom_fields: dict[str, dict[str, Any]],
    config: InvoiceAutomationSettings,
) -> dict[str, str]:
    return {
        "shipment_number": str(clickup_summary.get("name") or "").strip(),
        "booking": _first_present_field(custom_fields, config.shipment_booking_field_names),
        "containers": _first_present_field(custom_fields, config.shipment_container_field_names),
    }


def _build_shipment_metadata_line(shipment_metadata: dict[str, str]) -> dict[str, Any] | None:
    booking = _clean_marker_value(shipment_metadata.get("booking"))
    containers = _clean_marker_value(shipment_metadata.get("containers"))
    if not booking and not containers:
        return None

    parts = ["MTM META"]
    if booking:
        parts.append(f"BOOKING {booking}")
    if containers:
        parts.append(f"CONTAINER {containers}")

    return {
        "lineType": "Comment",
        "description": _truncate_for_bc_description(" ".join(parts)),
    }


def _clean_marker_value(value: str | None) -> str:
    return " ".join(str(value or "").replace("\n", " ").split()).strip()


def _truncate_for_bc_description(value: str) -> str:
    return value[:100]


def _combined_created_invoice_for_writeback(created_invoices: list[dict[str, Any]]) -> dict[str, Any]:
    if len(created_invoices) == 1:
        return created_invoices[0]
    return {
        "id": "; ".join(str(invoice.get("id") or "") for invoice in created_invoices if invoice.get("id")),
        "number": "; ".join(
            str(invoice.get("number") or "") for invoice in created_invoices if invoice.get("number")
        ),
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


def _build_mapped_charge_input(
    *,
    custom_fields: dict[str, dict[str, Any]],
    mapping: InvoiceChargeMapping,
) -> dict[str, Any]:
    raw_value, source_field, source_field_id = _present_field_value_and_source(
        custom_fields,
        field_name=mapping.clickup_field_name,
        field_id=mapping.clickup_field_id,
    )
    if not raw_value:
        return {
            "charge_name": mapping.charge_name,
            "amount": None,
            "item_number": mapping.bc_item_number,
            "description": mapping.bc_description or mapping.charge_name,
            "source_field": source_field,
            "source_field_id": source_field_id,
            "tax_group": mapping.tax_group,
        }

    amount = _parse_decimal(raw_value)
    if amount is None:
        return {
            "charge_name": mapping.charge_name,
            "amount": None,
            "item_number": mapping.bc_item_number,
            "description": mapping.bc_description or mapping.charge_name,
            "source_field": source_field,
            "source_field_id": source_field_id,
            "tax_group": mapping.tax_group,
            "error": f"Charge field {source_field or mapping.charge_name} has an invalid numeric value.",
        }

    return {
        "charge_name": mapping.charge_name,
        "amount": amount,
        "item_number": mapping.bc_item_number,
        "description": mapping.bc_description or mapping.charge_name,
        "source_field": source_field,
        "source_field_id": source_field_id,
        "tax_group": mapping.tax_group,
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
    return config.supported_currency


def _resolve_invoice_customer(
    *,
    custom_fields: dict[str, dict[str, Any]],
    bc_client: BusinessCentralClient,
    market: str,
    config: InvoiceAutomationSettings,
    customer_id: str,
    customer_number: str,
) -> dict[str, Any]:
    if customer_id or customer_number:
        return {
            "status": "explicit",
            "source": "business_central_field",
            "customer_id": customer_id or None,
            "customer_number": customer_number or None,
            "customer_name": None,
            "source_field": None,
            "source_field_id": None,
        }

    customer_name, source_field, source_field_id = _first_present_dropdown_or_field_value(
        custom_fields,
        field_names=config.bc_customer_name_field_names,
        field_ids=config.bc_customer_name_field_ids,
    )
    if not customer_name:
        return {
            "status": "missing_source",
            "source": None,
            "customer_id": None,
            "customer_number": None,
            "customer_name": None,
            "source_field": None,
            "source_field_id": None,
        }

    try:
        customer = bc_client.resolve_customer_by_name(customer_name, market=market)
    except ValueError as exc:
        return {
            "status": "ambiguous",
            "message": str(exc),
            "source": "clickup_customer_name",
            "customer_id": None,
            "customer_number": None,
            "customer_name": customer_name,
            "source_field": source_field,
            "source_field_id": source_field_id,
        }

    if not customer:
        return {
            "status": "not_found",
            "source": "clickup_customer_name",
            "customer_id": None,
            "customer_number": None,
            "customer_name": customer_name,
            "source_field": source_field,
            "source_field_id": source_field_id,
        }

    return {
        "status": "resolved",
        "source": "clickup_customer_name",
        "customer_id": customer.get("id") or None,
        "customer_number": customer.get("number") or None,
        "customer_name": customer_name,
        "bc_display_name": customer.get("displayName") or customer.get("name") or None,
        "source_field": source_field,
        "source_field_id": source_field_id,
    }


def _resolve_invoice_status(
    custom_fields: dict[str, dict[str, Any]],
    config: InvoiceAutomationSettings,
    *,
    fallback: str | None,
) -> dict[str, Any]:
    for field_name in config.invoice_status_field_names:
        field = custom_fields.get(field_name)
        if not field:
            continue
        resolved = resolve_dropdown_field(field)
        label = ((resolved or {}).get("name") or "").strip()
        raw = field_value(custom_fields, field_name=field_name)
        status = label or raw
        if status:
            return {
                "status": status,
                "source": "custom_field",
                "field_name": field_name,
                "field_id": field.get("id"),
                "ready_option_id": _dropdown_option_id(field, config.ready_status),
            }

    return {
        "status": fallback,
        "source": "task_status",
        "field_name": None,
        "field_id": None,
        "ready_option_id": None,
    }


def _dropdown_option_id(field: dict[str, Any], option_name: str) -> str | int | None:
    target = _normalize_status(option_name)
    for option in (field.get("type_config") or {}).get("options", []):
        if _normalize_status(option.get("name")) == target:
            return option.get("id") or option.get("orderindex")
    return None


def _resolve_eta_date(
    clickup_summary: dict[str, Any],
    config: InvoiceAutomationSettings,
) -> date | None:
    custom_fields = clickup_summary.get("custom_fields") or {}
    eta = _resolve_date_from_fields(
        custom_fields,
        config.eta_field_names,
        field_ids=config.eta_field_ids,
    )
    if eta is not None:
        return eta
    return _parse_date(clickup_summary.get("due_date"))


def _resolve_date_from_fields(
    custom_fields: dict[str, dict[str, Any]],
    field_names: tuple[str, ...],
    *,
    field_ids: tuple[str, ...] = (),
) -> date | None:
    for field_name in field_names:
        field = custom_fields.get(field_name) or {}
        value = field.get("value")
        parsed = _parse_date(value)
        if parsed is not None:
            return parsed
    for field_id in field_ids:
        field = _find_field_by_id(custom_fields, field_id) or {}
        parsed = _parse_date(field.get("value"))
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


def _first_present_dropdown_or_field_value(
    custom_fields: dict[str, dict[str, Any]],
    *,
    field_names: tuple[str, ...],
    field_ids: tuple[str, ...],
) -> tuple[str, str | None, str | None]:
    for field_name in field_names:
        field = custom_fields.get(field_name)
        value = _dropdown_or_raw_field_value(field)
        if value:
            return value, field_name, (field or {}).get("id")

    for field_id in field_ids:
        field = _find_field_by_id(custom_fields, field_id)
        value = _dropdown_or_raw_field_value(field)
        if value:
            return value, _field_name_by_id(custom_fields, field_id), field_id

    return "", None, None


def _dropdown_or_raw_field_value(field: dict[str, Any] | None) -> str:
    label = ((resolve_dropdown_field(field) or {}).get("name") or "").strip()
    if label:
        return label
    value = (field or {}).get("value")
    if value is None:
        return ""
    return str(value).strip()


def _find_field_by_id(
    custom_fields: dict[str, dict[str, Any]],
    field_id: str,
) -> dict[str, Any] | None:
    if not field_id:
        return None
    for details in custom_fields.values():
        if details.get("id") == field_id:
            return details
    return None


def _field_name_by_id(
    custom_fields: dict[str, dict[str, Any]],
    field_id: str,
) -> str | None:
    if not field_id:
        return None
    for field_name, details in custom_fields.items():
        if details.get("id") == field_id:
            return field_name
    return None


def _present_field_value_and_source(
    custom_fields: dict[str, dict[str, Any]],
    *,
    field_name: str,
    field_id: str,
) -> tuple[str, str | None, str | None]:
    field = None
    if field_id:
        for candidate_name, details in custom_fields.items():
            if details.get("id") == field_id:
                field = details
                source_name = candidate_name
                break
        else:
            source_name = None
    else:
        source_name = None

    if field is None and field_name:
        field = custom_fields.get(field_name)
        source_name = field_name if field is not None else source_name

    value = (field or {}).get("value")
    if value is None:
        return "", source_name, field_id or None
    return str(value).strip(), source_name, (field or {}).get("id") or field_id or None


def _status_equals(left: str | None, right: str | None) -> bool:
    return _normalize_status(left) == _normalize_status(right)


def _normalize_status(value: str | None) -> str:
    return " ".join((value or "").strip().lower().replace("-", " ").split())


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


def load_invoice_charge_mappings(path: str | os.PathLike[str]) -> tuple[InvoiceChargeMapping, ...]:
    mapping_path = Path(path)
    if not mapping_path.exists():
        raise ValueError(f"Invoice charge mapping file does not exist: {mapping_path}")

    payload = json.loads(mapping_path.read_text(encoding="utf-8"))
    rows = payload.get("mappings")
    if not isinstance(rows, list):
        raise ValueError(f"Invoice charge mapping file must contain a mappings list: {mapping_path}")

    mappings: list[InvoiceChargeMapping] = []
    seen_field_ids: set[str] = set()
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"Invoice charge mapping row {index} must be an object.")

        charge_name = str(row.get("charge_name") or row.get("clickup_field_name") or "").strip()
        clickup_field_name = str(row.get("clickup_field_name") or charge_name).strip()
        clickup_field_id = str(row.get("clickup_field_id") or "").strip()
        bc_item_number = str(row.get("bc_item_number") or "").strip()
        bc_description = str(row.get("bc_description") or charge_name).strip()
        tax_group = str(row.get("tax_group") or "").strip() or None
        missing = [
            name
            for name, value in (
                ("charge_name", charge_name),
                ("clickup_field_name", clickup_field_name),
                ("clickup_field_id", clickup_field_id),
                ("bc_item_number", bc_item_number),
                ("bc_description", bc_description),
            )
            if not value
        ]
        if missing:
            raise ValueError(f"Invoice charge mapping row {index} is missing: {', '.join(missing)}")
        if clickup_field_id in seen_field_ids:
            raise ValueError(f"Duplicate ClickUp field ID in invoice charge mapping: {clickup_field_id}")
        seen_field_ids.add(clickup_field_id)
        mappings.append(
            InvoiceChargeMapping(
                charge_name=charge_name,
                clickup_field_name=clickup_field_name,
                clickup_field_id=clickup_field_id,
                bc_item_number=bc_item_number,
                bc_description=bc_description,
                tax_group=tax_group,
            )
        )

    return tuple(mappings)


def _env_invoice_charge_mapping_path(market: str) -> str | None:
    explicit = os.getenv("CLICKUP_INVOICE_CHARGE_MAPPING_PATH", "").strip()
    if explicit:
        return explicit

    default_path = Path("config") / "invoice_charge_mappings" / f"{market.lower()}.json"
    if default_path.exists():
        return str(default_path)
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
