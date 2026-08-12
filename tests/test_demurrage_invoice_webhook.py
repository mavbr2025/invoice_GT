from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from clickup_integration.demurrage_invoice_sync import DemurrageInvoiceSettings
from webhook_bridge.main import app


class FakeClickUp:
    def __init__(self, _settings) -> None:
        self.settings = SimpleNamespace(default_workspace_id="8451352")

    def get_task(self, task_id: str, **_kwargs):
        return {
            "id": task_id,
            "custom_id": "MTMLXGT-26066",
            "name": "GT250103 || MTMLXGT-26066",
            "status": {"status": "arribado en puerto"},
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
    monkeypatch.setattr(
        "webhook_bridge.main.InvoiceAutomationSettings.from_env",
        lambda: SimpleNamespace(supported_market="GT", supported_currency="USD"),
    )
    monkeypatch.setattr(
        "webhook_bridge.main.DemurrageInvoiceSettings.from_env",
        DemurrageInvoiceSettings,
    )


def test_demurrage_readiness_reports_independent_apply_mode(monkeypatch) -> None:
    configure_route(monkeypatch)
    monkeypatch.setenv("CLICKUP_DEMURRAGE_INVOICE_WEBHOOK_APPLY", "false")

    response = TestClient(app).get("/clickup/webhooks/demurrage-invoice-sync/readiness")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["apply_mode"] is False
    assert payload["rate_mode"] == "derived_per_shipment"
    assert payload["bc_item_number"] == "NAT00000033"
    assert payload["reference_suffix"] == "DEM"


def test_demurrage_webhook_dry_run_accepts_dedicated_route(monkeypatch) -> None:
    configure_route(monkeypatch)
    monkeypatch.setenv("CLICKUP_DEMURRAGE_INVOICE_WEBHOOK_APPLY", "false")
    monkeypatch.setattr(
        "webhook_bridge.main.prepare_clickup_bc_demurrage_invoice_preview",
        lambda **_kwargs: {
            "status": "dry_run_ready",
            "reference": "MTMLXGT-26066-DEM-02",
            "invoice_type": "DEM",
        },
    )

    response = TestClient(app).post(
        "/clickup/webhooks/demurrage-invoice-sync/MTMLXGT-26066",
        headers={"Authorization": "Bearer expected-token"},
        json={},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "processed"
    assert payload["mode"] == "dry_run"
    assert payload["result"]["reference"] == "MTMLXGT-26066-DEM-02"


def test_demurrage_webhook_never_applies_when_preview_is_blocked(monkeypatch) -> None:
    configure_route(monkeypatch)
    monkeypatch.setenv("CLICKUP_DEMURRAGE_INVOICE_WEBHOOK_APPLY", "true")
    monkeypatch.setattr(
        "webhook_bridge.main.prepare_clickup_bc_demurrage_invoice_preview",
        lambda **_kwargs: {"status": "storage_history_customer_mismatch"},
    )
    issued = []
    monkeypatch.setattr(
        "webhook_bridge.main.issue_clickup_bc_demurrage_invoice",
        lambda **_kwargs: issued.append(True),
    )

    response = TestClient(app).post(
        "/clickup/webhooks/demurrage-invoice-sync/MTMLXGT-26066",
        headers={"Authorization": "Bearer expected-token"},
        json={},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "blocked"
    assert payload["mode"] == "dry_run"
    assert issued == []
