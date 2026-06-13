from clickup_integration.mapping import summarize_task_for_customer_mapping


def test_summarize_task_keeps_non_empty_dropdown_when_field_names_duplicate() -> None:
    summary = summarize_task_for_customer_mapping(
        {
            "id": "task-1",
            "status": {"status": "current customer"},
            "custom_fields": [
                {
                    "id": "currency-dropdown",
                    "name": "Currency",
                    "type": "drop_down",
                    "value": 0,
                    "type_config": {"options": [{"name": "USD", "orderindex": 0}]},
                },
                {
                    "id": "currency-amount",
                    "name": "Currency",
                    "type": "currency",
                    "value": None,
                    "type_config": {},
                },
            ],
        }
    )

    assert summary["custom_fields"]["Currency"]["id"] == "currency-dropdown"
