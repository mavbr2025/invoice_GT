from __future__ import annotations

from datetime import datetime, timezone
import base64
import hashlib
import hmac
from typing import Any, Mapping


def normalize_twilio_inbound(form_data: Mapping[str, Any]) -> dict[str, Any]:
    customer_phone = _strip_whatsapp_prefix(_clean_string(form_data.get("From")))
    to_phone = _strip_whatsapp_prefix(_clean_string(form_data.get("To")))
    profile_name = _clean_string(form_data.get("ProfileName"))
    message_id = _clean_string(form_data.get("MessageSid")) or _clean_string(form_data.get("SmsSid"))
    customer_wa_id = _clean_string(form_data.get("WaId"))
    body = _clean_string(form_data.get("Body"))
    media = _extract_media(form_data)

    conversation_id = customer_phone or customer_wa_id
    if conversation_id:
        conversation_id = f"whatsapp:{conversation_id}"

    return {
        "channel": "whatsapp",
        "provider": "twilio",
        "customer_phone": customer_phone,
        "customer_name": profile_name,
        "customer_wa_id": customer_wa_id,
        "message_id": message_id,
        "conversation_id": conversation_id,
        "received_at": datetime.now(timezone.utc).isoformat(),
        "text": body,
        "to_phone": to_phone,
        "media": media,
        "raw_payload": dict(form_data),
    }


def validate_twilio_request_signature(
    *,
    url: str,
    params: Mapping[str, Any],
    provided_signature: str | None,
    auth_token: str,
) -> bool:
    if not provided_signature or not auth_token:
        return False

    expected = _build_twilio_signature(url=url, params=params, auth_token=auth_token)
    return hmac.compare_digest(expected, provided_signature.strip())


def _build_twilio_signature(*, url: str, params: Mapping[str, Any], auth_token: str) -> str:
    pieces = [url]
    for key in sorted(params):
        value = params[key]
        if isinstance(value, (list, tuple)):
            values = [str(item) for item in value]
        else:
            values = [str(value)]
        for item in values:
            pieces.append(key)
            pieces.append(item)

    payload = "".join(pieces).encode("utf-8")
    digest = hmac.new(
        auth_token.encode("utf-8"),
        payload,
        hashlib.sha1,
    ).digest()
    return base64.b64encode(digest).decode("ascii")


def _extract_media(form_data: Mapping[str, Any]) -> list[dict[str, str | None]]:
    media_count = _parse_int(form_data.get("NumMedia"))
    if media_count == 0:
        return []

    media: list[dict[str, str | None]] = []
    upper_bound = max(media_count, 10)
    for index in range(upper_bound):
        url = _clean_string(form_data.get(f"MediaUrl{index}"))
        content_type = _clean_string(form_data.get(f"MediaContentType{index}"))
        if not url and index >= media_count:
            break
        if not url:
            continue
        media.append(
            {
                "url": url,
                "content_type": content_type,
            }
        )
    return media


def _parse_int(value: Any) -> int:
    try:
        return int(str(value).strip())
    except Exception:
        return 0


def _clean_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _strip_whatsapp_prefix(value: str | None) -> str | None:
    if not value:
        return value
    if value.lower().startswith("whatsapp:"):
        return value[len("whatsapp:") :].strip() or None
    return value
