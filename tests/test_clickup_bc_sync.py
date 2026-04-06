from types import SimpleNamespace

from clickup_integration.bc_sync import prepare_clickup_to_bc_customer_sync


class FakeBCClient:
    def __init__(self) -> None:
        self.settings = SimpleNamespace(tenant_id="tenant-id", environment="Production")

    def get_entity(self, entity_name: str, entity_id: str, *, market: str | None = None):
        assert entity_name == "customers"
        assert entity_id == "bc-id-1"
        assert market == "GT"
        return {
            "id": "bc-id-1",
            "number": "C00025",
            "displayName": "GIAI INNOVATIONS, SOCIEDAD ANONIMA",
            "phoneNumber": "50401010",
            "website": "",
        }


def test_prepare_clickup_to_bc_customer_sync() -> None:
    clickup_summary = {
        "task_id": "task-1",
        "status": "current customer",
        "market": "GT",
        "custom_fields": {
            "Business Central Customer ID": {"value": "bc-id-1"},
            "Business Central Customer Number": {"value": "C00025"},
            "BC Match Status": {
                "value": 2,
                "type_config": {
                    "options": [
                        {"id": "opt-0", "name": "Unmatched", "orderindex": 0},
                        {"id": "opt-1", "name": "Likely Match", "orderindex": 1},
                        {"id": "opt-2", "name": "Confirmed", "orderindex": 2},
                    ]
                },
            },
            "Contact Phone 1": {"value": "+502 5950 9758"},
            "Webpage": {"value": "https://biorgani.tech/"},
        },
    }

    preview = prepare_clickup_to_bc_customer_sync(
        clickup_summary=clickup_summary,
        bc_client=FakeBCClient(),
    )

    assert preview["status"] == "dry_run_ready"
    assert preview["proposed_bc_patch"] == {
        "phoneNumber": "+502 5950 9758",
        "website": "https://biorgani.tech/",
    }
    assert preview["clickup_sources"]["phone_field"] == "Contact Phone 1"


def test_prepare_clickup_to_bc_customer_sync_blocks_unconfirmed() -> None:
    clickup_summary = {
        "task_id": "task-1",
        "status": "current customer",
        "market": "GT",
        "custom_fields": {
            "Business Central Customer ID": {"value": "bc-id-1"},
            "BC Match Status": {
                "value": 1,
                "type_config": {
                    "options": [
                        {"id": "opt-0", "name": "Unmatched", "orderindex": 0},
                        {"id": "opt-1", "name": "Likely Match", "orderindex": 1},
                        {"id": "opt-2", "name": "Confirmed", "orderindex": 2},
                    ]
                },
            },
            "Contact Phone 1": {"value": "+502 5950 9758"},
            "Webpage": {"value": "https://biorgani.tech/"},
        },
    }

    preview = prepare_clickup_to_bc_customer_sync(
        clickup_summary=clickup_summary,
        bc_client=FakeBCClient(),
    )

    assert preview["status"] == "not_confirmed"
