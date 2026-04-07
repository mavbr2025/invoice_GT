from clickup_integration.auth import build_authorization_url
from clickup_integration.config import ClickUpSettings


def make_settings() -> ClickUpSettings:
    return ClickUpSettings(
        client_id="client-id",
        client_secret="client-secret",
        redirect_uri="http://localhost:8000/clickup/oauth/callback",
        access_token="access-token",
        token_type="Bearer",
        default_workspace_id=None,
        default_customer_list_id=None,
    )


def test_build_authorization_url_without_state() -> None:
    settings = make_settings()
    assert (
        build_authorization_url(settings)
        == "https://app.clickup.com/api?client_id=client-id&redirect_uri=http%3A%2F%2Flocalhost%3A8000%2Fclickup%2Foauth%2Fcallback"
    )


def test_build_authorization_url_with_state() -> None:
    settings = make_settings()
    assert (
        build_authorization_url(settings, state="abc123")
        == "https://app.clickup.com/api?client_id=client-id&redirect_uri=http%3A%2F%2Flocalhost%3A8000%2Fclickup%2Foauth%2Fcallback&state=abc123"
    )


def test_from_env_allows_token_only_runtime(monkeypatch) -> None:
    monkeypatch.delenv("CLICKUP_CLIENT_ID", raising=False)
    monkeypatch.delenv("CLICKUP_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("CLICKUP_REDIRECT_URI", raising=False)
    monkeypatch.setenv("CLICKUP_ACCESS_TOKEN", "pk_runtime_token")

    settings = ClickUpSettings.from_env()

    assert settings.client_id is None
    assert settings.client_secret is None
    assert settings.redirect_uri is None
    assert settings.access_token == "pk_runtime_token"


def test_from_env_requires_oauth_values_when_requested(monkeypatch) -> None:
    monkeypatch.delenv("CLICKUP_CLIENT_ID", raising=False)
    monkeypatch.delenv("CLICKUP_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("CLICKUP_REDIRECT_URI", raising=False)

    try:
        ClickUpSettings.from_env(require_oauth=True)
    except ValueError as exc:
        message = str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected ValueError when OAuth settings are missing.")

    assert "CLICKUP_CLIENT_ID" in message
    assert "CLICKUP_CLIENT_SECRET" in message
    assert "CLICKUP_REDIRECT_URI" in message
