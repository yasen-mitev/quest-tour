from datetime import UTC, datetime, timedelta
from typing import Annotated
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from starlette.middleware.sessions import SessionMiddleware

from questtour.admin import admin_router
from questtour.admin.crud import handle_integrity, require_fresh
from questtour.admin.errors import (
    AdminValidationError,
    ConflictError,
    FieldError,
    register_admin_exception_handlers,
)
from questtour.auth import AdminSession, auth_router, require_admin
from questtour.settings import Settings


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        _env_file=None,
        database_url="sqlite://",
        public_base_url="http://test",
        storage_backend="local",
        local_storage_dir=tmp_path / "blobs",
        static_dir=None,
        admin_session_secret="test-secret-must-be-at-least-32-bytes-long",
        admin_auth_provider="dev",
        admin_dev_emails=["admin@example.com"],
    )


@pytest.fixture
def auth_app(settings):
    app = FastAPI()
    app.state.settings = settings
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.admin_session_secret,
        session_cookie="questtour_admin_session",
        max_age=settings.admin_session_max_age_minutes * 60,
        same_site="lax",
        https_only=settings.admin_session_secure,
    )
    app.include_router(auth_router)

    @app.get("/api/admin/protected")
    def protected(admin: Annotated[AdminSession, Depends(require_admin)]):
        return admin

    return app


@pytest.fixture
def auth_client(auth_app):
    return TestClient(auth_app)


@pytest.fixture
def entra_settings(settings):
    return Settings(
        _env_file=None,
        database_url=settings.database_url,
        public_base_url=settings.public_base_url,
        storage_backend="local",
        local_storage_dir=settings.local_storage_dir,
        static_dir=None,
        admin_session_secret=settings.admin_session_secret,
        admin_auth_provider="entra",
        admin_entra_tenant_id="tenant-id",
        admin_entra_client_id="client-id",
        admin_entra_client_secret="secret",
        admin_entra_redirect_uri="http://test/api/admin/auth/callback",
        admin_entra_group_object_id="group-id",
    )


@pytest.fixture
def entra_app(entra_settings):
    app = FastAPI()
    app.state.settings = entra_settings
    app.add_middleware(
        SessionMiddleware,
        secret_key=entra_settings.admin_session_secret,
        session_cookie="questtour_admin_session",
        max_age=entra_settings.admin_session_max_age_minutes * 60,
        same_site="lax",
        https_only=entra_settings.admin_session_secure,
    )
    app.include_router(auth_router)
    return app


@pytest.fixture
def entra_client(entra_app):
    return TestClient(entra_app)


def _extract_magic_params(url: str) -> tuple[str, str]:
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    return params["token"][0], params["email"][0]


def test_require_admin_returns_401_without_session(auth_client):
    resp = auth_client.get("/api/admin/protected")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "admin session required"


def test_require_admin_returns_session_email_after_login(auth_client):
    request_resp = auth_client.post(
        "/api/admin/auth/magic/request", json={"email": "admin@example.com"}
    )
    assert request_resp.status_code == 200
    token, email = _extract_magic_params(request_resp.json()["url"])

    verify_resp = auth_client.get(
        "/api/admin/auth/magic/verify",
        params={"token": token, "email": email},
        follow_redirects=False,
    )
    assert verify_resp.status_code == 307
    assert verify_resp.headers["location"] == "/admin"

    protected_resp = auth_client.get("/api/admin/protected")
    assert protected_resp.status_code == 200
    assert protected_resp.json() == {"email": "admin@example.com", "provider": "dev"}


def test_dev_magic_link_url_encodes_email(auth_client):
    # Allow an email containing '+' so we can verify query-string encoding.
    auth_client.app.state.settings = auth_client.app.state.settings.model_copy(
        update={"admin_dev_emails": ["admin+test@example.com"]}
    )
    resp = auth_client.post(
        "/api/admin/auth/magic/request", json={"email": "admin+test@example.com"}
    )
    assert resp.status_code == 200
    url = resp.json()["url"]
    _token, email = _extract_magic_params(url)
    assert email == "admin+test@example.com"
    assert "%2B" in url  # '+' is encoded in query string


def test_dev_magic_link_rejected_for_unknown_email(auth_client):
    resp = auth_client.post(
        "/api/admin/auth/magic/request", json={"email": "not-allowed@example.com"}
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "email not in allowlist"


def test_dev_magic_verify_rejects_consumed_or_wrong_email(auth_client):
    request_resp = auth_client.post(
        "/api/admin/auth/magic/request", json={"email": "admin@example.com"}
    )
    token, email = _extract_magic_params(request_resp.json()["url"])

    wrong_resp = auth_client.get(
        "/api/admin/auth/magic/verify",
        params={"token": token, "email": "other@test.local"},
    )
    assert wrong_resp.status_code == 400

    first_resp = auth_client.get(
        "/api/admin/auth/magic/verify",
        params={"token": token, "email": email},
        follow_redirects=False,
    )
    assert first_resp.status_code == 307

    second_resp = auth_client.get(
        "/api/admin/auth/magic/verify",
        params={"token": token, "email": email},
    )
    assert second_resp.status_code == 400


def test_provider_endpoint_reports_configured_provider(auth_client, entra_client):
    assert auth_client.get("/api/admin/auth/provider").json() == {"provider": "dev"}
    assert entra_client.get("/api/admin/auth/provider").json() == {"provider": "entra"}


def test_dev_magic_endpoints_return_404_when_provider_is_entra(entra_client):
    request_resp = entra_client.post(
        "/api/admin/auth/magic/request", json={"email": "admin@example.com"}
    )
    assert request_resp.status_code == 404

    verify_resp = entra_client.get(
        "/api/admin/auth/magic/verify", params={"token": "abc", "email": "a@b.com"}
    )
    assert verify_resp.status_code == 404


def test_entra_callback_sets_session_when_user_is_in_group(entra_client):
    mock_oauth = MagicMock()
    mock_oauth.microsoft.authorize_access_token = AsyncMock(
        return_value={"access_token": "token123"}
    )

    with patch("questtour.auth.entra.OAuth", return_value=mock_oauth):
        mock_http_client = MagicMock()
        mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_http_client.__aexit__ = AsyncMock(return_value=None)

        user_resp = MagicMock()
        user_resp.status_code = 200
        user_resp.json.return_value = {"mail": "admin@example.com"}

        member_resp = MagicMock()
        member_resp.status_code = 200
        member_resp.json.return_value = {"value": [{"id": "group-id"}]}

        mock_http_client.get = AsyncMock(side_effect=[user_resp, member_resp])

        with patch("questtour.auth.entra.httpx.AsyncClient", return_value=mock_http_client):
            callback_resp = entra_client.get(
                "/api/admin/auth/callback?code=abc&state=xyz",
                follow_redirects=False,
            )
            assert callback_resp.status_code == 307
            assert callback_resp.headers["location"] == "/admin"


def test_entra_callback_rejects_account_without_usable_email(entra_client):
    mock_oauth = MagicMock()
    mock_oauth.microsoft.authorize_access_token = AsyncMock(
        return_value={"access_token": "token123"}
    )

    with patch("questtour.auth.entra.OAuth", return_value=mock_oauth):
        mock_http_client = MagicMock()
        mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_http_client.__aexit__ = AsyncMock(return_value=None)

        user_resp = MagicMock()
        user_resp.status_code = 200
        user_resp.json.return_value = {"givenName": "No Email"}

        member_resp = MagicMock()
        member_resp.status_code = 200
        member_resp.json.return_value = {"value": [{"id": "group-id"}]}

        mock_http_client.get = AsyncMock(side_effect=[user_resp, member_resp])

        with patch("questtour.auth.entra.httpx.AsyncClient", return_value=mock_http_client):
            callback_resp = entra_client.get("/api/admin/auth/callback?code=abc&state=xyz")
            assert callback_resp.status_code == 403
            assert callback_resp.json()["detail"] == "account has no usable email"


def test_entra_callback_rejects_user_not_in_group(entra_client):
    mock_oauth = MagicMock()
    mock_oauth.microsoft.authorize_access_token = AsyncMock(
        return_value={"access_token": "token123"}
    )

    with patch("questtour.auth.entra.OAuth", return_value=mock_oauth):
        mock_http_client = MagicMock()
        mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_http_client.__aexit__ = AsyncMock(return_value=None)

        user_resp = MagicMock()
        user_resp.status_code = 200
        user_resp.json.return_value = {"mail": "user@example.com"}

        member_resp = MagicMock()
        member_resp.status_code = 200
        member_resp.json.return_value = {"value": []}

        mock_http_client.get = AsyncMock(side_effect=[user_resp, member_resp])

        with patch("questtour.auth.entra.httpx.AsyncClient", return_value=mock_http_client):
            callback_resp = entra_client.get("/api/admin/auth/callback?code=abc&state=xyz")
            assert callback_resp.status_code == 403
            assert callback_resp.json()["detail"] == "not in admin group"


def test_entra_callback_rejects_graph_errors(entra_client):
    mock_oauth = MagicMock()
    mock_oauth.microsoft.authorize_access_token = AsyncMock(
        return_value={"access_token": "token123"}
    )

    with patch("questtour.auth.entra.OAuth", return_value=mock_oauth):
        mock_http_client = MagicMock()
        mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_http_client.__aexit__ = AsyncMock(return_value=None)

        user_resp = MagicMock()
        user_resp.status_code = 500
        member_resp = MagicMock()
        member_resp.status_code = 200
        member_resp.json.return_value = {"value": [{"id": "group-id"}]}

        mock_http_client.get = AsyncMock(side_effect=[user_resp, member_resp])

        with patch("questtour.auth.entra.httpx.AsyncClient", return_value=mock_http_client):
            callback_resp = entra_client.get("/api/admin/auth/callback?code=abc&state=xyz")
            assert callback_resp.status_code == 403
            assert callback_resp.json()["detail"] == "cannot verify group membership"


def test_logout_clears_session_cookie(auth_client):
    request_resp = auth_client.post(
        "/api/admin/auth/magic/request", json={"email": "admin@example.com"}
    )
    token, email = _extract_magic_params(request_resp.json()["url"])
    auth_client.get(
        "/api/admin/auth/magic/verify",
        params={"token": token, "email": email},
        follow_redirects=False,
    )

    protected_resp = auth_client.get("/api/admin/protected")
    assert protected_resp.status_code == 200

    logout_resp = auth_client.post("/api/admin/auth/logout")
    assert logout_resp.status_code == 200
    assert logout_resp.json() == {"ok": True}

    protected_after = auth_client.get("/api/admin/protected")
    assert protected_after.status_code == 401


# ---------------------------------------------------------------------------
# Structured admin error handlers
# ---------------------------------------------------------------------------


class EchoBody(BaseModel):
    msg: str


@pytest.fixture
def admin_errors_app(settings):
    app = FastAPI()
    app.state.settings = settings
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.admin_session_secret,
        session_cookie="questtour_admin_session",
        max_age=settings.admin_session_max_age_minutes * 60,
        same_site="lax",
        https_only=settings.admin_session_secure,
    )
    register_admin_exception_handlers(app)
    app.include_router(auth_router)
    app.include_router(admin_router)

    @app.post("/api/admin/check")
    def admin_check():
        raise AdminValidationError([FieldError(field="name", message="bad name")])

    @app.get("/api/admin/conflict")
    def admin_conflict():
        raise ConflictError(
            "Team",
            {"id": 1, "updated_at": "2026-10-14T08:00:00+00:00"},
        )

    @app.get("/api/admin/boom")
    def admin_boom():
        raise RuntimeError("intentional admin boom")

    @app.post("/api/admin/echo")
    def admin_echo(body: EchoBody):
        return {"msg": body.msg}

    @app.post("/play/echo")
    def player_echo(body: EchoBody):
        return {"msg": body.msg}

    @app.get("/play/boom")
    def player_boom():
        raise RuntimeError("intentional player boom")

    return app


@pytest.fixture
def admin_errors_client(admin_errors_app):
    return TestClient(admin_errors_app, raise_server_exceptions=False)


def test_admin_validation_error_returns_errors_shape(admin_errors_client):
    resp = admin_errors_client.post("/api/admin/check", json={})
    assert resp.status_code == 422
    assert resp.json() == {"errors": [{"field": "name", "message": "bad name"}]}


def test_admin_request_validation_error_returns_errors_shape(admin_errors_client):
    resp = admin_errors_client.post("/api/admin/echo", json={"msg": 123})
    assert resp.status_code == 422
    data = resp.json()
    assert "errors" in data
    assert "detail" not in data
    assert data["errors"][0]["field"] == "body.msg"


def test_player_request_validation_error_keeps_detail_shape(admin_errors_client):
    resp = admin_errors_client.post("/play/echo", json={"msg": 123})
    assert resp.status_code == 422
    data = resp.json()
    assert "detail" in data
    assert "errors" not in data


def test_conflict_error_returns_409(admin_errors_client):
    resp = admin_errors_client.get("/api/admin/conflict")
    assert resp.status_code == 409
    assert resp.json() == {
        "entity": "Team",
        "current": {"id": 1, "updated_at": "2026-10-14T08:00:00+00:00"},
    }


def test_unexpected_admin_error_returns_reference_and_logs(admin_errors_client):
    with patch("questtour.admin.errors.log.exception") as mock_log:
        resp = admin_errors_client.get("/api/admin/boom")
    assert resp.status_code == 500
    data = resp.json()
    assert "reference" in data
    assert len(data) == 1
    mock_log.assert_called_once_with("unhandled admin error (reference=%s)", data["reference"])


def test_player_error_not_caught_by_admin_handler(admin_errors_client):
    resp = admin_errors_client.get("/play/boom")
    assert resp.status_code == 500
    assert "reference" not in resp.text


def test_seed_error_requires_admin_session(admin_errors_client):
    resp = admin_errors_client.get("/api/admin/seed-error")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "admin session required"


def test_seed_error_returns_app_state_seed_error(admin_errors_client):
    admin_errors_client.app.state.seed_error = "seed import failed; see logs"

    request_resp = admin_errors_client.post(
        "/api/admin/auth/magic/request", json={"email": "admin@example.com"}
    )
    token, email = _extract_magic_params(request_resp.json()["url"])
    admin_errors_client.get(
        "/api/admin/auth/magic/verify",
        params={"token": token, "email": email},
        follow_redirects=False,
    )

    resp = admin_errors_client.get("/api/admin/seed-error")
    assert resp.status_code == 200
    assert resp.json() == {"error": "seed import failed; see logs"}


# ---------------------------------------------------------------------------
# Shared CRUD helpers
# ---------------------------------------------------------------------------


def test_require_fresh_accepts_matching_timestamp():
    now = datetime(2026, 10, 14, 8, 0, 0, tzinfo=UTC)
    FakeEntity = type("Landmark", (), {"id": 1, "updated_at": now})
    require_fresh(FakeEntity(), now)


def test_require_fresh_rejects_stale_timestamp():
    now = datetime(2026, 10, 14, 8, 0, 0, tzinfo=UTC)
    FakeEntity = type("Landmark", (), {"id": 1, "updated_at": now})
    seen_at = now - timedelta(seconds=5)
    with pytest.raises(ConflictError) as exc_info:
        require_fresh(FakeEntity(), seen_at)
    assert exc_info.value.entity == "Landmark"
    assert exc_info.value.current == {"id": 1, "updated_at": now}


def test_handle_integrity_maps_postgres_team_name_constraint():
    orig = Exception(
        'duplicate key value violates unique constraint "uq_teams_host_name" '
        "DETAIL: Key (host_id, name)=(h1, T1) already exists."
    )
    err = IntegrityError("statement", {}, orig)
    result = handle_integrity(err, {"key": "key", "name": "name"})
    assert len(result.errors) == 1
    assert result.errors[0].field == "name"
    assert "already exists" in result.errors[0].message


def test_handle_integrity_maps_sqlite_team_key_constraint():
    orig = Exception("UNIQUE constraint failed: teams.host_id, teams.key")
    err = IntegrityError("statement", {}, orig)
    result = handle_integrity(err, {"key": "key", "name": "name"})
    assert len(result.errors) == 1
    assert result.errors[0].field == "key"
    assert "already exists" in result.errors[0].message


def test_handle_integrity_falls_back_to_generic_database_constraint():
    orig = Exception("some other integrity failure")
    err = IntegrityError("statement", {}, orig)
    result = handle_integrity(err, {"key": "key", "name": "name"})
    assert len(result.errors) == 1
    assert result.errors[0].field == ""
    assert result.errors[0].message == "database constraint failed"
