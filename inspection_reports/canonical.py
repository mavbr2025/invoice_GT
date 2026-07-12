from __future__ import annotations

import json
from typing import Any

from inspection_reports.clickup import summarize_task_for_report


CANONICAL_SCHEMA_VERSION = "mtm.inspection-report.v1"
DEFAULT_CANONICAL_PAYLOAD_FIELD_ID = "14cba98e-7dd2-426b-90b6-5c88be5e27e4"

_CHECKPOINT_FIELDS = {
    "overview_360": "360 Overview Result",
    "door": "Door Result",
    "floor": "Floor Result",
    "emergency_exits": "Emergency exits Result",
    "window": "Window Result",
    "seat_appearance": "Seat Appearance / Fixation Result",
    "tire_and_wheel": "Tire and Wheel Result",
    "car_keys": "Car keys in glove box",
    "accessories": "Accessories Result",
    "corrosion": "Corrosion Result",
    "painting": "Painting Result",
    "glass": "Glass Result",
    "exterior_lights": "Exterior Lights Result",
    "mirrors": "Mirrors Result",
    "branding": "Branding Result",
}


class CanonicalPayloadError(ValueError):
    """Raised when the Report Payload custom field is not usable for generation."""


def load_canonical_payload_from_task(
    task: dict[str, Any],
    *,
    field_id: str = DEFAULT_CANONICAL_PAYLOAD_FIELD_ID,
) -> dict[str, Any] | None:
    field = next(
        (
            item
            for item in task.get("custom_fields") or []
            if str(item.get("id") or "") == field_id
        ),
        None,
    )
    if not field or field.get("value") in (None, ""):
        return None

    raw_value = field["value"]
    if isinstance(raw_value, dict):
        payload = raw_value
    elif isinstance(raw_value, str):
        try:
            payload = json.loads(raw_value)
        except json.JSONDecodeError as exc:
            raise CanonicalPayloadError("Report Payload is not valid JSON.") from exc
    else:
        raise CanonicalPayloadError("Report Payload must be a JSON object.")

    if not isinstance(payload, dict):
        raise CanonicalPayloadError("Report Payload must be a JSON object.")
    validate_canonical_payload(payload, task=task)
    return payload


def canonical_request_mode(payload: dict[str, Any]) -> str:
    mode = _required_text(payload.get("request"), "mode", "request.mode").lower()
    if mode not in {"apply", "dry_run"}:
        raise CanonicalPayloadError("request.mode must be apply or dry_run.")
    return mode


def report_summary_from_canonical_payload(
    payload: dict[str, Any],
    *,
    task: dict[str, Any],
) -> dict[str, Any]:
    validate_canonical_payload(payload, task=task)

    vehicle = _required_object(payload, "vehicle")
    inspection = _required_object(payload, "inspection")
    routing = _optional_object(payload, "routing")
    checkpoints = _required_object(payload, "checkpoints")
    source_folder_url = _photo_source_url(payload)

    summary = summarize_task_for_report(task, report_field_names=())
    report_fields = {
        "VIN number": _required_text(vehicle, "vin", "vehicle.vin").upper(),
        "Brand": _text_or_empty(vehicle.get("brand")),
        "Model": _text_or_empty(vehicle.get("model")),
        "Line": _text_or_empty(vehicle.get("line")),
        "Color": _text_or_empty(vehicle.get("color")),
        "Motor": _text_or_empty(vehicle.get("motor")),
        "Number of seats": _text_or_empty(vehicle.get("seats")),
        "Inspection Date": _required_text(inspection, "date", "inspection.date"),
        "Inspector Name": _text_or_empty(inspection.get("inspector")),
        "Inspection AI Exec Summary": _text_or_empty(inspection.get("summary")),
        "Inspection Result Summary": _text_or_empty(inspection.get("summary")),
        "Destination Country": _text_or_empty(routing.get("destination_country")),
        "Port of Loading": _text_or_empty(routing.get("port_of_loading")),
        "OneDrive Pictures": source_folder_url,
    }
    for checkpoint_key, field_name in _CHECKPOINT_FIELDS.items():
        checkpoint = _required_object(checkpoints, checkpoint_key, parent="checkpoints")
        report_fields[field_name] = _required_text(
            checkpoint,
            "result",
            f"checkpoints.{checkpoint_key}.result",
        )

    overview_comment = _optional_object(checkpoints, "overview_360").get("comment")
    if overview_comment not in (None, ""):
        report_fields["360 Overview Comment"] = _text_or_empty(overview_comment)

    custom_fields = dict(summary.get("custom_fields") or {})
    source_field = dict(custom_fields.get("OneDrive Pictures") or {})
    source_field["type"] = source_field.get("type") or "url"
    source_field["value"] = source_folder_url
    custom_fields["OneDrive Pictures"] = source_field

    return {
        **summary,
        "custom_fields": custom_fields,
        "report_fields": {name: value for name, value in report_fields.items() if value},
    }


def validate_canonical_payload(payload: dict[str, Any], *, task: dict[str, Any]) -> None:
    if payload.get("schema_version") != CANONICAL_SCHEMA_VERSION:
        raise CanonicalPayloadError(
            f"schema_version must be {CANONICAL_SCHEMA_VERSION}."
        )

    request = _required_object(payload, "request")
    _required_text(request, "request_id", "request.request_id")
    _required_text(request, "source_revision", "request.source_revision")
    canonical_request_mode(payload)

    document = _required_object(payload, "document")
    if _required_text(document, "profile", "document.profile") != "magna-inspection-v1":
        raise CanonicalPayloadError("document.profile must be magna-inspection-v1.")
    if _required_text(document, "title", "document.title") != "Inspection Report":
        raise CanonicalPayloadError("document.title must be Inspection Report.")

    vehicle = _required_object(payload, "vehicle")
    vin = _required_text(vehicle, "vin", "vehicle.vin").upper()
    if _required_text(document, "file_name", "document.file_name") != f"{vin}.pdf":
        raise CanonicalPayloadError("document.file_name must be exactly <VIN>.pdf.")

    task_payload = _required_object(payload, "task")
    _required_text(task_payload, "workspace_id", "task.workspace_id")
    expected_task_id = str(task.get("id") or "").strip()
    if _required_text(task_payload, "task_id", "task.task_id") != expected_task_id:
        raise CanonicalPayloadError("task.task_id does not match the ClickUp task.")

    inspection = _required_object(payload, "inspection")
    inspection_date = _required_text(inspection, "date", "inspection.date")
    if len(inspection_date) != 10 or inspection_date[4] != "-" or inspection_date[7] != "-":
        raise CanonicalPayloadError("inspection.date must use YYYY-MM-DD.")

    checkpoints = _required_object(payload, "checkpoints")
    for checkpoint_key in _CHECKPOINT_FIELDS:
        checkpoint = _required_object(checkpoints, checkpoint_key, parent="checkpoints")
        _required_text(checkpoint, "result", f"checkpoints.{checkpoint_key}.result")

    source_url = _photo_source_url(payload)
    photos = _required_object(payload, "photos")
    expected_folder = _required_text(photos, "expected_folder_name", "photos.expected_folder_name")
    if expected_folder.upper() != vin:
        raise CanonicalPayloadError("photos.expected_folder_name must match vehicle.vin.")
    if not source_url.startswith("https://"):
        raise CanonicalPayloadError("photos must contain an HTTPS SharePoint reference.")


def _photo_source_url(payload: dict[str, Any]) -> str:
    photos = _required_object(payload, "photos")
    source_type = _required_text(photos, "source_type", "photos.source_type")
    if source_type == "share_url":
        return _required_text(photos, "share_url", "photos.share_url")
    if source_type == "graph_drive_item":
        return _required_text(photos, "web_url", "photos.web_url")
    raise CanonicalPayloadError("photos.source_type must be share_url or graph_drive_item.")


def _required_object(
    container: dict[str, Any],
    key: str,
    parent: str | None = None,
) -> dict[str, Any]:
    value = container.get(key) if isinstance(container, dict) else None
    if not isinstance(value, dict):
        prefix = f"{parent}." if parent else ""
        raise CanonicalPayloadError(f"{prefix}{key} must be an object.")
    return value


def _optional_object(container: dict[str, Any], key: str) -> dict[str, Any]:
    value = container.get(key) if isinstance(container, dict) else None
    return value if isinstance(value, dict) else {}


def _required_text(container: dict[str, Any], key: str, label: str) -> str:
    value = container.get(key) if isinstance(container, dict) else None
    text = _text_or_empty(value)
    if not text:
        raise CanonicalPayloadError(f"{label} is required.")
    return text


def _text_or_empty(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
