from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from clickup_integration.mapping import summarize_task_for_customer_mapping


def summarize_task_for_report(
    task: dict[str, Any],
    *,
    report_field_names: tuple[str, ...],
) -> dict[str, Any]:
    summary = summarize_task_for_customer_mapping(task)
    custom_fields = summary.get("custom_fields") or {}
    report_fields: dict[str, str] = {}

    for field_name in report_field_names:
        field = _find_field_by_names(custom_fields, (field_name,))
        value = resolve_field_value(field)
        if value:
            report_fields[field_name] = value

    return {
        **summary,
        "report_fields": report_fields,
    }


def resolve_field_value(field: dict[str, Any] | None) -> str | None:
    if not field:
        return None

    value = field.get("value")
    if value in (None, ""):
        return None

    field_type = field.get("type")
    if field_type == "drop_down":
        option = _resolve_dropdown_option(field, value)
        return option.get("name") if option else str(value)

    if field_type in {"labels", "tasks"} and isinstance(value, list):
        return ", ".join(str(item) for item in value if item not in (None, ""))

    if field_type == "date":
        try:
            timestamp = int(value) / 1000
        except (TypeError, ValueError):
            return str(value)
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).date().isoformat()

    if field_type == "currency" and isinstance(value, dict):
        amount = value.get("amount")
        currency = value.get("currency") or (field.get("type_config") or {}).get("currency_type")
        if amount is None:
            return None
        return f"{amount} {currency}".strip()

    if isinstance(value, dict):
        if value.get("url"):
            return str(value["url"])
        if value.get("text"):
            return str(value["text"])
        return ", ".join(f"{key}: {item}" for key, item in value.items() if item not in (None, ""))

    return str(value).strip() or None


def get_field_value_by_names(
    custom_fields: dict[str, dict[str, Any]],
    field_names: tuple[str, ...],
) -> str | None:
    return resolve_field_value(_find_field_by_names(custom_fields, field_names))


def get_field_value_by_ids(
    custom_fields: dict[str, dict[str, Any]],
    field_ids: tuple[str, ...],
) -> str | None:
    return resolve_field_value(_find_field_by_ids(custom_fields, field_ids))


def get_field_details_by_names(
    custom_fields: dict[str, dict[str, Any]],
    field_names: tuple[str, ...],
) -> dict[str, Any] | None:
    return _find_field_by_names(custom_fields, field_names)


def get_field_details_by_ids(
    custom_fields: dict[str, dict[str, Any]],
    field_ids: tuple[str, ...],
) -> dict[str, Any] | None:
    return _find_field_by_ids(custom_fields, field_ids)


def build_identifier_values(
    summary: dict[str, Any],
    *,
    field_names: tuple[str, ...],
) -> tuple[str, ...]:
    identifiers: list[str] = []
    for value in (
        summary.get("custom_id"),
        summary.get("name"),
    ):
        if value:
            identifiers.append(str(value))

    custom_fields = summary.get("custom_fields") or {}
    for field_name in field_names:
        value = get_field_value_by_names(custom_fields, (field_name,))
        if value:
            identifiers.append(value)

    seen: set[str] = set()
    unique: list[str] = []
    for value in identifiers:
        normalized = " ".join(value.split())
        if normalized and normalized.lower() not in seen:
            seen.add(normalized.lower())
            unique.append(normalized)
    return tuple(unique)


def prepare_report_link_writeback(
    summary: dict[str, Any],
    *,
    report_url: str,
    report_link_field_names: tuple[str, ...],
    report_link_field_ids: tuple[str, ...] = (),
) -> dict[str, Any]:
    custom_fields = summary.get("custom_fields") or {}
    field = _find_field_by_ids(custom_fields, report_link_field_ids)
    if not field:
        field = _find_field_by_names(custom_fields, report_link_field_names)
    if not field and report_link_field_ids:
        field = {"id": report_link_field_ids[0]}
    if not field or not field.get("id"):
        return {
            "task_id": summary.get("task_id"),
            "status": "missing_field",
            "missing_field_names": report_link_field_names,
            "missing_field_ids": report_link_field_ids,
        }

    return {
        "task_id": summary["task_id"],
        "status": "ready",
        "field_id": field["id"],
        "field_name": _resolve_field_name(custom_fields, field),
        "value": report_url,
    }


def _find_field_by_names(
    custom_fields: dict[str, dict[str, Any]],
    field_names: tuple[str, ...],
) -> dict[str, Any] | None:
    normalized_targets = {_normalize_name(name) for name in field_names}
    for name, details in custom_fields.items():
        if _normalize_name(name) in normalized_targets:
            return details
    return None


def _find_field_by_ids(
    custom_fields: dict[str, dict[str, Any]],
    field_ids: tuple[str, ...],
) -> dict[str, Any] | None:
    target_ids = {field_id.strip() for field_id in field_ids if field_id.strip()}
    if not target_ids:
        return None
    for details in custom_fields.values():
        if details.get("id") in target_ids:
            return details
    return None


def _resolve_field_name(
    custom_fields: dict[str, dict[str, Any]],
    field: dict[str, Any],
) -> str | None:
    for name, candidate in custom_fields.items():
        if candidate is field or candidate.get("id") == field.get("id"):
            return name
    return None


def _resolve_dropdown_option(field: dict[str, Any], value: Any) -> dict[str, Any] | None:
    for option in (field.get("type_config") or {}).get("options", []):
        if option.get("id") == value or option.get("orderindex") == value:
            return option
        if str(option.get("id")) == str(value):
            return option
        if str(option.get("orderindex")) == str(value):
            return option
    return None


def _normalize_name(value: str) -> str:
    return " ".join(value.strip().lower().replace("/", " ").split())
