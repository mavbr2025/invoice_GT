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
