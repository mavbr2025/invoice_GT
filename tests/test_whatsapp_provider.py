from whatsapp_integration.provider import (
    normalize_twilio_inbound,
    validate_twilio_request_signature,
)


def test_normalize_twilio_inbound_message() -> None:
    payload = normalize_twilio_inbound(
        {
            "From": "whatsapp:+5215512345678",
            "To": "whatsapp:+14155238886",
            "ProfileName": "Mario",
            "MessageSid": "SM123",
            "WaId": "5215512345678",
            "Body": "I need a transfer tomorrow at 8am",
            "NumMedia": "1",
            "MediaUrl0": "https://example.com/file.jpg",
            "MediaContentType0": "image/jpeg",
        }
    )

    assert payload["channel"] == "whatsapp"
    assert payload["provider"] == "twilio"
    assert payload["customer_phone"] == "+5215512345678"
    assert payload["customer_name"] == "Mario"
    assert payload["message_id"] == "SM123"
    assert payload["conversation_id"] == "whatsapp:+5215512345678"
    assert payload["text"] == "I need a transfer tomorrow at 8am"
    assert payload["received_at"]
    assert payload["media"] == [
        {
            "url": "https://example.com/file.jpg",
            "content_type": "image/jpeg",
        }
    ]


def test_validate_twilio_request_signature() -> None:
    params = {
        "Body": "hello",
        "From": "whatsapp:+5215512345678",
        "MessageSid": "SM123",
    }

    assert validate_twilio_request_signature(
        url="https://example.com/whatsapp/webhooks/inbound",
        params=params,
        provided_signature="PoLCbdkWHz1fEiyaY6oABfakRqQ=",
        auth_token="auth-token",
    )


def test_validate_twilio_request_signature_rejects_invalid_signature() -> None:
    params = {
        "Body": "hello",
        "From": "whatsapp:+5215512345678",
        "MessageSid": "SM123",
    }

    assert not validate_twilio_request_signature(
        url="https://example.com/whatsapp/webhooks/inbound",
        params=params,
        provided_signature="invalid",
        auth_token="auth-token",
    )
