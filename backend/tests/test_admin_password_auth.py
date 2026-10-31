from typing import Annotated
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from questtour.auth import AdminSession, auth_router, require_admin
from questtour.auth.passwords import (
    ENTRA_FLAG,
    LoginThrottle,
    auth_methods,
    get_flag,
    hash_password,
    seed_auth_state,
    set_flag,
    verify_password,
)
from questtour.models import AdminUser
from questtour.settings import Settings

ENTRA = {
    "admin_entra_tenant_id": "tenant-id",
    "admin_entra_client_id": "client-id",
    "admin_entra_client_secret": "secret",
    "admin_entra_redirect_uri": "http://test/api/admin/auth/callback",
    "admin_entra_group_object_id": "group-id",
}
CREDS = {
    "admin_bootstrap_email": "Boss@Example.com",
    "admin_bootstrap_password": "correct-horse-battery",
}


def make_settings(provider: str, *, entra: bool = False, creds: bool = True, **kw) -> Settings:
    return Settings(
        _env_file=None,
        database_url="sqlite://",
        public_base_url="http://test",
        admin_session_secret="test-secret-must-be-at-least-32-bytes-long",
        admin_auth_provider=provider,
        **(ENTRA if entra else {}),
        **(CREDS if creds else {}),
        **kw,
    )


def test_seed_creates_bootstrap_once_and_never_overwrites(session_factory):
    settings = make_settings("password")
    with session_factory() as s:
        seed_auth_state(s, settings)
        user = s.query(AdminUser).one()
        assert user.email == "boss@example.com" and user.is_bootstrap
        user.password_hash = hash_password("changed-in-console-1")
        s.commit()
        seed_auth_state(s, settings)
        assert s.query(AdminUser).count() == 1
        assert verify_password(s, "BOSS@example.com", "changed-in-console-1")
        assert verify_password(s, "boss@example.com", "correct-horse-battery") is None


def test_seed_does_not_recreate_a_bootstrap_admin_removed_in_the_console(session_factory):
    settings = make_settings("password")
    with session_factory() as s:
        seed_auth_state(s, settings)
        s.delete(s.query(AdminUser).one())
        s.commit()
        seed_auth_state(s, settings)
        assert s.query(AdminUser).count() == 0


def test_seed_still_seeds_a_changed_bootstrap_email(session_factory):
    with session_factory() as s:
        seed_auth_state(s, make_settings("password"))
        s.delete(s.query(AdminUser).one())
        s.commit()
        seed_auth_state(
            s,
            make_settings(
                "password",
                creds=False,
                admin_bootstrap_email="new@example.com",
                admin_bootstrap_password="another-long-password-1",
            ),
        )
        assert [u.email for u in s.query(AdminUser)] == ["new@example.com"]


def test_seed_marks_an_existing_bootstrap_row_so_a_later_removal_sticks(session_factory):
    settings = make_settings("password")
    with session_factory() as s:
        s.add(AdminUser(email="boss@example.com", is_bootstrap=True, password_hash="x"))
        s.commit()
        seed_auth_state(s, settings)  # upgrade path: row predates the marker
        s.delete(s.query(AdminUser).one())
        s.commit()
        seed_auth_state(s, settings)
        assert s.query(AdminUser).count() == 0


def test_entra_mode_seeds_flag_and_keeps_entra_after_switch_to_password(session_factory):
    with session_factory() as s:
        seed_auth_state(s, make_settings("entra", entra=True))
        assert get_flag(s, ENTRA_FLAG) is True
        assert auth_methods(make_settings("password", entra=True), s) == {
            "password": True,
            "entra": True,
            "dev": False,
        }


def test_seed_does_not_override_an_entra_toggle_the_admin_turned_off(session_factory):
    with session_factory() as s:
        set_flag(s, ENTRA_FLAG, False)
        seed_auth_state(s, make_settings("entra", entra=True))
        assert get_flag(s, ENTRA_FLAG) is False


@pytest.mark.parametrize(
    ("provider", "entra", "flag", "expected_entra"),
    [
        ("password", False, None, False),
        ("password", True, None, False),
        ("password", True, True, True),
        ("password", False, True, False),
        ("entra", True, None, True),
        ("entra", True, False, False),
    ],
)
def test_auth_methods_matrix(session_factory, provider, entra, flag, expected_entra):
    with session_factory() as s:
        if flag is not None:
            set_flag(s, ENTRA_FLAG, flag)
        m = auth_methods(make_settings(provider, entra=entra), s)
        assert m == {"password": True, "entra": expected_entra, "dev": False}


def test_auth_methods_without_db_uses_defaults():
    assert auth_methods(make_settings("dev", creds=False), None) == {
        "password": False,
        "entra": False,
        "dev": True,
    }
    assert auth_methods(make_settings("entra", entra=True), None)["entra"] is True
    assert auth_methods(make_settings("password", entra=True), None)["entra"] is False


def test_verify_rejects_wrong_password_and_unknown_email(session_factory):
    with session_factory() as s:
        seed_auth_state(s, make_settings("password"))
        assert verify_password(s, "boss@example.com", "wrong-password-123") is None
        assert verify_password(s, "nobody@example.com", "correct-horse-battery") is None


def test_throttle_blocks_after_limit_and_expires():
    now = [0.0]
    t = LoginThrottle(limit=2, window=10.0, clock=lambda: now[0])
    t.fail("k")
    t.fail("k")
    assert t.blocked("k") and not t.blocked("other")
    now[0] = 11.0
    assert not t.blocked("k")
    t.fail("k")
    t.clear("k")
    assert not t.blocked("k")


# --- router-level behaviour -------------------------------------------------------------------

GOOD = {"email": "boss@example.com", "password": "correct-horse-battery"}


def build_app(settings: Settings, session_factory=None) -> FastAPI:
    app = FastAPI()
    app.state.settings = settings
    if session_factory is not None:
        app.state.session_factory = session_factory
        with session_factory() as s:
            seed_auth_state(s, settings)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.admin_session_secret,
        session_cookie="questtour_admin_session",
        same_site="lax",
        https_only=settings.admin_session_secure,
    )
    app.include_router(auth_router)

    @app.get("/api/admin/protected")
    def protected(admin: Annotated[AdminSession, Depends(require_admin)]):
        return admin

    return app


@pytest.fixture
def password_client(session_factory):
    return TestClient(build_app(make_settings("password"), session_factory))


def test_password_login_sets_session(password_client):
    assert password_client.post("/api/admin/auth/password", json=GOOD).json() == {"ok": True}
    me = password_client.get("/api/admin/protected")
    assert me.status_code == 200
    assert me.json() == {"email": "boss@example.com", "provider": "password"}


def test_password_login_failures_share_one_body(password_client):
    for body in (
        {**GOOD, "password": "wrong-password-123"},
        {"email": "nobody@example.com", "password": GOOD["password"]},
    ):
        resp = password_client.post("/api/admin/auth/password", json=body)
        assert resp.status_code == 400
        assert resp.json() == {"detail": "invalid email or password"}


def test_password_login_throttles_after_five_failures(password_client):
    bad = {**GOOD, "password": "wrong-password-123"}
    assert [
        password_client.post("/api/admin/auth/password", json=bad).status_code for _ in range(5)
    ] == [400] * 5
    assert password_client.post("/api/admin/auth/password", json=bad).status_code == 429
    assert password_client.post("/api/admin/auth/password", json=GOOD).status_code == 429


def test_password_session_dies_when_admin_row_is_deleted(password_client, session_factory):
    password_client.post("/api/admin/auth/password", json=GOOD)
    with session_factory() as s:
        s.query(AdminUser).delete()
        s.commit()
    assert password_client.get("/api/admin/protected").status_code == 401


def test_password_endpoint_is_404_in_dev_mode(session_factory):
    client = TestClient(build_app(make_settings("dev", creds=False), session_factory))
    assert client.post("/api/admin/auth/password", json=GOOD).status_code == 404


def test_password_mode_without_session_factory_is_503():
    client = TestClient(build_app(make_settings("password")))
    assert client.post("/api/admin/auth/password", json=GOOD).status_code == 503


def test_password_login_works_in_entra_mode(session_factory):
    client = TestClient(build_app(make_settings("entra", entra=True), session_factory))
    assert client.post("/api/admin/auth/password", json=GOOD).status_code == 200


def test_entra_login_allowed_when_configured_and_flag_on(session_factory):
    client = TestClient(build_app(make_settings("entra", entra=True), session_factory))
    with patch(
        "questtour.auth.entra.EntraAuthProvider.login_url",
        new=AsyncMock(return_value="http://idp/authorize"),
    ):
        resp = client.get("/api/admin/auth/login", follow_redirects=False)
    assert resp.status_code == 307 and resp.headers["location"] == "http://idp/authorize"


def test_entra_login_and_callback_404_when_flag_off(session_factory):
    client = TestClient(build_app(make_settings("entra", entra=True), session_factory))
    with session_factory() as s:
        set_flag(s, ENTRA_FLAG, False)
    assert client.get("/api/admin/auth/login").status_code == 404
    assert client.get("/api/admin/auth/callback?code=a&state=b").status_code == 404
    assert client.get("/api/admin/auth/provider").json()["methods"]["entra"] is False


def test_password_mode_with_entra_config_but_flag_off_has_no_entra_login(session_factory):
    client = TestClient(build_app(make_settings("password", entra=True), session_factory))
    assert client.get("/api/admin/auth/login").status_code == 404
