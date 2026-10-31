import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from questtour.main import create_app
from questtour.settings import Settings

BOSS = "boss@example.com"
BOSS_PW = "correct-horse-battery"
ENTRA = {
    "admin_entra_tenant_id": "t",
    "admin_entra_client_id": "c",
    "admin_entra_client_secret": "s",
    "admin_entra_redirect_uri": "http://test/api/admin/auth/callback",
    "admin_entra_group_object_id": "g",
}
BASE = "/api/admin/account"


def _settings(tmp_path, **kw):
    return Settings(
        _env_file=None,
        database_url="sqlite://",
        public_base_url="http://test",
        admin_session_secret="a" * 32,
        storage_backend="local",
        local_storage_dir=tmp_path / "b",
        config_dir=tmp_path / "none",
        **kw,
    )


def _password_settings(tmp_path, **kw):
    return _settings(
        tmp_path,
        admin_auth_provider="password",
        admin_bootstrap_email=BOSS,
        admin_bootstrap_password=BOSS_PW,
        **kw,
    )


def _client(settings, session_factory, blob_store):
    app = create_app(settings, session_factory=session_factory, blob_store=blob_store)

    @app.get("/test-login/{provider}")
    def _test_login(provider: str, request: Request):
        request.session["admin"] = {"email": "ent@example.com", "provider": provider}
        return {"ok": True}

    return TestClient(app)


def _login(c, email=BOSS, password=BOSS_PW):
    return c.post("/api/admin/auth/password", json={"email": email, "password": password})


@pytest.fixture
def client(tmp_path, session_factory, blob_store):
    with _client(_password_settings(tmp_path), session_factory, blob_store) as c:
        assert _login(c).status_code == 200
        yield c


@pytest.fixture
def entra_session_client(tmp_path, session_factory, blob_store):
    s = _password_settings(tmp_path, **ENTRA)
    with _client(s, session_factory, blob_store) as c:
        c.get("/test-login/entra")
        yield c


def test_requires_session(tmp_path, session_factory, blob_store):
    with _client(_password_settings(tmp_path), session_factory, blob_store) as c:
        assert c.get(f"{BASE}/auth-settings").status_code == 401
        assert c.get(f"{BASE}/admins").status_code == 401
        assert c.post(f"{BASE}/password", json={}).status_code == 401


def test_auth_settings_reports_mode_and_session_provider(client):
    assert client.get(f"{BASE}/auth-settings").json() == {
        "mode": "password",
        "entra_configured": False,
        "entra_enabled": False,
        "session_provider": "password",
    }


def test_change_password_round_trip(client):
    new = "a-brand-new-password"
    resp = client.post(f"{BASE}/password", json={"current_password": BOSS_PW, "new_password": new})
    assert resp.status_code == 200
    other = TestClient(client.app)
    assert _login(other).status_code == 400
    assert _login(other, password=new).status_code == 200


def test_change_password_wrong_current_is_400(client):
    resp = client.post(
        f"{BASE}/password", json={"current_password": "nope-nope-nope", "new_password": "x" * 12}
    )
    assert resp.status_code == 400
    assert client.get(f"{BASE}/auth-settings").status_code == 200  # session untouched


def test_change_password_short_new_is_422(client):
    resp = client.post(
        f"{BASE}/password", json={"current_password": BOSS_PW, "new_password": "short"}
    )
    assert resp.status_code == 422
    assert resp.json()["errors"][0]["field"].endswith("new_password")


def test_add_list_delete_admins(client):
    resp = client.post(f"{BASE}/admins", json={"email": "Two@Example.com", "password": "x" * 12})
    assert resp.status_code == 200
    created = resp.json()
    assert created["email"] == "two@example.com" and created["is_bootstrap"] is False
    listed = client.get(f"{BASE}/admins").json()
    assert [a["email"] for a in listed] == [BOSS, "two@example.com"]
    assert "password_hash" not in listed[0]
    assert _login(TestClient(client.app), "two@example.com", "x" * 12).status_code == 200
    assert client.delete(f"{BASE}/admins/{created['id']}").status_code == 200
    assert len(client.get(f"{BASE}/admins").json()) == 1
    assert client.delete(f"{BASE}/admins/{created['id']}").status_code == 404


def test_duplicate_admin_is_409_case_insensitive(client):
    resp = client.post(f"{BASE}/admins", json={"email": "BOSS@example.com", "password": "x" * 12})
    assert resp.status_code == 409


def test_cannot_delete_self(client):
    client.post(f"{BASE}/admins", json={"email": "two@example.com", "password": "x" * 12})
    me = next(a for a in client.get(f"{BASE}/admins").json() if a["email"] == BOSS)
    assert client.delete(f"{BASE}/admins/{me['id']}").status_code == 409


def test_reset_another_admins_password(client):
    created = client.post(
        f"{BASE}/admins", json={"email": "two@example.com", "password": "x" * 12}
    ).json()
    resp = client.put(
        f"{BASE}/admins/{created['id']}/password", json={"password": "reset-pass-123"}
    )
    assert resp.status_code == 200
    other = TestClient(client.app)
    assert _login(other, "two@example.com", "x" * 12).status_code == 400
    assert _login(other, "two@example.com", "reset-pass-123").status_code == 200
    assert (
        client.put(f"{BASE}/admins/9999/password", json={"password": "y" * 12}).status_code == 404
    )
    assert (
        client.put(f"{BASE}/admins/{created['id']}/password", json={"password": "s"}).status_code
        == 422
    )


def test_entra_session_is_forbidden_from_password_and_admin_routes(entra_session_client):
    c = entra_session_client
    assert c.get(f"{BASE}/auth-settings").json()["session_provider"] == "entra"
    body = {"current_password": "x", "new_password": "y" * 12}
    assert c.post(f"{BASE}/password", json=body).status_code == 403
    assert c.get(f"{BASE}/admins").status_code == 403
    new_admin = {"email": "a@example.com", "password": "y" * 12}
    assert c.post(f"{BASE}/admins", json=new_admin).status_code == 403
    assert c.delete(f"{BASE}/admins/1").status_code == 403
    assert c.put(f"{BASE}/admins/1/password", json={"password": "y" * 12}).status_code == 403


def test_enable_entra_when_unconfigured_is_409(client):
    assert client.put(f"{BASE}/auth-settings", json={"entra_enabled": True}).status_code == 409


def test_toggle_entra_persists_and_flips_login_methods(tmp_path, session_factory, blob_store):
    s = _password_settings(tmp_path, **ENTRA)
    with _client(s, session_factory, blob_store) as c:
        assert _login(c).status_code == 200
        assert c.get("/api/admin/auth/provider").json()["methods"]["entra"] is False
        assert c.put(f"{BASE}/auth-settings", json={"entra_enabled": True}).status_code == 200
        assert c.get(f"{BASE}/auth-settings").json()["entra_enabled"] is True
        assert c.get("/api/admin/auth/provider").json()["methods"]["entra"] is True
        assert c.put(f"{BASE}/auth-settings", json={"entra_enabled": False}).status_code == 200
        assert c.get("/api/admin/auth/provider").json()["methods"]["entra"] is False


def test_entra_mode_disable_hides_entra_but_password_still_works(
    tmp_path, session_factory, blob_store
):
    s = _settings(
        tmp_path,
        admin_auth_provider="entra",
        admin_bootstrap_email=BOSS,
        admin_bootstrap_password=BOSS_PW,
        **ENTRA,
    )
    with _client(s, session_factory, blob_store) as c:
        assert _login(c).status_code == 200
        assert c.get("/api/admin/auth/provider").json()["methods"]["entra"] is True
        assert c.put(f"{BASE}/auth-settings", json={"entra_enabled": False}).status_code == 200
        assert c.get("/api/admin/auth/provider").json()["methods"]["entra"] is False
        assert _login(TestClient(c.app)).status_code == 200


def test_disable_entra_with_no_admin_rows_is_409(tmp_path, session_factory, blob_store):
    s = _settings(tmp_path, admin_auth_provider="entra", **ENTRA)
    with _client(s, session_factory, blob_store) as c:
        c.get("/test-login/entra")
        assert c.put(f"{BASE}/auth-settings", json={"entra_enabled": False}).status_code == 409


def test_toggle_in_dev_mode_is_409(tmp_path, session_factory, blob_store):
    s = _settings(tmp_path, admin_auth_provider="dev", admin_dev_emails=["dev@example.com"])
    with _client(s, session_factory, blob_store) as c:
        c.get("/test-login/dev")
        assert c.put(f"{BASE}/auth-settings", json={"entra_enabled": True}).status_code == 409
