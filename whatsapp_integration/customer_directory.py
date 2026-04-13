from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from clickup_integration.mapping import resolve_dropdown_field
from whatsapp_integration.booking_intake import normalize_phone_key
from whatsapp_integration.config import WhatsAppSettings


@dataclass(frozen=True)
class CustomerDirectoryMatch:
    task_id: str
    task_name: str | None
    custom_id: str | None
    customer_name: str | None
    target_list_id: str | None
    matched_phone_field: str


def find_customer_directory_match(
    *,
    clickup: Any,
    phone_number: str,
    settings: WhatsAppSettings,
) -> CustomerDirectoryMatch | None:
    if not settings.customer_directory_list_id:
        return None

    target_phone = normalize_phone_key(phone_number)
    if not target_phone:
        return None

    matches: list[tuple[str, CustomerDirectoryMatch]] = []
    for page in range(settings.directory_task_scan_pages):
        payload = clickup.get_list_tasks(
            settings.customer_directory_list_id,
            archived=False,
            include_closed=True,
            page=page,
        )
        tasks = payload.get("tasks") or []
        for task in tasks:
            if not _task_status_allowed(task=task, settings=settings):
                continue
            field_map = _custom_field_map(task)
            phone_field = _first_matching_phone_field(
                field_map=field_map,
                phone_number=target_phone,
                field_names=settings.directory_phone_field_names,
            )
            if not phone_field:
                continue
            hydrated_task = _hydrate_task(clickup=clickup, task=task)
            hydrated_field_map = _custom_field_map(hydrated_task)
            matches.append(
                (
                    str(hydrated_task.get("date_updated") or hydrated_task.get("date_created") or ""),
                    CustomerDirectoryMatch(
                        task_id=str(hydrated_task.get("id") or ""),
                        task_name=str(hydrated_task.get("name") or "").strip() or None,
                        custom_id=str(hydrated_task.get("custom_id") or "").strip() or None,
                        customer_name=_resolve_customer_name(
                            task=hydrated_task,
                            field_map=hydrated_field_map,
                            field_names=settings.directory_customer_name_field_names,
                        ),
                        target_list_id=_resolve_target_list_id(
                            field_map=hydrated_field_map,
                            field_names=settings.directory_target_list_field_names,
                            field_ids=settings.directory_target_list_field_ids,
                        ),
                        matched_phone_field=phone_field,
                    ),
                )
            )
        if len(tasks) < 100:
            break

    if not matches:
        return None

    matches.sort(key=lambda item: item[0], reverse=True)
    return matches[0][1]


def _task_status_allowed(*, task: dict[str, Any], settings: WhatsAppSettings) -> bool:
    allowed = settings.directory_allowed_statuses
    if not allowed:
        return True
    status = (task.get("status") or {}).get("status")
    normalized = " ".join(str(status or "").strip().lower().split())
    return normalized in allowed


def _hydrate_task(*, clickup: Any, task: dict[str, Any]) -> dict[str, Any]:
    task_id = str(task.get("id") or "").strip()
    if not task_id or not hasattr(clickup, "get_task"):
        return task
    try:
        hydrated = clickup.get_task(
            task_id,
            custom_task_ids=False,
            include_subtasks=False,
        )
    except Exception:
        return task
    if isinstance(hydrated, dict) and hydrated.get("id"):
        return hydrated
    return task


def _custom_field_map(task: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for field in task.get("custom_fields") or []:
        name = str(field.get("name") or field.get("id") or "").strip()
        if not name:
            continue
        result[name] = {
            "id": field.get("id"),
            "type": field.get("type"),
            "value": field.get("value"),
            "type_config": field.get("type_config"),
        }
    return result


def _first_matching_phone_field(
    *,
    field_map: dict[str, dict[str, Any]],
    phone_number: str,
    field_names: tuple[str, ...],
) -> str | None:
    for field_name in field_names:
        value = _first_field_value(field_map=field_map, field_names=(field_name,))
        if normalize_phone_key(value) == phone_number:
            return field_name
    return None


def _resolve_customer_name(
    *,
    task: dict[str, Any],
    field_map: dict[str, dict[str, Any]],
    field_names: tuple[str, ...],
) -> str | None:
    for field_name in field_names:
        field = field_map.get(field_name)
        if not field:
            continue
        dropdown = resolve_dropdown_field(field)
        if dropdown and (dropdown.get("name") or "").strip():
            return str(dropdown["name"]).strip()
        value = field.get("value")
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    task_name = str(task.get("name") or "").strip()
    return task_name or None


def _first_field_value(
    *,
    field_map: dict[str, dict[str, Any]],
    field_names: tuple[str, ...],
    field_ids: tuple[str, ...] = (),
) -> str | None:
    for field_name in field_names:
        field = field_map.get(field_name)
        if not field:
            continue
        value = field.get("value")
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    for field in field_map.values():
        field_id = str(field.get("id") or "").strip()
        if field_id not in field_ids:
            continue
        value = field.get("value")
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _resolve_target_list_id(
    *,
    field_map: dict[str, dict[str, Any]],
    field_names: tuple[str, ...],
    field_ids: tuple[str, ...],
) -> str | None:
    raw_value = _first_field_value(
        field_map=field_map,
        field_names=field_names,
        field_ids=field_ids,
    )
    if not raw_value:
        return None
    return parse_clickup_list_identifier(raw_value)


def parse_clickup_list_identifier(value: str) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.isdigit():
        return text

    parsed = urlparse(text)
    path = parsed.path.rstrip("/")
    if not path:
        return None
    parts = [part for part in path.split("/") if part]
    if len(parts) >= 4 and parts[-2] == "li" and parts[-1].isdigit():
        return parts[-1]
    return None
