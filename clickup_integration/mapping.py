from __future__ import annotations

from typing import Any


def summarize_task_for_customer_mapping(task: dict[str, Any]) -> dict[str, Any]:
    custom_fields = {}
    for field in task.get("custom_fields", []):
        field_name = field.get("name") or field.get("id")
        custom_fields[field_name] = {
            "id": field.get("id"),
            "type": field.get("type"),
            "value": field.get("value"),
            "type_config": field.get("type_config"),
        }

    list_info = task.get("list") or {}
    folder_info = task.get("folder") or {}
    space_info = task.get("space") or {}

    return {
        "task_id": task.get("id"),
        "custom_id": task.get("custom_id"),
        "name": task.get("name"),
        "status": (task.get("status") or {}).get("status"),
        "sync_eligible": is_current_customer_status((task.get("status") or {}).get("status")),
        "url": task.get("url"),
        "date_created": task.get("date_created"),
        "date_updated": task.get("date_updated"),
        "workspace": {
            "id": (space_info.get("id") if isinstance(space_info, dict) else None),
            "name": (space_info.get("name") if isinstance(space_info, dict) else None),
        },
        "folder": {
            "id": (folder_info.get("id") if isinstance(folder_info, dict) else None),
            "name": (folder_info.get("name") if isinstance(folder_info, dict) else None),
        },
        "list": {
            "id": (list_info.get("id") if isinstance(list_info, dict) else None),
            "name": (list_info.get("name") if isinstance(list_info, dict) else None),
        },
        "assignees": [
            {
                "id": assignee.get("id"),
                "username": assignee.get("username"),
                "email": assignee.get("email"),
            }
            for assignee in task.get("assignees", [])
        ],
        "custom_fields": custom_fields,
        "owner_country": resolve_dropdown_field(custom_fields.get("Owner Country/")),
        "market": resolve_market_code_from_owner_country(
            resolve_dropdown_field(custom_fields.get("Owner Country/"))
        ),
    }


def resolve_dropdown_field(field: dict[str, Any] | None) -> dict[str, Any] | None:
    if not field or field.get("value") is None:
        return None

    value = field.get("value")
    type_config = field.get("type_config") or {}
    for option in type_config.get("options", []):
        if option.get("orderindex") == value or option.get("id") == value:
            return option
        if str(option.get("orderindex")) == str(value):
            return option
        if str(option.get("id")) == str(value):
            return option

    return None


def resolve_market_code_from_owner_country(owner_country: dict[str, Any] | None) -> str | None:
    if not owner_country:
        return None

    mapping = {
        "mexico": "MX",
        "guatemala": "GT",
    }
    normalized = (owner_country.get("name") or "").strip().lower()
    return mapping.get(normalized)


def is_current_customer_status(status: str | None) -> bool:
    normalized = " ".join((status or "").strip().lower().split())
    return normalized == "current customer"
