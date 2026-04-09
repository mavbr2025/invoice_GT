from clickup_integration.config import ClickUpSettings
from webhook_bridge.main import (
    _fetch_clickup_task_for_webhook,
    _infer_clickup_team_id,
    extract_task_id,
    extract_task_id_from_path,
)


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


def test_extract_task_id_from_path_supports_clickup_dynamic_segments() -> None:
    path = "/clickup/webhooks/customer-sync86e0ty7pg/OPERA%2520LOGISTICA/1775697146706/"
    assert (
        extract_task_id_from_path(path, base_path="/clickup/webhooks/customer-sync")
        == "86e0ty7pg"
    )


def test_extract_task_id_from_path_returns_none_for_other_routes() -> None:
    assert (
        extract_task_id_from_path(
            "/clickup/webhooks/not-customer-sync/123",
            base_path="/clickup/webhooks/customer-sync",
        )
        is None
    )


class _FakeClickUpClient:
    def __init__(self, *, default_workspace_id: str | None = None) -> None:
        self.settings = ClickUpSettings(
            client_id=None,
            client_secret=None,
            redirect_uri=None,
            access_token="pk_test",
            token_type="Bearer",
            default_workspace_id=default_workspace_id,
            default_customer_list_id=None,
        )
        self.calls: list[tuple[str, bool, str | None]] = []

    def get_authorized_workspaces(self) -> dict[str, object]:
        return {"teams": [{"id": "8451352"}]}

    def get_task(
        self,
        task_id: str,
        *,
        custom_task_ids: bool = False,
        team_id: str | None = None,
        include_subtasks: bool = False,
    ) -> dict[str, object]:
        self.calls.append((task_id, custom_task_ids, team_id))
        if custom_task_ids and team_id == "8451352":
            return {"id": "1", "name": "ok"}
        raise RuntimeError("lookup failed")


def test_infer_clickup_team_id_uses_single_authorized_workspace() -> None:
    client = _FakeClickUpClient()
    assert _infer_clickup_team_id(client) == "8451352"


def test_fetch_clickup_task_for_webhook_retries_with_inferred_team_id() -> None:
    client = _FakeClickUpClient()
    task = _fetch_clickup_task_for_webhook(
        clickup=client,
        task_id="MTM-1",
        custom_task_ids=True,
        team_id=None,
    )
    assert task == {"id": "1", "name": "ok"}
    assert client.calls == [
        ("MTM-1", True, None),
        ("MTM-1", True, "8451352"),
    ]
