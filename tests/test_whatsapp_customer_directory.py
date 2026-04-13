from whatsapp_integration.config import WhatsAppSettings
from whatsapp_integration.customer_directory import (
    find_customer_directory_match,
    parse_clickup_list_identifier,
)


class FakeClickUpClient:
    def __init__(self, tasks_by_page: dict[int, list[dict]]) -> None:
        self.tasks_by_page = tasks_by_page

    def get_list_tasks(
        self,
        list_id: str,
        *,
        archived: bool = False,
        include_closed: bool = False,
        page: int = 0,
    ) -> dict:
        assert list_id == "directory-list"
        assert not archived
        assert include_closed
        return {"tasks": self.tasks_by_page.get(page, [])}

    def get_task(
        self,
        task_id: str,
        *,
        custom_task_ids: bool = False,
        team_id: str | None = None,
        include_subtasks: bool = False,
    ) -> dict:
        for tasks in self.tasks_by_page.values():
            for task in tasks:
                if task.get("id") == task_id:
                    return task
        raise AssertionError(f"Unknown task id {task_id}")


def make_settings() -> WhatsAppSettings:
    return WhatsAppSettings(
        twilio_auth_token="auth-token",
        twilio_validate_signature=True,
        twilio_validate_url=None,
        booking_list_id="booking-list",
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
        customer_directory_list_id="directory-list",
        directory_task_scan_pages=3,
        directory_phone_field_names=("Contact Phone 1", "Customer Phone"),
        directory_target_list_field_names=("WhatsApp Intake List ID",),
        directory_target_list_field_ids=(),
        directory_customer_name_field_names=("Business Central Legal Name", "Clientes/"),
        directory_allowed_statuses=("current customer",),
        route_rules=(),
    )


def test_parse_clickup_list_identifier_supports_raw_id_and_url() -> None:
    assert parse_clickup_list_identifier("901711638279") == "901711638279"
    assert (
        parse_clickup_list_identifier("https://app.clickup.com/8451352/v/li/901711638279")
        == "901711638279"
    )


def test_find_customer_directory_match_by_phone() -> None:
    clickup = FakeClickUpClient(
        {
            0: [
                {
                    "id": "customer-task-1",
                    "custom_id": "MTM-123",
                    "name": "Smartspace Customer",
                    "date_updated": "200",
                    "status": {"status": "Current Customer"},
                    "custom_fields": [
                        {"name": "Contact Phone 1", "value": "+52 1 55 1234 5678"},
                        {"name": "Business Central Legal Name", "value": "SMARTSPACE SA DE CV"},
                        {"name": "WhatsApp Intake List ID", "value": "901711638279"},
                    ],
                }
            ]
        }
    )

    match = find_customer_directory_match(
        clickup=clickup,
        phone_number="+5215512345678",
        settings=make_settings(),
    )

    assert match is not None
    assert match.task_id == "customer-task-1"
    assert match.custom_id == "MTM-123"
    assert match.customer_name == "SMARTSPACE SA DE CV"
    assert match.target_list_id == "901711638279"
    assert match.matched_phone_field == "Contact Phone 1"


def test_find_customer_directory_match_parses_target_list_url() -> None:
    clickup = FakeClickUpClient(
        {
            0: [
                {
                    "id": "customer-task-1",
                    "custom_id": "MTM-123",
                    "name": "Smartspace Customer",
                    "date_updated": "200",
                    "status": {"status": "Current Customer"},
                    "custom_fields": [
                        {"name": "Contact Phone 1", "value": "+52 1 55 1234 5678"},
                    ],
                }
            ]
        }
    )
    clickup.tasks_by_page[0][0] = {
        **clickup.tasks_by_page[0][0],
        "custom_fields": [
            {"name": "Contact Phone 1", "value": "+52 1 55 1234 5678"},
            {
                "name": "Shipment Management EndPoint",
                "id": "a36761c6-7ac5-4429-a99e-8a9495799c05",
                "value": "https://app.clickup.com/8451352/v/li/901711638279",
            },
        ],
    }
    settings = make_settings()
    settings = WhatsAppSettings(
        **{
            **settings.__dict__,
            "directory_target_list_field_names": ("Shipment Management EndPoint",),
            "directory_target_list_field_ids": ("a36761c6-7ac5-4429-a99e-8a9495799c05",),
        }
    )

    match = find_customer_directory_match(
        clickup=clickup,
        phone_number="+5215512345678",
        settings=settings,
    )

    assert match is not None
    assert match.target_list_id == "901711638279"


def test_find_customer_directory_match_respects_status_filter() -> None:
    clickup = FakeClickUpClient(
        {
            0: [
                {
                    "id": "customer-task-1",
                    "name": "Prospect",
                    "date_updated": "200",
                    "status": {"status": "Prospect"},
                    "custom_fields": [
                        {"name": "Contact Phone 1", "value": "+5215512345678"},
                    ],
                }
            ]
        }
    )

    match = find_customer_directory_match(
        clickup=clickup,
        phone_number="+5215512345678",
        settings=make_settings(),
    )

    assert match is None
