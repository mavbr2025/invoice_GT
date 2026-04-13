from fastapi.testclient import TestClient

from webhook_bridge.main import app


class FakeClickUpClient:
    def __init__(self, settings) -> None:
        self.settings = settings
        self.created_tasks: list[dict] = []
        self.field_updates: list[dict] = []

    def get_list_custom_fields(self, list_id: str) -> dict:
        return {
            "fields": [
                {"id": "field-phone", "name": "Customer Phone"},
                {"id": "field-name", "name": "Customer Name"},
                {"id": "field-routed-customer", "name": "Routed Customer"},
                {"id": "field-source", "name": "Source Channel"},
                {"id": "field-conversation", "name": "Conversation ID"},
                {"id": "field-at", "name": "Last WhatsApp Message At"},
                {"id": "field-message", "name": "Last WhatsApp Message ID"},
            ]
        }

    def get_list_tasks(
        self,
        list_id: str,
        *,
        archived: bool = False,
        include_closed: bool = False,
        page: int = 0,
    ) -> dict:
        return {"tasks": []}

    def create_task(self, list_id: str, *, name: str, description: str | None = None, status: str | None = None) -> dict:
        task = {
            "id": "task-1",
            "name": name,
            "description": description,
            "status": status,
        }
        self.created_tasks.append(task)
        return task

    def set_task_custom_field_value(self, task_id: str, field_id: str, value: str) -> dict:
        payload = {"task_id": task_id, "field_id": field_id, "value": value}
        self.field_updates.append(payload)
        return payload

    def create_task_comment(self, task_id: str, *, comment_text: str, notify_all: bool = False) -> dict:
        raise AssertionError("Comment creation should not be used in this scenario.")


def test_whatsapp_webhook_creates_booking_task(monkeypatch) -> None:
    fake_clients: list[FakeClickUpClient] = []

    def fake_clickup_client_factory(settings):
        client = FakeClickUpClient(settings)
        fake_clients.append(client)
        return client

    monkeypatch.setenv("CLICKUP_ACCESS_TOKEN", "pk_test")
    monkeypatch.setenv("WHATSAPP_CLICKUP_BOOKING_LIST_ID", "list-1")
    monkeypatch.setenv("WHATSAPP_CLICKUP_OPERATIONS_LIST_ID", "ops-list")
    monkeypatch.setenv("TWILIO_VALIDATE_SIGNATURE", "false")
    monkeypatch.setenv("WHATSAPP_CLICKUP_ROUTED_CUSTOMER_FIELD_NAME", "Routed Customer")
    monkeypatch.setenv("WHATSAPP_CLICKUP_CUSTOMER_DIRECTORY_LIST_ID", "")
    monkeypatch.setenv(
        "WHATSAPP_CLICKUP_ROUTE_RULES_JSON",
        '[{"match_type":"exact_phone","pattern":"+5215512345678","list_id":"customer-list","customer_name":"SMARTSPACE"}]',
    )
    monkeypatch.setattr("webhook_bridge.main.ClickUpClient", fake_clickup_client_factory)

    client = TestClient(app)
    response = client.post(
        "/whatsapp/webhooks/inbound",
        data={
            "From": "whatsapp:+5215512345678",
            "To": "whatsapp:+14155238886",
            "ProfileName": "Mario",
            "MessageSid": "SM123",
            "Body": "I need a transfer tomorrow at 8am",
            "NumMedia": "0",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "processed"
    assert payload["action"] == "create_booking_task"
    assert payload["list_id"] == "customer-list"
    assert payload["routed_customer"] == "SMARTSPACE"
    assert payload["route_source"] == "env_rule"
    assert fake_clients[0].created_tasks[0]["name"] == "Booking Intake - SMARTSPACE"


def test_whatsapp_webhook_fails_closed_when_no_operations_fallback(monkeypatch) -> None:
    def fake_clickup_client_factory(settings):
        return FakeClickUpClient(settings)

    monkeypatch.setenv("CLICKUP_ACCESS_TOKEN", "pk_test")
    monkeypatch.delenv("WHATSAPP_CLICKUP_BOOKING_LIST_ID", raising=False)
    monkeypatch.delenv("WHATSAPP_CLICKUP_OPERATIONS_LIST_ID", raising=False)
    monkeypatch.setenv("WHATSAPP_CLICKUP_CUSTOMER_DIRECTORY_LIST_ID", "")
    monkeypatch.setenv("TWILIO_VALIDATE_SIGNATURE", "false")
    monkeypatch.delenv("WHATSAPP_CLICKUP_ROUTE_RULES_JSON", raising=False)
    monkeypatch.setattr("webhook_bridge.main.ClickUpClient", fake_clickup_client_factory)

    client = TestClient(app)
    response = client.post(
        "/whatsapp/webhooks/inbound",
        data={
            "From": "whatsapp:+5215512345678",
            "To": "whatsapp:+14155238886",
            "ProfileName": "Mario",
            "MessageSid": "SM999",
            "Body": "I need a transfer tomorrow at 8am",
            "NumMedia": "0",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ignored"
    assert payload["reason"] == "missing_operations_fallback"
    assert payload["route_source"] == "unrouted"
