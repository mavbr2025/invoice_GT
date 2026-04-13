from __future__ import annotations

import logging
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Any

from whatsapp_integration.config import WhatsAppSettings


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BookingTarget:
    list_id: str
    customer_name: str | None = None
    customer_task_id: str | None = None
    customer_task_name: str | None = None
    customer_task_custom_id: str | None = None
    route_source: str | None = None


def process_whatsapp_booking_intake(
    *,
    event: dict[str, Any],
    clickup: Any,
    settings: WhatsAppSettings,
    target: BookingTarget,
) -> dict[str, Any]:
    customer_phone = (event.get("customer_phone") or "").strip()
    if not customer_phone:
        return {
            "status": "ignored",
            "reason": "missing_customer_phone",
            "message_id": event.get("message_id"),
        }

    if not target.list_id:
        raise ValueError("No ClickUp target list is configured for WhatsApp intake.")

    field_map = _load_list_field_map(
        clickup=clickup,
        list_id=target.list_id,
    )
    logger.info(
        "Processing WhatsApp booking intake route_source=%s customer_phone=%s target_list_id=%s routed_customer=%s customer_task_id=%s customer_task_custom_id=%s",
        target.route_source,
        customer_phone,
        target.list_id,
        target.customer_name,
        target.customer_task_id,
        target.customer_task_custom_id,
    )
    existing_task = _find_existing_task(
        clickup=clickup,
        list_id=target.list_id,
        phone_number=customer_phone,
        settings=settings,
    )

    if existing_task and _is_duplicate_message(existing_task=existing_task, event=event, settings=settings):
        logger.info(
            "Ignoring duplicate WhatsApp message message_id=%s task_id=%s target_list_id=%s",
            event.get("message_id"),
            existing_task.get("id"),
            target.list_id,
        )
        return {
            "status": "ignored",
            "reason": "duplicate_message",
            "task_id": existing_task.get("id"),
            "message_id": event.get("message_id"),
        }

    if existing_task:
        comment_text = build_whatsapp_comment(event)
        clickup.create_task_comment(
            existing_task["id"],
            comment_text=comment_text,
            notify_all=False,
        )
        logger.info(
            "Appending WhatsApp message to existing task task_id=%s target_list_id=%s",
            existing_task.get("id"),
            target.list_id,
        )
        applied_fields = _apply_field_updates(
            clickup=clickup,
            task_id=existing_task["id"],
            field_map=field_map,
            updates=_build_field_updates(event=event, settings=settings, target=target),
        )
        return {
            "status": "processed",
            "action": "append_to_existing_task",
            "task_id": existing_task.get("id"),
            "task_name": existing_task.get("name"),
            "message_id": event.get("message_id"),
            "list_id": target.list_id,
            "routed_customer": target.customer_name,
            "route_source": target.route_source,
            "customer_task_id": target.customer_task_id,
            "customer_task_custom_id": target.customer_task_custom_id,
            "field_updates": applied_fields,
        }

    task = clickup.create_task(
        target.list_id,
        name=build_task_name(event=event, settings=settings, target=target),
        description=build_task_description(event, target=target),
        status=settings.booking_status_new,
    )
    task_id = task.get("id")
    if not task_id:
        raise ValueError("ClickUp create_task did not return a task id.")
    logger.info(
        "Created WhatsApp booking task task_id=%s target_list_id=%s routed_customer=%s",
        task_id,
        target.list_id,
        target.customer_name,
    )

    applied_fields = _apply_field_updates(
        clickup=clickup,
        task_id=str(task_id),
        field_map=field_map,
        updates=_build_field_updates(event=event, settings=settings, target=target),
    )
    return {
        "status": "processed",
        "action": "create_booking_task",
        "task_id": str(task_id),
        "task_name": task.get("name"),
        "message_id": event.get("message_id"),
        "list_id": target.list_id,
        "routed_customer": target.customer_name,
        "route_source": target.route_source,
        "customer_task_id": target.customer_task_id,
        "customer_task_custom_id": target.customer_task_custom_id,
        "field_updates": applied_fields,
    }


def build_task_name(*, event: dict[str, Any], settings: WhatsAppSettings, target: BookingTarget) -> str:
    customer_label = (
        target.customer_name
        or event.get("customer_name")
        or event.get("customer_phone")
        or "Unknown"
    ).strip()
    return f"{settings.task_name_prefix} - {customer_label}"


def build_task_description(event: dict[str, Any], target: BookingTarget) -> str:
    received_at = _event_received_at(event)
    return "\n".join(
        [
            "# WhatsApp Booking Intake",
            f"- Received at: {received_at}",
            f"- Route source: {target.route_source or 'Unknown'}",
            f"- Routed customer: {target.customer_name or 'Unknown'}",
            f"- Routed customer task: {target.customer_task_name or target.customer_task_id or 'Unknown'}",
            f"- Routed customer custom id: {target.customer_task_custom_id or 'Unknown'}",
            f"- From: {event.get('customer_phone') or 'Unknown'}",
            f"- Customer: {event.get('customer_name') or 'Unknown'}",
            f"- Message ID: {event.get('message_id') or 'Unknown'}",
            f"- Conversation ID: {event.get('conversation_id') or 'Unknown'}",
            "",
            "## Message",
            event.get("text") or "[no text body]",
            "",
            "## Media",
            _render_media_lines(event),
        ]
    ).strip()


def build_whatsapp_comment(event: dict[str, Any]) -> str:
    received_at = _event_received_at(event)
    return "\n".join(
        [
            "Inbound WhatsApp message",
            f"From: {event.get('customer_phone') or 'Unknown'}",
            f"Customer: {event.get('customer_name') or 'Unknown'}",
            f"Message ID: {event.get('message_id') or 'Unknown'}",
            f"Received at: {received_at}",
            "",
            event.get("text") or "[no text body]",
            "",
            "Media:",
            _render_media_lines(event),
        ]
    ).strip()


def _build_field_updates(
    *,
    event: dict[str, Any],
    settings: WhatsAppSettings,
    target: BookingTarget,
) -> dict[str, str]:
    updates: dict[str, str] = {}
    if event.get("customer_phone"):
        updates[settings.customer_phone_field_name] = str(event["customer_phone"])
    if event.get("customer_name"):
        updates[settings.customer_name_field_name] = str(event["customer_name"])
    if settings.routed_customer_field_name and target.customer_name:
        updates[settings.routed_customer_field_name] = target.customer_name
    if settings.source_channel_value:
        updates[settings.source_channel_field_name] = settings.source_channel_value
    if event.get("conversation_id"):
        updates[settings.conversation_id_field_name] = str(event["conversation_id"])
    if event.get("message_id"):
        updates[settings.last_message_id_field_name] = str(event["message_id"])
    updates[settings.last_message_at_field_name] = _event_received_at(event)
    return updates


def _load_list_field_map(*, clickup: Any, list_id: str) -> dict[str, str]:
    payload = clickup.get_list_custom_fields(list_id)
    fields = payload.get("fields") or []
    field_map: dict[str, str] = {}
    for field in fields:
        name = str(field.get("name") or "").strip()
        field_id = str(field.get("id") or "").strip()
        if name and field_id:
            field_map[name] = field_id
    return field_map


def _apply_field_updates(
    *,
    clickup: Any,
    task_id: str,
    field_map: dict[str, str],
    updates: dict[str, str],
) -> dict[str, Any]:
    applied: list[str] = []
    missing: list[str] = []
    for field_name, value in updates.items():
        field_id = field_map.get(field_name)
        if not field_id:
            missing.append(field_name)
            continue
        clickup.set_task_custom_field_value(task_id, field_id, value)
        applied.append(field_name)
    return {
        "applied": applied,
        "missing": missing,
    }


def _find_existing_task(
    *,
    clickup: Any,
    list_id: str,
    phone_number: str,
    settings: WhatsAppSettings,
) -> dict[str, Any] | None:
    target_phone = normalize_phone_key(phone_number)
    matches: list[dict[str, Any]] = []

    for page in range(settings.task_scan_pages):
        payload = clickup.get_list_tasks(
            list_id,
            archived=False,
            include_closed=False,
            page=page,
        )
        tasks = payload.get("tasks") or []
        for task in tasks:
            current_phone = _task_custom_field_value(task, settings.customer_phone_field_name)
            if normalize_phone_key(current_phone) == target_phone:
                matches.append(task)
        if len(tasks) < 100:
            break

    if not matches:
        return None

    matches.sort(
        key=lambda task: str(task.get("date_updated") or task.get("date_created") or ""),
        reverse=True,
    )
    return matches[0]


def _is_duplicate_message(
    *,
    existing_task: dict[str, Any],
    event: dict[str, Any],
    settings: WhatsAppSettings,
) -> bool:
    last_message_id = _task_custom_field_value(existing_task, settings.last_message_id_field_name)
    current_message_id = (event.get("message_id") or "").strip()
    return bool(last_message_id and current_message_id and str(last_message_id).strip() == current_message_id)


def _task_custom_field_value(task: dict[str, Any], field_name: str) -> Any:
    custom_fields = task.get("custom_fields") or []
    if isinstance(custom_fields, dict):
        field = custom_fields.get(field_name) or {}
        return field.get("value")
    for field in custom_fields:
        if str(field.get("name") or "").strip() == field_name:
            return field.get("value")
    return None


def normalize_phone_key(value: Any) -> str:
    if value is None:
        return ""
    digits = [character for character in str(value) if character.isdigit()]
    return "".join(digits)


def _render_media_lines(event: dict[str, Any]) -> str:
    media = event.get("media") or []
    if not media:
        return "- none"
    return "\n".join(
        f"- {item.get('content_type') or 'unknown'}: {item.get('url')}"
        for item in media
    )


def _render_received_at() -> str:
    return datetime.now(timezone.utc).isoformat()


def _event_received_at(event: dict[str, Any]) -> str:
    received_at = event.get("received_at")
    if received_at:
        return str(received_at)
    return _render_received_at()
