from whatsapp_integration.config import RouteRule, WhatsAppSettings
from whatsapp_integration.router import route_customer_message


def make_settings(*, route_rules=(), operations_list_id="ops-list", booking_list_id="booking-list") -> WhatsAppSettings:
    return WhatsAppSettings(
        twilio_auth_token="auth-token",
        twilio_validate_signature=True,
        twilio_validate_url=None,
        booking_list_id=booking_list_id,
        operations_list_id=operations_list_id,
        booking_status_new="New WhatsApp Lead",
        task_name_prefix="Booking Intake",
        task_scan_pages=3,
        customer_phone_field_name="Customer Phone",
        customer_name_field_name="Customer Name",
        source_channel_field_name="Source Channel",
        source_channel_value="WhatsApp",
        conversation_id_field_name="Conversation ID",
        last_message_at_field_name="Last WhatsApp Message At",
        last_message_id_field_name="Last WhatsApp Message ID",
        routed_customer_field_name="Routed Customer",
        customer_directory_list_id=None,
        directory_task_scan_pages=3,
        directory_phone_field_names=("Contact Phone 1",),
        directory_target_list_field_names=("WhatsApp Intake List ID",),
        directory_target_list_field_ids=(),
        directory_customer_name_field_names=("Business Central Legal Name",),
        directory_allowed_statuses=("current customer",),
        route_rules=tuple(route_rules),
    )


def make_event(phone: str) -> dict:
    return {
        "channel": "whatsapp",
        "customer_phone": phone,
    }


def test_route_customer_message_prefers_exact_phone_rule() -> None:
    settings = make_settings(
        route_rules=[
            RouteRule(
                match_type="exact_phone",
                pattern="+5215512345678",
                list_id="customer-list",
                customer_name="SMARTSPACE",
            )
        ]
    )

    decision = route_customer_message(make_event("+5215512345678"), settings)

    assert decision.route == "booking_intake"
    assert decision.list_id == "customer-list"
    assert decision.customer_name == "SMARTSPACE"
    assert decision.source == "env_rule"
    assert decision.reason == "matched_env_rule"


def test_route_customer_message_supports_prefix_rule() -> None:
    settings = make_settings(
        route_rules=[
            RouteRule(
                match_type="phone_prefix",
                pattern="+502",
                list_id="gt-list",
                customer_name="GUATEMALA OPS",
            )
        ]
    )

    decision = route_customer_message(make_event("+50255112233"), settings)

    assert decision.route == "booking_intake"
    assert decision.list_id == "gt-list"
    assert decision.customer_name == "GUATEMALA OPS"
    assert decision.source == "env_rule"
    assert decision.reason == "matched_env_rule"


def test_route_customer_message_falls_back_to_operations_list() -> None:
    settings = make_settings(route_rules=[])

    decision = route_customer_message(make_event("+5215512345678"), settings)

    assert decision.route == "booking_intake"
    assert decision.list_id == "ops-list"
    assert decision.customer_name is None
    assert decision.source == "fallback"
    assert decision.reason == "operations_fallback"


def test_route_customer_message_fails_closed_without_operations_fallback() -> None:
    settings = make_settings(route_rules=[], operations_list_id=None, booking_list_id="booking-list")

    decision = route_customer_message(make_event("+5215512345678"), settings)

    assert decision.route == "ignored"
    assert decision.list_id is None
    assert decision.source == "unrouted"
    assert decision.reason == "missing_operations_fallback"
