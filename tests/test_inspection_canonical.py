import json

import pytest

from inspection_reports.canonical import (
    CanonicalPayloadError,
    load_canonical_payload_from_task,
    report_summary_from_canonical_payload,
)


def _payload(*, file_name: str = "LGDCH91C5VA702240.pdf") -> dict:
    return {
        "schema_version": "mtm.inspection-report.v1",
        "request": {
            "request_id": "dry-run-1",
            "mode": "dry_run",
            "source_revision": "2026-07-11T00:00:00Z",
        },
        "document": {
            "profile": "magna-inspection-v1",
            "title": "Inspection Report",
            "file_name": file_name,
            "max_photos_per_folder": 4,
        },
        "task": {"workspace_id": "8451352", "task_id": "task-1"},
        "vehicle": {
            "vin": "LGDCH91C5VA702240",
            "brand": "Dongfeng",
            "model": "DF-350",
            "line": "DF-350",
            "color": "White",
            "motor": "41061004",
            "seats": 3,
        },
        "inspection": {
            "date": "2026-07-03",
            "inspector": "zhengbo",
            "summary": "Inspection complete.",
        },
        "routing": {"destination_country": "Guatemala", "port_of_loading": "Shanghai, China"},
        "checkpoints": {
            "overview_360": {"result": "Pass", "comment": "No issues"},
            "door": {"result": "Pass"},
            "floor": {"result": "Pass"},
            "emergency_exits": {"result": "N/A"},
            "window": {"result": "Pass"},
            "seat_appearance": {"result": "Pass"},
            "tire_and_wheel": {"result": "Pass"},
            "car_keys": {"result": "Yes (2)"},
            "accessories": {"result": "Pass"},
            "corrosion": {"result": "Pass"},
            "painting": {"result": "Pass"},
            "glass": {"result": "Pass"},
            "exterior_lights": {"result": "Pass"},
            "mirrors": {"result": "Pass"},
            "branding": {"result": "Pass"},
        },
        "photos": {
            "source_type": "share_url",
            "share_url": "https://mtmlogixmx.sharepoint.com/:f:/s/MTMLogixTopManagement/example",
            "expected_folder_name": "LGDCH91C5VA702240",
        },
    }


def _task(payload: dict) -> dict:
    return {
        "id": "task-1",
        "name": "Vehicle inspection",
        "status": {"status": "inspected"},
        "custom_fields": [
            {
                "id": "14cba98e-7dd2-426b-90b6-5c88be5e27e4",
                "name": "Report Payload",
                "type": "text",
                "value": json.dumps(payload),
            },
            {
                "id": "pictures-field",
                "name": "OneDrive Pictures",
                "type": "url",
                "value": "https://old.example/photos",
            },
        ],
    }


def test_canonical_payload_maps_to_report_fields_and_photo_source() -> None:
    payload = _payload()
    task = _task(payload)

    loaded = load_canonical_payload_from_task(task)
    summary = report_summary_from_canonical_payload(loaded, task=task)

    assert summary["report_fields"]["VIN number"] == "LGDCH91C5VA702240"
    assert summary["report_fields"]["Number of seats"] == "3"
    assert summary["report_fields"]["360 Overview Comment"] == "No issues"
    assert summary["report_fields"]["Inspection AI Exec Summary"] == "Inspection complete."
    assert summary["custom_fields"]["OneDrive Pictures"]["value"] == payload["photos"]["share_url"]


def test_canonical_payload_rejects_a_non_vin_file_name() -> None:
    payload = _payload(file_name="incorrect.pdf")

    with pytest.raises(CanonicalPayloadError, match="file_name"):
        load_canonical_payload_from_task(_task(payload))
