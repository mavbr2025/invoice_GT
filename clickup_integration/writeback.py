from __future__ import annotations

from typing import Any
from urllib.parse import quote

from business_central_client.client import BusinessCentralClient


BC_FIELD_DEFS = {
    "number": {
        "name": "Business Central Customer Number",
    },
    "id": {
        "name": "Business Central Customer ID",
    },
    "link": {
        "name": "Business Central Customer Link",
    },
    "legal_name": {
        "name": "Business Central Legal Name",
        "id": "708a731c-f104-4327-b500-687cb103eac0",
    },
    "status": {
        "name": "BC Match Status",
    },
}


def build_bc_customer_url(
    *,
    tenant_id: str,
    environment: str,
    company_name: str,
    customer_number: str,
) -> str:
    base = f"https://businesscentral.dynamics.com/{tenant_id}/{quote(environment, safe='')}/"
    filter_expr = f"Customer.'No.' IS '{customer_number}'"
    query = (
        f"?company={quote(company_name, safe='')}"
        f"&page=21"
        f"&filter={quote(filter_expr, safe='')}"
        f"&dc=0"
    )
    return base + query


def prepare_clickup_bc_writeback(
    *,
    clickup_summary: dict[str, Any],
    match_result: dict[str, Any],
    bc_client: BusinessCentralClient,
) -> dict[str, Any]:
    if match_result.get("status") not in {"likely_match", "possible_match"}:
        raise ValueError("No eligible BC match is available for write-back.")

    candidates = match_result.get("candidates") or []
    if not candidates:
        raise ValueError("No BC candidates were returned.")

    best = candidates[0]
    company = bc_client.get_company_metadata(market=best.get("market"))
    if not company:
        raise ValueError(f"Could not resolve company metadata for market {best.get('market')}.")

    company_name = company.get("name") or company.get("displayName")
    if not company_name:
        raise ValueError("Could not determine the Business Central company name for the link.")

    link = build_bc_customer_url(
        tenant_id=bc_client.settings.tenant_id,
        environment=bc_client.settings.environment,
        company_name=company_name,
        customer_number=best["number"],
    )

    field_lookup = {
        key: _find_clickup_field(
            clickup_summary.get("custom_fields") or {},
            field_name=field_def["name"],
            fallback_field_id=field_def.get("id"),
        )
        for key, field_def in BC_FIELD_DEFS.items()
    }

    missing_fields = [
        BC_FIELD_DEFS[key]["name"]
        for key, details in field_lookup.items()
        if details is None
    ]
    if missing_fields:
        missing = ", ".join(missing_fields)
        raise ValueError(f"ClickUp task is missing required BC write-back fields: {missing}")

    status_field = field_lookup["status"]
    status_value = _resolve_match_status_value(status_field, match_result["status"])

    return {
        "task_id": clickup_summary["task_id"],
        "market": best.get("market"),
        "bc_customer_number": best["number"],
        "bc_customer_id": best.get("id"),
        "bc_customer_link": link,
        "bc_legal_name": best.get("displayName"),
        "bc_match_status": status_value,
        "field_ids": {
            "number": field_lookup["number"]["id"],
            "id": field_lookup["id"]["id"],
            "link": field_lookup["link"]["id"],
            "legal_name": field_lookup["legal_name"]["id"],
            "status": field_lookup["status"]["id"],
        },
    }


def _resolve_match_status_value(field: dict[str, Any], match_status: str) -> str:
    current_name = _resolve_dropdown_option_name(field, field.get("value"))
    if current_name == "Confirmed":
        return resolve_clickup_dropdown_option_id(field, "Confirmed")

    desired_label = "Likely Match" if match_status == "likely_match" else "Unmatched"
    return resolve_clickup_dropdown_option_id(field, desired_label)


def _find_clickup_field(
    custom_fields: dict[str, dict[str, Any]],
    *,
    field_name: str,
    fallback_field_id: str | None = None,
) -> dict[str, Any] | None:
    if field_name in custom_fields:
        return custom_fields[field_name]

    if fallback_field_id:
        for details in custom_fields.values():
            if details.get("id") == fallback_field_id:
                return details
        return {"id": fallback_field_id}

    return None


def _resolve_dropdown_option_name(field: dict[str, Any], value: Any) -> str | None:
    for option in (field.get("type_config") or {}).get("options", []):
        if option.get("id") == value or option.get("orderindex") == value:
            return option.get("name")
        if value is not None and str(option.get("id")) == str(value):
            return option.get("name")
        if value is not None and str(option.get("orderindex")) == str(value):
            return option.get("name")
    return None


def resolve_clickup_dropdown_option_id(field: dict[str, Any], label: str) -> str:
    for option in (field.get("type_config") or {}).get("options", []):
        if option.get("name") == label:
            return option["id"]
    raise ValueError(f"Could not resolve ClickUp dropdown option for {label}.")
