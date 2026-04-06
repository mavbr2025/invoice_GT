from __future__ import annotations

import re
from typing import Any

from business_central_client.client import BusinessCentralClient
from clickup_integration.mapping import is_current_customer_status
from clickup_integration.writeback import _resolve_dropdown_option_name


CLICKUP_PHONE_FIELD_CANDIDATES = (
    "Contact Phone 1",
    "Contact Phone Number",
    "Phone",
    "Contact Phone 2",
    "Contact Phone 3",
    "Contact Phone 4",
    "Contact Phone 5",
    "Contact Phone 6",
)

CLICKUP_WEBSITE_FIELD = "Webpage"
BC_FIELD_NAMES = {
    "customer_id": "Business Central Customer ID",
    "customer_number": "Business Central Customer Number",
    "match_status": "BC Match Status",
}


def prepare_clickup_to_bc_customer_sync(
    *,
    clickup_summary: dict[str, Any],
    bc_client: BusinessCentralClient,
) -> dict[str, Any]:
    task_status = clickup_summary.get("status")
    if not is_current_customer_status(task_status):
        return {
            "status": "not_current_customer",
            "message": (
                "ClickUp task is not eligible for BC customer updates. "
                "Only tasks with status CURRENT CUSTOMER are processed."
            ),
            "task_status": task_status,
        }

    market = clickup_summary.get("market")
    if not market:
        return {
            "status": "no_market",
            "message": "ClickUp task does not resolve to a supported market from Owner Country/.",
            "task_status": task_status,
        }

    custom_fields = clickup_summary.get("custom_fields") or {}
    bc_customer_id = _field_value(custom_fields, BC_FIELD_NAMES["customer_id"])
    bc_customer_number = _field_value(custom_fields, BC_FIELD_NAMES["customer_number"])
    match_status_name = _match_status_name(custom_fields.get(BC_FIELD_NAMES["match_status"]))

    if match_status_name != "Confirmed":
        return {
            "status": "not_confirmed",
            "message": "ClickUp task does not have a confirmed BC match. Updates to BC are blocked.",
            "task_status": task_status,
            "market": market,
            "bc_match_status": match_status_name,
        }

    if not bc_customer_id:
        return {
            "status": "missing_bc_customer_id",
            "message": "ClickUp task does not have a Business Central Customer ID.",
            "task_status": task_status,
            "market": market,
            "bc_match_status": match_status_name,
        }

    bc_customer = bc_client.get_entity("customers", bc_customer_id, market=market)

    clickup_phone = _first_present_field(custom_fields, CLICKUP_PHONE_FIELD_CANDIDATES)
    clickup_website = _field_value(custom_fields, CLICKUP_WEBSITE_FIELD)

    proposed_updates: dict[str, str] = {}
    comparison = {
        "phone": {
            "clickup": clickup_phone or None,
            "bc": (bc_customer.get("phoneNumber") or None),
            "will_update": False,
        },
        "website": {
            "clickup": clickup_website or None,
            "bc": (bc_customer.get("website") or None),
            "will_update": False,
        },
    }

    if clickup_phone and not _phone_equivalent(clickup_phone, bc_customer.get("phoneNumber") or ""):
        proposed_updates["phoneNumber"] = clickup_phone
        comparison["phone"]["will_update"] = True

    if clickup_website and not _website_equivalent(clickup_website, bc_customer.get("website") or ""):
        proposed_updates["website"] = clickup_website
        comparison["website"]["will_update"] = True

    return {
        "status": "dry_run_ready" if proposed_updates else "no_changes",
        "task_status": task_status,
        "market": market,
        "bc_match_status": match_status_name,
        "task_id": clickup_summary.get("task_id"),
        "bc_customer_id": bc_customer_id,
        "bc_customer_number": bc_customer_number or bc_customer.get("number"),
        "bc_customer_name": bc_customer.get("displayName"),
        "clickup_sources": {
            "phone_field": _first_present_field_name(custom_fields, CLICKUP_PHONE_FIELD_CANDIDATES),
            "website_field": CLICKUP_WEBSITE_FIELD if clickup_website else None,
        },
        "comparison": comparison,
        "proposed_bc_patch": proposed_updates,
    }


def apply_clickup_to_bc_customer_sync(
    *,
    clickup_summary: dict[str, Any],
    bc_client: BusinessCentralClient,
) -> dict[str, Any]:
    preview = prepare_clickup_to_bc_customer_sync(
        clickup_summary=clickup_summary,
        bc_client=bc_client,
    )
    if preview.get("status") != "dry_run_ready":
        return preview

    updated = bc_client.patch_entity(
        "customers",
        preview["bc_customer_id"],
        preview["proposed_bc_patch"],
        market=preview["market"],
    )
    return {
        **preview,
        "status": "applied",
        "updated_customer": updated,
    }


def _field_value(custom_fields: dict[str, Any], field_name: str) -> str:
    value = (custom_fields.get(field_name) or {}).get("value")
    if value is None:
        return ""
    return str(value).strip()


def _first_present_field(custom_fields: dict[str, Any], field_names: tuple[str, ...]) -> str:
    for field_name in field_names:
        value = _field_value(custom_fields, field_name)
        if value:
            return value
    return ""


def _first_present_field_name(custom_fields: dict[str, Any], field_names: tuple[str, ...]) -> str | None:
    for field_name in field_names:
        value = _field_value(custom_fields, field_name)
        if value:
            return field_name
    return None


def _match_status_name(field: dict[str, Any] | None) -> str | None:
    if not field:
        return None
    return _resolve_dropdown_option_name(field, field.get("value"))


def _phone_equivalent(left: str, right: str) -> bool:
    return _digits_only(left) == _digits_only(right) and bool(_digits_only(left))


def _website_equivalent(left: str, right: str) -> bool:
    return _normalize_website(left) == _normalize_website(right) and bool(_normalize_website(left))


def _digits_only(value: str) -> str:
    return re.sub(r"\D+", "", value or "")


def _normalize_website(value: str) -> str:
    normalized = (value or "").strip().lower().rstrip("/")
    normalized = re.sub(r"^https?://", "", normalized)
    return normalized
