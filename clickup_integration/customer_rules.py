from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from clickup_integration.mapping import resolve_dropdown_field


CLICKUP_CREDIT_TERMS_FIELD_ID = "0d38f633-717b-420b-bb1d-07443855a998"
CLICKUP_CREDIT_APPROVED_FIELD_ID = "54574add-833f-42a5-b027-3b0d64ef95af"
CLICKUP_CONTACT_NAME_1_FIELD_ID = "b6d78494-948e-4439-aed0-f37181c17373"
CLICKUP_CREDIT_TERMS_FIELD_NAMES = ("Credit Terms", "Credit Days Required")
CLICKUP_CREDIT_APPROVED_FIELD_NAMES = ("Credit amount approved", "Credit Approved")


def find_custom_field(
    custom_fields: dict[str, dict[str, Any]],
    *,
    field_name: str | None = None,
    field_id: str | None = None,
) -> dict[str, Any] | None:
    if field_name and field_name in custom_fields:
        return custom_fields[field_name]
    if field_id:
        for details in custom_fields.values():
            if details.get("id") == field_id:
                return details
    return None


def field_value(
    custom_fields: dict[str, dict[str, Any]],
    *,
    field_name: str | None = None,
    field_id: str | None = None,
) -> str:
    field = find_custom_field(custom_fields, field_name=field_name, field_id=field_id)
    value = (field or {}).get("value")
    if value is None:
        return ""
    return str(value).strip()


def dropdown_label(
    custom_fields: dict[str, dict[str, Any]],
    *,
    field_name: str | None = None,
    field_id: str | None = None,
) -> str:
    field = find_custom_field(custom_fields, field_name=field_name, field_id=field_id)
    resolved = resolve_dropdown_field(field)
    return ((resolved or {}).get("name") or "").strip()


def location_formatted_address(
    custom_fields: dict[str, dict[str, Any]],
    *,
    field_name: str,
) -> str:
    field = custom_fields.get(field_name) or {}
    value = field.get("value")
    if isinstance(value, str):
        return value.strip()
    if not isinstance(value, dict):
        return ""
    if isinstance(value.get("formatted_address"), str):
        return value["formatted_address"].strip()
    location = value.get("location")
    if isinstance(location, dict):
        formatted = location.get("formatted_address")
        if isinstance(formatted, str):
            return formatted.strip()
    return ""


def normalize_customer_name(value: str) -> str:
    return " ".join((value or "").strip().upper().split())


def normalize_tax_id_digits(value: str) -> str:
    return re.sub(r"\D+", "", value or "")


def normalize_email(value: str) -> str:
    return (value or "").strip()


def normalize_credit_limit(value: str) -> int | float | None:
    cleaned = re.sub(r"[^0-9.\-]", "", value or "")
    if not cleaned:
        return None
    try:
        numeric = Decimal(cleaned)
    except InvalidOperation:
        return None
    if numeric == numeric.to_integral():
        return int(numeric)
    return float(numeric)


def payment_method_code_from_credit_terms(value: str) -> str | None:
    normalized = normalize_customer_name(value)
    if not normalized:
        return None
    return "CONTADO" if normalized == "CONTADO" else "CREDITO"


def normalize_credit_terms_label(value: str) -> str:
    normalized = normalize_customer_name(value)
    if not normalized:
        return ""
    if normalized == "0":
        return "CONTADO"
    if normalized.isdigit():
        return f"{normalized} DÍAS"
    return normalized


def resolve_clickup_credit_terms(custom_fields: dict[str, dict[str, Any]]) -> str:
    for field_name in CLICKUP_CREDIT_TERMS_FIELD_NAMES:
        label = dropdown_label(custom_fields, field_name=field_name)
        if label:
            return normalize_credit_terms_label(label)
        value = field_value(custom_fields, field_name=field_name)
        if value:
            return normalize_credit_terms_label(value)

    for field_name, details in custom_fields.items():
        if details.get("id") != CLICKUP_CREDIT_TERMS_FIELD_ID:
            continue
        normalized_name = (field_name or "").strip().lower()
        if "credit" not in normalized_name and "payment" not in normalized_name:
            return ""
        label = dropdown_label(custom_fields, field_id=CLICKUP_CREDIT_TERMS_FIELD_ID)
        if label:
            return normalize_credit_terms_label(label)
        raw = field_value(custom_fields, field_id=CLICKUP_CREDIT_TERMS_FIELD_ID)
        if raw:
            return normalize_credit_terms_label(raw)

    return ""


def resolve_clickup_credit_approved(custom_fields: dict[str, dict[str, Any]]) -> int | float | None:
    value = field_value(custom_fields, field_id=CLICKUP_CREDIT_APPROVED_FIELD_ID)
    if value:
        return normalize_credit_limit(value)

    for field_name in CLICKUP_CREDIT_APPROVED_FIELD_NAMES:
        value = field_value(custom_fields, field_name=field_name)
        if value:
            return normalize_credit_limit(value)

    return None
