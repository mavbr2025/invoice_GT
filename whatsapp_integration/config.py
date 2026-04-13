from __future__ import annotations

import os
import json
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class WhatsAppSettings:
    twilio_auth_token: str | None
    twilio_validate_signature: bool
    twilio_validate_url: str | None
    booking_list_id: str | None
    operations_list_id: str | None
    booking_status_new: str | None
    task_name_prefix: str
    task_scan_pages: int
    customer_phone_field_name: str
    customer_name_field_name: str
    source_channel_field_name: str
    source_channel_value: str
    conversation_id_field_name: str
    last_message_at_field_name: str
    last_message_id_field_name: str
    routed_customer_field_name: str | None
    customer_directory_list_id: str | None
    directory_task_scan_pages: int
    directory_phone_field_names: tuple[str, ...]
    directory_target_list_field_names: tuple[str, ...]
    directory_target_list_field_ids: tuple[str, ...]
    directory_customer_name_field_names: tuple[str, ...]
    directory_allowed_statuses: tuple[str, ...]
    route_rules: tuple["RouteRule", ...]

    @classmethod
    def from_env(
        cls,
        *,
        require_booking: bool = False,
        require_twilio_auth: bool = False,
    ) -> "WhatsAppSettings":
        twilio_auth_token = os.getenv("TWILIO_AUTH_TOKEN", "").strip() or None
        booking_list_id = os.getenv("WHATSAPP_CLICKUP_BOOKING_LIST_ID", "").strip() or None
        operations_list_id = os.getenv("WHATSAPP_CLICKUP_OPERATIONS_LIST_ID", "").strip() or None
        booking_status_new = os.getenv("WHATSAPP_CLICKUP_BOOKING_STATUS_NEW", "").strip() or None

        missing: list[str] = []
        if require_twilio_auth and not twilio_auth_token:
            missing.append("TWILIO_AUTH_TOKEN")
        if missing:
            raise ValueError(
                "Missing required WhatsApp environment variables: "
                + ", ".join(missing)
                + ". Update .env before using the WhatsApp integration."
            )

        return cls(
            twilio_auth_token=twilio_auth_token,
            twilio_validate_signature=_env_bool(
                "TWILIO_VALIDATE_SIGNATURE",
                default=True,
            ),
            twilio_validate_url=os.getenv("TWILIO_VALIDATE_URL", "").strip() or None,
            booking_list_id=booking_list_id,
            operations_list_id=operations_list_id,
            booking_status_new=booking_status_new,
            task_name_prefix=os.getenv(
                "WHATSAPP_CLICKUP_TASK_NAME_PREFIX",
                "Booking Intake",
            ).strip()
            or "Booking Intake",
            task_scan_pages=max(1, int(os.getenv("WHATSAPP_CLICKUP_TASK_SCAN_PAGES", "3"))),
            customer_phone_field_name=os.getenv(
                "WHATSAPP_CLICKUP_CUSTOMER_PHONE_FIELD_NAME",
                "Customer Phone",
            ).strip()
            or "Customer Phone",
            customer_name_field_name=os.getenv(
                "WHATSAPP_CLICKUP_CUSTOMER_NAME_FIELD_NAME",
                "Customer Name",
            ).strip()
            or "Customer Name",
            source_channel_field_name=os.getenv(
                "WHATSAPP_CLICKUP_SOURCE_CHANNEL_FIELD_NAME",
                "Source Channel",
            ).strip()
            or "Source Channel",
            source_channel_value=os.getenv(
                "WHATSAPP_CLICKUP_SOURCE_CHANNEL_VALUE",
                "WhatsApp",
            ).strip()
            or "WhatsApp",
            conversation_id_field_name=os.getenv(
                "WHATSAPP_CLICKUP_CONVERSATION_ID_FIELD_NAME",
                "Conversation ID",
            ).strip()
            or "Conversation ID",
            last_message_at_field_name=os.getenv(
                "WHATSAPP_CLICKUP_LAST_MESSAGE_AT_FIELD_NAME",
                "Last WhatsApp Message At",
            ).strip()
            or "Last WhatsApp Message At",
            last_message_id_field_name=os.getenv(
                "WHATSAPP_CLICKUP_LAST_MESSAGE_ID_FIELD_NAME",
                "Last WhatsApp Message ID",
            ).strip()
            or "Last WhatsApp Message ID",
            routed_customer_field_name=os.getenv(
                "WHATSAPP_CLICKUP_ROUTED_CUSTOMER_FIELD_NAME",
                "",
            ).strip()
            or None,
            customer_directory_list_id=os.getenv(
                "WHATSAPP_CLICKUP_CUSTOMER_DIRECTORY_LIST_ID",
                "",
            ).strip()
            or None,
            directory_task_scan_pages=max(
                1,
                int(os.getenv("WHATSAPP_CLICKUP_DIRECTORY_TASK_SCAN_PAGES", "3")),
            ),
            directory_phone_field_names=_csv_env(
                "WHATSAPP_CLICKUP_DIRECTORY_PHONE_FIELD_NAMES",
                default=(
                    "Contact Phone 1",
                    "Contact Phone Number",
                    "Phone",
                    "Contact Phone 2",
                    "Contact Phone 3",
                    "Contact Phone 4",
                    "Contact Phone 5",
                    "Contact Phone 6",
                    "Customer Phone",
                ),
            ),
            directory_target_list_field_names=_csv_env(
                "WHATSAPP_CLICKUP_DIRECTORY_TARGET_LIST_FIELD_NAMES",
                default=(
                    "WhatsApp Intake List ID",
                    "Operations List ID",
                    "Booking Intake List ID",
                    "Shipment Management EndPoint",
                ),
            ),
            directory_target_list_field_ids=_csv_env(
                "WHATSAPP_CLICKUP_DIRECTORY_TARGET_LIST_FIELD_IDS",
                default=(),
            ),
            directory_customer_name_field_names=_csv_env(
                "WHATSAPP_CLICKUP_DIRECTORY_CUSTOMER_NAME_FIELD_NAMES",
                default=(
                    "Business Central Legal Name",
                    "Clientes/",
                    "Customer Name",
                ),
            ),
            directory_allowed_statuses=_normalized_csv_env(
                "WHATSAPP_CLICKUP_DIRECTORY_ALLOWED_STATUSES",
                default=(),
            ),
            route_rules=_load_route_rules(),
        )


@dataclass(frozen=True)
class RouteRule:
    match_type: str
    pattern: str
    list_id: str
    customer_name: str | None = None


def _env_bool(name: str, *, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _csv_env(name: str, *, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.getenv(name, "")
    values = tuple(item.strip() for item in raw.split(",") if item.strip())
    return values or default


def _normalized_csv_env(name: str, *, default: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(" ".join(item.lower().split()) for item in _csv_env(name, default=default))


def _load_route_rules() -> tuple[RouteRule, ...]:
    raw = os.getenv("WHATSAPP_CLICKUP_ROUTE_RULES_JSON", "").strip()
    if not raw:
        return ()

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "WHATSAPP_CLICKUP_ROUTE_RULES_JSON must be valid JSON."
        ) from exc

    if not isinstance(payload, list):
        raise ValueError("WHATSAPP_CLICKUP_ROUTE_RULES_JSON must decode to a list.")

    rules: list[RouteRule] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ValueError(
                f"WHATSAPP_CLICKUP_ROUTE_RULES_JSON[{index}] must be an object."
            )
        match_type = str(item.get("match_type") or "").strip().lower()
        pattern = str(item.get("pattern") or item.get("phone") or item.get("phone_prefix") or "").strip()
        list_id = str(item.get("list_id") or "").strip()
        customer_name = str(item.get("customer_name") or "").strip() or None
        if match_type not in {"exact_phone", "phone_prefix"}:
            raise ValueError(
                f"WHATSAPP_CLICKUP_ROUTE_RULES_JSON[{index}].match_type must be exact_phone or phone_prefix."
            )
        if not pattern or not list_id:
            raise ValueError(
                f"WHATSAPP_CLICKUP_ROUTE_RULES_JSON[{index}] must include pattern and list_id."
            )
        rules.append(
            RouteRule(
                match_type=match_type,
                pattern=pattern,
                list_id=list_id,
                customer_name=customer_name,
            )
        )
    return tuple(rules)
