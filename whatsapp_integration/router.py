from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from whatsapp_integration.booking_intake import normalize_phone_key
from whatsapp_integration.config import RouteRule, WhatsAppSettings
from whatsapp_integration.customer_directory import find_customer_directory_match


@dataclass(frozen=True)
class RouteDecision:
    route: str
    list_id: str | None
    customer_name: str | None
    matched_rule: RouteRule | None
    source: str
    customer_task_id: str | None
    customer_task_name: str | None
    customer_task_custom_id: str | None
    reason: str | None = None


def route_customer_message(
    event: dict[str, Any],
    settings: WhatsAppSettings,
    *,
    clickup: Any | None = None,
) -> RouteDecision:
    if event.get("channel") == "whatsapp":
        phone = normalize_phone_key(event.get("customer_phone"))
        for rule in settings.route_rules:
            if _matches_rule(phone=phone, rule=rule):
                return RouteDecision(
                    route="booking_intake",
                    list_id=rule.list_id,
                    customer_name=rule.customer_name,
                    matched_rule=rule,
                    source="env_rule",
                    customer_task_id=None,
                    customer_task_name=None,
                    customer_task_custom_id=None,
                    reason="matched_env_rule",
                )
        if clickup and settings.customer_directory_list_id:
            match = find_customer_directory_match(
                clickup=clickup,
                phone_number=phone,
                settings=settings,
            )
            if match:
                return RouteDecision(
                    route="booking_intake",
                    list_id=match.target_list_id or settings.operations_list_id or settings.booking_list_id,
                    customer_name=match.customer_name,
                    matched_rule=None,
                    source="customer_directory",
                    customer_task_id=match.task_id,
                    customer_task_name=match.task_name,
                    customer_task_custom_id=match.custom_id,
                    reason="matched_customer_directory",
                )
        fallback_list_id = settings.operations_list_id
        if not fallback_list_id:
            return RouteDecision(
                route="ignored",
                list_id=None,
                customer_name=None,
                matched_rule=None,
                source="unrouted",
                customer_task_id=None,
                customer_task_name=None,
                customer_task_custom_id=None,
                reason="missing_operations_fallback",
            )
        return RouteDecision(
            route="booking_intake",
            list_id=fallback_list_id,
            customer_name=None,
            matched_rule=None,
            source="fallback",
            customer_task_id=None,
            customer_task_name=None,
            customer_task_custom_id=None,
            reason="operations_fallback",
        )
    return RouteDecision(
        route="ignored",
        list_id=None,
        customer_name=None,
        matched_rule=None,
        source="ignored",
        customer_task_id=None,
        customer_task_name=None,
        customer_task_custom_id=None,
        reason="unsupported_channel",
    )


def _matches_rule(*, phone: str, rule: RouteRule) -> bool:
    pattern = normalize_phone_key(rule.pattern)
    if not phone or not pattern:
        return False
    if rule.match_type == "exact_phone":
        return phone == pattern
    if rule.match_type == "phone_prefix":
        return phone.startswith(pattern)
    return False
