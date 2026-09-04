from __future__ import annotations

import json
from datetime import date

from inspection_invoices.service import issue_inspection_invoice, prepare_inspection_invoice_preview
from webhook_bridge import main as webhook_main
from webhook_bridge.main import app


PAYLOAD_FIELD_ID = "5e825df5-9a5e-45f8-87cf-0b1daa16b38f"


def _task(*, payload: dict | None = None) -> dict:
    payload = payload or {
        "schema_version": "mtm.inspection-invoice.v1",
        "task_id": "86e29y1gx",
        "bc_item": "INT000000031",
        "description": "INSPECTION AT ORIGIN",
        "po_reference": "LGDCH91C5VA702240",
        "customer_name": "MAGNA MOTORS GUATEMALA, SOCIEDAD ANONIMA",
        "unit_price": 65,
        "quantity": 1,
        "currency": "USD",
        "inspection_date": "2026-07-03",
        "vendor": "Asia IBS",
    }
    return {
        "id": "86e29y1gx",
        "custom_id": "MTLXMGN-316",
        "name": "LGDCH91C5VA702240(DRYRUN TEST)",
        "list": {"id": "901707774763"},
        "custom_fields": [
            {"id": PAYLOAD_FIELD_ID, "name": "Invoice Payload", "value": json.dumps(payload)}
        ],
    }


class _BC:
    def __init__(self) -> None:
        self.headers: list[dict] = []
        self.lines: list[dict] = []
        self.posted = False
        self.stamped = False

    def resolve_customer_by_name(self, customer_name: str, *, market: str):
        assert customer_name.startswith("MAGNA")
        assert market == "GT"
        return {
            "id": "customer-id",
            "number": "C00095",
            "displayName": "MAGNA MOTORS GUATEMALA SOCIEDAD ANONIMA",
            "currencyCode": "USD",
            "paymentTermsId": "term-30",
        }

    def get_customer_by_id(self, *_args, **_kwargs):
        return None

    def find_entities(self, entity_name: str, **_kwargs):
        assert entity_name == "salesInvoices"
        return []

    def get_customer_invoicing_by_number(self, number: str, *, market: str):
        assert number == "C00095"
        assert market == "GT"
        return {"felCountryReady": True, "resolvedFelCountryCode": "GT"}

    def resolve_item_by_number(self, number: str, *, market: str):
        assert number == "INT000000031"
        assert market == "GT"
        return {"id": "item-id", "number": number, "blocked": False}

    def create_sales_invoice(self, payload: dict, *, market: str):
        self.headers.append(payload)
        return {"id": "invoice-id", "number": "DRAFT-1", **payload}

    def create_sales_invoice_line(self, invoice_id: str, payload: dict, *, market: str):
        assert invoice_id == "invoice-id"
        self.lines.append(payload)
        return {"id": f"line-{len(self.lines)}", **payload}

    def post_sales_invoice(self, invoice_id: str, *, market: str):
        assert invoice_id == "invoice-id"
        self.posted = True
        return {}

    def get_entity(self, entity_name: str, invoice_id: str, *, market: str):
        assert entity_name == "salesInvoices"
        if not self.posted:
            return {"id": invoice_id, "number": "DRAFT-1"}
        return {
            "id": invoice_id,
            "number": "GTFVR0005001",
            "externalDocumentNumber": "MTLXMGN-316-INT",
        }

    def get_posted_sales_invoice_by_external_document_number(self, *_args, **_kwargs):
        return None

    def get_posted_invoice_fel_description_by_number(self, invoice_number: str, *, market: str):
        assert invoice_number == "GTFVR0005001"
        return {
            "id": "fel-id",
            "electronicDocumentStatus": "Stamp Received" if self.stamped else "Pending",
        }

    def sync_posted_invoice_fel_line_descriptions(self, fel_id: str, *, market: str):
        assert fel_id == "fel-id"
        return {}

    def stamp_posted_invoice_fel(self, fel_id: str, *, market: str):
        assert fel_id == "fel-id"
        self.stamped = True
        return {}


def test_preview_builds_a_task_idempotent_bc_invoice(monkeypatch) -> None:
    monkeypatch.setenv("INSPECTION_INVOICE_MARKET", "GT")
    monkeypatch.setenv("INSPECTION_INVOICE_CURRENCY", "USD")
    preview = prepare_inspection_invoice_preview(task=_task(), bc_client=_BC(), today=date(2026, 7, 11))

    assert preview["status"] == "dry_run_ready"
    assert preview["proposed_bc_payload"]["externalDocumentNumber"] == "MTLXMGN-316-INT"
    assert preview["proposed_bc_payload"]["customerPurchaseOrderReference"] == "LGDCH91C5VA702240"
    assert preview["proposed_bc_payload"]["invoiceDate"] == "2026-07-11"
    assert preview["proposed_bc_line_payloads"][1] == {
        "lineType": "Item",
        "lineObjectNumber": "INT000000031",
        "itemId": "item-id",
        "description": "INSPECTION AT ORIGIN",
        "quantity": 1.0,
        "unitPrice": 65.0,
        "taxCode": "NO IVA",
    }
    assert preview["total"] == 65.0


def test_preview_rejects_a_payload_for_another_task() -> None:
    task = _task()
    payload = json.loads(task["custom_fields"][0]["value"])
    payload["task_id"] = "another-task"
    task["custom_fields"][0]["value"] = json.dumps(payload)

    result = prepare_inspection_invoice_preview(task=task, bc_client=_BC())

    assert result["status"] == "invalid_invoice_payload"
    assert "does not match" in result["message"]


def test_issue_creates_posts_and_stamps_after_preflight(monkeypatch) -> None:
    monkeypatch.setenv("INSPECTION_INVOICE_MARKET", "GT")
    bc = _BC()

    result = issue_inspection_invoice(task=_task(), bc_client=bc, today=date(2026, 7, 11))

    assert result["status"] == "applied"
    assert result["completed_stages"] == [
        "create_sales_invoice",
        "create_sales_invoice_lines",
        "post_sales_invoice",
        "sync_fel_descriptions",
        "stamp_fel_invoice",
    ]
    assert len(bc.headers) == 1
    assert len(bc.lines) == 2
    assert result["finalized_invoices"][0]["number"] == "GTFVR0005001"


def test_inspection_invoice_webhook_requires_the_shared_webhook_token(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    monkeypatch.setenv("CLICKUP_WEBHOOK_TOKEN", "expected-token")

    response = TestClient(app).post(
        "/clickup/webhooks/inspection-invoice-sync/MTLXMGN-316",
        headers={"Authorization": "Bearer wrong-token"},
        json={},
    )

    assert response.status_code == 401


def test_inspection_invoice_readiness_is_dry_run_by_default(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    monkeypatch.setenv("CLICKUP_WEBHOOK_TOKEN", "expected-token")
    monkeypatch.setenv("CLICKUP_ACCESS_TOKEN", "pk_test")
    monkeypatch.delenv("INSPECTION_INVOICE_WEBHOOK_APPLY", raising=False)
    monkeypatch.delenv("CLICKUP_INVOICE_SEND_ENABLED", raising=False)

    response = TestClient(app).get("/clickup/webhooks/inspection-invoice-sync/readiness")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["apply_mode"] is False
    assert response.json()["customer_email_enabled"] is False


def test_inspection_invoice_webhook_returns_the_live_style_dry_run(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    class _ClickUp:
        settings = type("Settings", (), {"default_workspace_id": "8451352"})()

        def get_task(self, task_id: str, **_kwargs):
            assert task_id == "MTLXMGN-316"
            return _task()

    monkeypatch.setenv("CLICKUP_WEBHOOK_TOKEN", "expected-token")
    monkeypatch.setenv("INSPECTION_INVOICE_WEBHOOK_APPLY", "false")
    monkeypatch.setattr(webhook_main.ClickUpSettings, "from_env", lambda: object())
    monkeypatch.setattr(webhook_main.BusinessCentralSettings, "from_env", lambda: object())
    monkeypatch.setattr(webhook_main, "ClickUpClient", lambda _settings: _ClickUp())
    monkeypatch.setattr(webhook_main, "BusinessCentralClient", lambda _settings: _BC())

    response = TestClient(app).post(
        "/clickup/webhooks/inspection-invoice-sync/MTLXMGN-316",
        headers={"Authorization": "Bearer expected-token"},
        json={},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "processed"
    assert response.json()["mode"] == "dry_run"
    assert response.json()["result"]["proposed_bc_payload"]["externalDocumentNumber"] == "MTLXMGN-316-INT"


def test_inspection_invoice_apply_sends_customer_email_before_clickup_delivery(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    events: list[str] = []

    class _ClickUp:
        settings = type("Settings", (), {"default_workspace_id": "8451352"})()

        def get_task(self, task_id: str, **_kwargs):
            assert task_id == "MTLXMGN-316"
            return _task()

    issued = {
        "status": "applied",
        "market": "GT",
        "finalized_invoices": [],
        "completed_stages": ["stamp_fel_invoice"],
    }
    settings = type("Settings", (), {"supported_market": "GT"})()
    summary = {
        "task_id": "86e29y1gx",
        "custom_id": "MTLXMGN-316",
        "name": "LGDCH91C5VA702240(DRYRUN TEST)",
        "custom_fields": {},
    }

    def send_email(**_kwargs):
        events.append("send")
        return {"status": "sent", "sender": "consuelo@mtmlogix.com"}

    def finalize(**_kwargs):
        events.append("finalize")
        return {"status": "delivered"}

    monkeypatch.setenv("CLICKUP_WEBHOOK_TOKEN", "expected-token")
    monkeypatch.setenv("CLICKUP_WEBHOOK_TEAM_ID", "8451352")
    monkeypatch.setenv("CLICKUP_WEBHOOK_CUSTOM_TASK_IDS", "true")
    monkeypatch.setenv("INSPECTION_INVOICE_WEBHOOK_APPLY", "true")
    monkeypatch.setenv("CLICKUP_INVOICE_SEND_ENABLED", "true")
    monkeypatch.setattr(webhook_main.ClickUpSettings, "from_env", lambda: object())
    monkeypatch.setattr(webhook_main.BusinessCentralSettings, "from_env", lambda: object())
    monkeypatch.setattr(webhook_main.InvoiceAutomationSettings, "from_env", lambda: settings)
    monkeypatch.setattr(webhook_main, "ClickUpClient", lambda _settings: _ClickUp())
    monkeypatch.setattr(webhook_main, "BusinessCentralClient", lambda _settings: object())
    monkeypatch.setattr(
        webhook_main,
        "prepare_inspection_invoice_preview",
        lambda **_kwargs: {"status": "dry_run_ready"},
    )
    monkeypatch.setattr(webhook_main, "issue_inspection_invoice", lambda **_kwargs: issued)
    monkeypatch.setattr(webhook_main, "summarize_task_for_customer_mapping", lambda _task: summary)
    monkeypatch.setattr(webhook_main, "send_issued_invoice_customer_emails", send_email)
    monkeypatch.setattr(webhook_main, "finalize_clickup_issued_invoices", finalize)
    monkeypatch.setattr(
        webhook_main,
        "_write_inspection_invoice_number",
        lambda **_kwargs: {"status": "written"},
    )
    monkeypatch.setattr(
        webhook_main,
        "_mark_inspection_invoice_complete",
        lambda **_kwargs: {"status": "complete"},
    )

    response = TestClient(app).post(
        "/clickup/webhooks/inspection-invoice-sync/MTLXMGN-316",
        headers={"Authorization": "Bearer expected-token"},
        json={},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "processed"
    assert payload["mode"] == "apply"
    assert payload["customer_email_action"] == "sent"
    assert payload["result"]["customer_email_delivery"]["status"] == "sent"
    assert events == ["send", "finalize"]


def test_inspection_invoice_email_failure_blocks_clickup_completion(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    class _ClickUp:
        settings = type("Settings", (), {"default_workspace_id": "8451352"})()

        def __init__(self) -> None:
            self.comments: list[dict] = []

        def get_task(self, task_id: str, **_kwargs):
            assert task_id == "MTLXMGN-316"
            return _task()

        def create_task_comment(self, task_id: str, *, comment_text: str, notify_all: bool):
            comment = {
                "task_id": task_id,
                "comment_text": comment_text,
                "notify_all": notify_all,
            }
            self.comments.append(comment)
            return comment

    clickup = _ClickUp()
    settings = type("Settings", (), {"supported_market": "GT"})()
    summary = {
        "task_id": "86e29y1gx",
        "custom_id": "MTLXMGN-316",
        "name": "LGDCH91C5VA702240(DRYRUN TEST)",
        "custom_fields": {},
    }

    monkeypatch.setenv("CLICKUP_WEBHOOK_TOKEN", "expected-token")
    monkeypatch.setenv("CLICKUP_WEBHOOK_TEAM_ID", "8451352")
    monkeypatch.setenv("CLICKUP_WEBHOOK_CUSTOM_TASK_IDS", "true")
    monkeypatch.setenv("INSPECTION_INVOICE_WEBHOOK_APPLY", "true")
    monkeypatch.setenv("CLICKUP_INVOICE_SEND_ENABLED", "true")
    monkeypatch.setattr(webhook_main.ClickUpSettings, "from_env", lambda: object())
    monkeypatch.setattr(webhook_main.BusinessCentralSettings, "from_env", lambda: object())
    monkeypatch.setattr(webhook_main.InvoiceAutomationSettings, "from_env", lambda: settings)
    monkeypatch.setattr(webhook_main, "ClickUpClient", lambda _settings: clickup)
    monkeypatch.setattr(webhook_main, "BusinessCentralClient", lambda _settings: object())
    monkeypatch.setattr(
        webhook_main,
        "prepare_inspection_invoice_preview",
        lambda **_kwargs: {"status": "dry_run_ready"},
    )
    monkeypatch.setattr(
        webhook_main,
        "issue_inspection_invoice",
        lambda **_kwargs: {"status": "applied", "market": "GT"},
    )
    monkeypatch.setattr(webhook_main, "summarize_task_for_customer_mapping", lambda _task: summary)
    monkeypatch.setattr(
        webhook_main,
        "send_issued_invoice_customer_emails",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("SMTP delivery failed")),
    )
    monkeypatch.setattr(
        webhook_main,
        "finalize_clickup_issued_invoices",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("must not finalize")),
    )

    response = TestClient(app).post(
        "/clickup/webhooks/inspection-invoice-sync/MTLXMGN-316",
        headers={"Authorization": "Bearer expected-token"},
        json={},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "failed"
    assert payload["result"]["status"] == "failed_post_creation"
    assert payload["result"]["failed_stage"] == "envio_cliente"
    assert "SMTP delivery failed" in payload["result"]["message"]
    assert len(clickup.comments) == 1
    assert "ENVIO DE FACTURA AL CLIENTE DESDE BUSINESS CENTRAL" in clickup.comments[0]["comment_text"]
