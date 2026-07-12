import json
import hashlib
import hmac
from types import SimpleNamespace

from inspection_app import handler
from inspection_reports.workflow import ReportRunResult


class _Context:
    invoked_function_arn = "arn:aws:lambda:us-east-1:525753067477:function:mtm-inspection-app"


def test_webhook_rejects_invalid_token(monkeypatch) -> None:
    monkeypatch.setenv("INSPECTION_APP_WEBHOOK_TOKEN", "expected-token")

    response = handler.lambda_handler(
        {
            "rawPath": "/clickup/webhooks/inspection-reports/task-1",
            "headers": {"authorization": "Bearer wrong-token"},
            "body": "{}",
        },
        _Context(),
    )

    assert response["statusCode"] == 401


def test_webhook_accepts_task_id_from_path_and_invokes_worker(monkeypatch) -> None:
    monkeypatch.setenv("INSPECTION_APP_WEBHOOK_TOKEN", "expected-token")
    invoked: list[dict] = []
    monkeypatch.setattr(
        handler,
        "_invoke_async",
        lambda *, worker_name, job: invoked.append({"worker_name": worker_name, "job": job}),
    )

    response = handler.lambda_handler(
        {
            "rawPath": "/clickup/webhooks/inspection-reports/MTLXMGN-301",
            "headers": {"Authorization": "Bearer expected-token"},
            "body": json.dumps({"event": "automation"}),
        },
        _Context(),
    )

    assert response["statusCode"] == 202
    assert json.loads(response["body"])["task_id"] == "MTLXMGN-301"
    assert invoked[0]["worker_name"] == _Context.invoked_function_arn
    assert invoked[0]["job"]["task_id"] == "MTLXMGN-301"


def test_webhook_accepts_a_valid_clickup_api_signature(monkeypatch) -> None:
    raw_body = '{"task_id":"MTLXMGN-301","event":"taskStatusUpdated"}'
    secret = "clickup-webhook-secret"
    signature = hmac.new(secret.encode("utf-8"), raw_body.encode("utf-8"), hashlib.sha256).hexdigest()
    monkeypatch.delenv("INSPECTION_APP_WEBHOOK_TOKEN", raising=False)
    monkeypatch.setenv("CLICKUP_API_WEBHOOK_SECRET", secret)
    monkeypatch.setattr(handler, "_invoke_async", lambda **_kwargs: None)

    response = handler.lambda_handler(
        {
            "rawPath": "/clickup/webhooks/inspection-reports",
            "headers": {"X-Signature": signature},
            "body": raw_body,
        },
        _Context(),
    )

    assert response["statusCode"] == 202


def test_webhook_normalizes_a_double_slash_function_url_path(monkeypatch) -> None:
    monkeypatch.setenv("INSPECTION_APP_WEBHOOK_TOKEN", "expected-token")
    monkeypatch.setattr(handler, "_invoke_async", lambda **_kwargs: None)

    response = handler.lambda_handler(
        {
            "rawPath": "//clickup/webhooks/inspection-reports/task-1",
            "headers": {"Authorization": "Bearer expected-token"},
            "body": "{}",
        },
        _Context(),
    )

    assert response["statusCode"] == 202


def test_readiness_requires_the_inspection_runtime_configuration(monkeypatch) -> None:
    monkeypatch.setenv("INSPECTION_APP_WEBHOOK_TOKEN", "expected-token")
    monkeypatch.setenv("CLICKUP_ACCESS_TOKEN", "clickup-token")
    monkeypatch.setattr(
        handler.InspectionReportSettings,
        "from_env",
        lambda: SimpleNamespace(
            clickup_list_id="901707774763",
            report_link_field_ids=("report-field",),
            picture_folder_field_ids=("pictures-field",),
            report_attachment_field_ids=("attachment-field",),
        ),
    )
    monkeypatch.setattr(handler.GraphSettings, "from_env", lambda: object())

    response = handler.lambda_handler(
        {
            "rawPath": "/clickup/webhooks/inspection-reports/readiness",
            "requestContext": {"http": {"method": "GET"}},
            "headers": {"Authorization": "Bearer expected-token"},
        },
        _Context(),
    )

    assert response["statusCode"] == 200
    assert json.loads(response["body"])["status"] == "ready"


def test_worker_is_non_mutating_until_apply_is_enabled(monkeypatch) -> None:
    task = {
        "id": "task-1",
        "list": {"id": "901707774763"},
        "status": {"status": "Ready for Report"},
    }
    fake_clickup = SimpleNamespace(
        settings=SimpleNamespace(default_workspace_id="8451352"),
        get_task=lambda *_args, **_kwargs: task,
    )
    settings = SimpleNamespace(
        custom_task_ids=True,
        clickup_team_id="8451352",
        clickup_list_id="901707774763",
    )
    monkeypatch.setenv("INSPECTION_APP_APPLY", "false")
    monkeypatch.setattr(handler.ClickUpSettings, "from_env", lambda: object())
    monkeypatch.setattr(handler.InspectionReportSettings, "from_env", lambda: settings)
    monkeypatch.setattr(handler, "ClickUpClient", lambda _settings: fake_clickup)

    result = handler.lambda_handler(
        {"job_type": "inspection_report", "request_id": "req-1", "task_id": "task-1"},
        _Context(),
    )

    assert result == {
        "status": "dry_run",
        "task_id": "task-1",
        "request_id": "req-1",
        "task_status": "Ready for Report",
    }


def test_worker_dry_runs_a_canonical_payload_when_explicitly_requested(monkeypatch) -> None:
    payload = {
        "schema_version": "mtm.inspection-report.v1",
        "request": {
            "request_id": "payload-run",
            "mode": "dry_run",
            "source_revision": "2026-07-11T00:00:00Z",
        },
        "document": {
            "profile": "magna-inspection-v1",
            "title": "Inspection Report",
            "file_name": "VIN123.pdf",
        },
        "task": {"workspace_id": "8451352", "task_id": "task-1"},
        "vehicle": {"vin": "VIN123"},
        "inspection": {"date": "2026-07-03"},
        "checkpoints": {
            "overview_360": {"result": "Pass"}, "door": {"result": "Pass"},
            "floor": {"result": "Pass"}, "emergency_exits": {"result": "N/A"},
            "window": {"result": "Pass"}, "seat_appearance": {"result": "Pass"},
            "tire_and_wheel": {"result": "Pass"}, "car_keys": {"result": "Yes"},
            "accessories": {"result": "Pass"}, "corrosion": {"result": "Pass"},
            "painting": {"result": "Pass"}, "glass": {"result": "Pass"},
            "exterior_lights": {"result": "Pass"}, "mirrors": {"result": "Pass"},
            "branding": {"result": "Pass"},
        },
        "photos": {
            "source_type": "share_url",
            "share_url": "https://example.com/:f:/s/MTM/VIN123",
            "expected_folder_name": "VIN123",
        },
    }
    task = {
        "id": "task-1",
        "list": {"id": "901707774763"},
        "status": {"status": "inspected"},
        "custom_fields": [
            {
                "id": "14cba98e-7dd2-426b-90b6-5c88be5e27e4",
                "name": "Report Payload",
                "type": "text",
                "value": json.dumps(payload),
            }
        ],
    }
    fake_clickup = SimpleNamespace(
        settings=SimpleNamespace(default_workspace_id="8451352"),
        get_task=lambda *_args, **_kwargs: task,
    )
    settings = SimpleNamespace(
        custom_task_ids=True,
        clickup_team_id="8451352",
        clickup_list_id="901707774763",
    )
    calls: list[dict] = []

    class FakeWorkflow:
        def __init__(self, **_kwargs) -> None:
            pass

        def run_canonical_payload(self, canonical_payload, *, task, dry_run):
            calls.append({"payload": canonical_payload, "task": task, "dry_run": dry_run})
            return ReportRunResult(
                task_id="task-1",
                task_name="VIN123",
                status="dry_run",
                local_pdf_path="/tmp/VIN123.pdf",
                matched_image_count=12,
            )

    monkeypatch.setenv("INSPECTION_APP_APPLY", "true")
    monkeypatch.setattr(handler.ClickUpSettings, "from_env", lambda: object())
    monkeypatch.setattr(handler.InspectionReportSettings, "from_env", lambda: settings)
    monkeypatch.setattr(handler.GraphSettings, "from_env", lambda: object())
    monkeypatch.setattr(handler, "ClickUpClient", lambda _settings: fake_clickup)
    monkeypatch.setattr(handler, "SharePointGraphClient", lambda _settings: object())
    monkeypatch.setattr(handler, "InspectionReportWorkflow", FakeWorkflow)

    result = handler.lambda_handler(
        {
            "job_type": "inspection_report",
            "request_id": "req-1",
            "task_id": "task-1",
            "mode_override": "dry_run",
            "ignore_trigger_status": True,
        },
        _Context(),
    )

    assert result["status"] == "dry_run"
    assert result["canonical_payload_used"] is True
    assert result["run_mode"] == "dry_run"
    assert calls[0]["dry_run"] is True
