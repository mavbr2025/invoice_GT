from webhook_bridge.main import extract_task_id


def test_extract_task_id_prefers_explicit_task_id_keys() -> None:
    assert extract_task_id({"Task ID": "MTM-2035664"}) == "MTM-2035664"
    assert extract_task_id({"task_id": "12345"}) == "12345"
    assert extract_task_id({"taskId": "abc"}) == "abc"


def test_extract_task_id_supports_nested_task_object() -> None:
    assert extract_task_id({"task": {"id": "nested-1"}}) == "nested-1"


def test_extract_task_id_returns_none_when_missing() -> None:
    assert extract_task_id({"foo": "bar"}) is None


def test_extract_task_id_returns_none_for_empty_payload() -> None:
    assert extract_task_id({}) is None
