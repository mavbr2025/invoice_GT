from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from webhook_bridge.main import app


class FakeClickUp:
    def __init__(self, _settings) -> None:
        self.settings = SimpleNamespace(default_workspace_id="8451352")

    def get_task(self, task_id: str, **_kwargs):
        return {
            "id": task_id,
            "custom_id": "MTMLXGT-25981",
            "name": "5939 - E1",
            "status": {"status": "vacío devuelto"},
            "space": {"id": "space-gt"},
            "custom_fields": [],
        }


class FakeBC:
    def __init__(self, _settings) -> None:
        pass


def configure_route(monkeypatch) -> None:
    monkeypatch.setenv("CLICKUP_ACCESS_TOKEN", "pk_test")
    monkeypatch.setenv("CLICKUP_DEFAULT_WORKSPACE_ID", "8451352")
    monkeypatch.setenv("CLICKUP_WEBHOOK_TEAM_ID", "8451352")
    monkeypatch.setenv("CLICKUP_WEBHOOK_TOKEN", "expected-token")
    monkeypatch.setenv("CLICKUP_WEBHOOK_CUSTOM_TASK_IDS", "true")
    monkeypatch.setattr("webhook_bridge.main.ClickUpClient", FakeClickUp)
    monkeypatch.setattr("webhook_bridge.main.BusinessCentralClient", FakeBC)
    monkeypatch.setattr("webhook_bridge.main.ClickUpSettings.from_env", lambda: object())
    monkeypatch.setattr("webhook_bridge.main.BusinessCentralSettings.from_env", lambda: object())
    monkeypatch.setattr("webhook_bridge.main.InvoiceAutomationSettings.from_env", lambda: object())
    monkeypatch.setattr("webhook_bridge.main.StorageInvoiceSettings.from_env", lambda: object())


def test_storage_webhook_dry_run_accepts_dedicated_route(monkeypatch) -> None:
    configure_route(monkeypatch)
    monkeypatch.setenv("CLICKUP_STORAGE_INVOICE_WEBHOOK_APPLY", "false")
    monkeypatch.setattr(
        "webhook_bridge.main.prepare_clickup_bc_storage_invoice_preview",
        lambda **_kwargs: {
            "status": "dry_run_ready",
            "reference": "MTMLXGT-25981-ALM",
            "storage_validation": {"task_status": "Facturada"},
        },
    )

    response = TestClient(app).post(
        "/clickup/webhooks/storage-invoice-sync/MTMLXGT-25981",
        headers={"Authorization": "Bearer expected-token"},
        json={},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "processed"
    assert payload["mode"] == "dry_run"
    assert payload["result"]["reference"] == "MTMLXGT-25981-ALM"


def test_storage_webhook_apply_preserves_facturada_status(monkeypatch) -> None:
    configure_route(monkeypatch)
    monkeypatch.setenv("CLICKUP_STORAGE_INVOICE_WEBHOOK_APPLY", "true")
    monkeypatch.setenv("CLICKUP_INVOICE_SEND_ENABLED", "true")
    monkeypatch.setattr(
        "webhook_bridge.main.prepare_clickup_bc_storage_invoice_preview",
        lambda **_kwargs: {"status": "duplicate_invoice"},
    )
    issued = {
        "status": "applied",
        "completed_stages": ["reuse_existing_posted_storage_invoice"],
        "finalized_invoices": [
            {
                "invoice_group": "ALM",
                "posted_invoice_after_stamp": {"id": "invoice-1", "number": "GTFVR0004450"},
                "custom_api_row_after_stamp": {"electronicDocumentStatus": "Stamp Received"},
            }
        ],
    }
    monkeypatch.setattr(
        "webhook_bridge.main.issue_clickup_bc_storage_invoice",
        lambda **_kwargs: issued,
    )
    monkeypatch.setattr("webhook_bridge.main.validate_invoice_pdf_field_on_task", lambda _summary: {})
    email_calls = []

    def send_email(**kwargs):
        email_calls.append(kwargs)
        return {"status": "sent", "deliveries": [{"invoice_number": "GTFVR0004450"}]}

    monkeypatch.setattr("webhook_bridge.main.send_issued_invoice_customer_emails", send_email)
    delivery_calls = []

    def finalize(**kwargs):
        delivery_calls.append(kwargs)
        return {"uploaded_documents": [{"invoice_number": "GTFVR0004450"}]}

    monkeypatch.setattr("webhook_bridge.main.finalize_clickup_issued_invoices", finalize)

    response = TestClient(app).post(
        "/clickup/webhooks/storage-invoice-sync/MTMLXGT-25981",
        headers={"Authorization": "Bearer expected-token"},
        json={},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "processed"
    assert payload["mode"] == "apply"
    assert payload["final_status_update"] is None
    assert "send_customer_email_from_bc" in payload["action"]
    assert "retain_facturada_status" in payload["action"]
    assert email_calls[0]["invoice_result"]["finalized_invoices"][0]["invoice_group"] == "ALM"
    assert delivery_calls[0]["mark_status"] is False
