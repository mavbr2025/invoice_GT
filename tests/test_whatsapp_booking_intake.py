from whatsapp_integration.booking_intake import BookingTarget, normalize_phone_key, process_whatsapp_booking_intake
from whatsapp_integration.config import WhatsAppSettings


class FakeClickUpClient:
    def __init__(self) -> None:
        self.created_tasks: list[dict] = []
        self.comments: list[dict] = []
        self.field_updates: list[dict] = []
        self.tasks_by_page = {
            0: [],
        }

    def get_list_custom_fields(self, list_id: str) -> dict:
        assert list_id == "list-1"
        return {
            "fields": [
                {"id": "field-phone", "name": "Customer Phone"},
                {"id": "field-name", "name": "Customer Name"},
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
        assert list_id == "list-1"
        assert not archived
        assert not include_closed
        return {"tasks": self.tasks_by_page.get(page, [])}

    def create_task(self, list_id: str, *, name: str, description: str | None = None, status: str | None = None) -> dict:
        task = {
            "id": "task-new",
            "name": name,
            "description": description,
            "status": status,
        }
        self.created_tasks.append(task)
        return task

    def create_task_comment(self, task_id: str, *, comment_text: str, notify_all: bool = False) -> dict:
        comment = {
            "task_id": task_id,
            "comment_text": comment_text,
            "notify_all": notify_all,
        }
        self.comments.append(comment)
        return comment

    def set_task_custom_field_value(self, task_id: str, field_id: str, value: str) -> dict:
        payload = {
            "task_id": task_id,
            "field_id": field_id,
            "value": value,
        }
        self.field_updates.append(payload)
        return payload


def make_settings() -> WhatsAppSettings:
    return WhatsAppSettings(
        twilio_auth_token="auth-token",
        twilio_validate_signature=True,
        twilio_validate_url=None,
        booking_list_id="list-1",
        operations_list_id="ops-list",
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
        route_rules=(),
    )


def make_event(message_id: str = "SM123") -> dict:
    return {
        "channel": "whatsapp",
        "provider": "twilio",
        "customer_phone": "+5215512345678",
        "customer_name": "Mario",
        "message_id": message_id,
        "conversation_id": "whatsapp:+5215512345678",
        "received_at": "2026-04-11T06:00:00+00:00",
        "text": "I need a transfer tomorrow at 8am",
        "media": [],
    }


def test_normalize_phone_key_strips_non_digits() -> None:
    assert normalize_phone_key("whatsapp:+52 1 55 1234 5678") == "5215512345678"


def test_process_whatsapp_booking_intake_creates_task_when_none_exists() -> None:
    clickup = FakeClickUpClient()

    result = process_whatsapp_booking_intake(
        event=make_event(),
        clickup=clickup,
        settings=make_settings(),
        target=BookingTarget(
            list_id="list-1",
            customer_name="SMARTSPACE",
            customer_task_id="customer-task-1",
            customer_task_custom_id="MTM-123",
            route_source="customer_directory",
        ),
    )

    assert result["status"] == "processed"
    assert result["action"] == "create_booking_task"
    assert clickup.created_tasks[0]["status"] == "New WhatsApp Lead"
    assert clickup.created_tasks[0]["name"] == "Booking Intake - SMARTSPACE"
    assert "Routed customer: SMARTSPACE" in clickup.created_tasks[0]["description"]
    assert "Route source: customer_directory" in clickup.created_tasks[0]["description"]
    assert "Routed customer custom id: MTM-123" in clickup.created_tasks[0]["description"]
    assert any(update["field_id"] == "field-phone" for update in clickup.field_updates)
    assert any(update["field_id"] == "field-message" for update in clickup.field_updates)


def test_process_whatsapp_booking_intake_appends_to_existing_task() -> None:
    clickup = FakeClickUpClient()
    clickup.tasks_by_page[0] = [
        {
            "id": "task-existing",
            "name": "Booking Intake - Mario",
            "date_updated": "200",
            "custom_fields": [
                {"name": "Customer Phone", "value": "5215512345678"},
                {"name": "Last WhatsApp Message ID", "value": "SM122"},
            ],
        }
    ]

    result = process_whatsapp_booking_intake(
        event=make_event(message_id="SM123"),
        clickup=clickup,
        settings=make_settings(),
        target=BookingTarget(list_id="list-1", customer_name="SMARTSPACE", route_source="customer_directory"),
    )

    assert result["status"] == "processed"
    assert result["action"] == "append_to_existing_task"
    assert result["task_id"] == "task-existing"
    assert clickup.comments[0]["task_id"] == "task-existing"
    assert not clickup.created_tasks


def test_process_whatsapp_booking_intake_ignores_duplicate_message() -> None:
    clickup = FakeClickUpClient()
    clickup.tasks_by_page[0] = [
        {
            "id": "task-existing",
            "name": "Booking Intake - Mario",
            "date_updated": "200",
            "custom_fields": [
                {"name": "Customer Phone", "value": "5215512345678"},
                {"name": "Last WhatsApp Message ID", "value": "SM123"},
            ],
        }
    ]

    result = process_whatsapp_booking_intake(
        event=make_event(message_id="SM123"),
        clickup=clickup,
        settings=make_settings(),
        target=BookingTarget(list_id="list-1", customer_name="SMARTSPACE", route_source="customer_directory"),
    )

    assert result["status"] == "ignored"
    assert result["reason"] == "duplicate_message"
    assert not clickup.comments
    assert not clickup.created_tasks
