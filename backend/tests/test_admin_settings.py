from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from questtour.main import create_app
from questtour.settings import Settings


def test_settings_validates_admin_fields():
    settings = Settings(
        _env_file=None,
        database_url="sqlite://",
        public_base_url="http://test",
        admin_auth_provider="dev",
        admin_session_secret="a" * 32,
        admin_session_max_age_minutes=720,
        admin_session_secure=False,
        admin_dev_emails=["admin@example.com"],
        config_dir="config",
    )
    assert settings.admin_auth_provider == "dev"
    assert settings.admin_session_secret == "a" * 32
    assert settings.admin_session_max_age_minutes == 720
    assert settings.admin_session_secure is False
    assert settings.admin_dev_emails == ["admin@example.com"]
    assert settings.config_dir == Path("config")


def test_settings_rejects_short_session_secret():
    with pytest.raises(ValueError):
        Settings(
            _env_file=None,
            database_url="sqlite://",
            public_base_url="http://test",
            admin_session_secret="short",
        )


def test_settings_entra_requires_all_fields():
    with pytest.raises(ValueError):
        Settings(
            _env_file=None,
            database_url="sqlite://",
            public_base_url="http://test",
            admin_auth_provider="entra",
            admin_entra_tenant_id="tenant",
            # missing other entra fields
        )


def test_settings_splits_admin_dev_emails_from_string():
    settings = Settings(
        _env_file=None,
        database_url="sqlite://",
        public_base_url="http://test",
        admin_dev_emails="a@example.com,b@example.com",
    )
    assert settings.admin_dev_emails == ["a@example.com", "b@example.com"]


def test_settings_splits_admin_dev_emails_from_env(monkeypatch):
    # The env/.env source must honor the documented comma-separated format too,
    # not only values passed as init arguments.
    monkeypatch.setenv("ADMIN_DEV_EMAILS", "a@example.com,b@example.com")
    settings = Settings(
        _env_file=None,
        database_url="sqlite://",
        public_base_url="http://test",
    )
    assert settings.admin_dev_emails == ["a@example.com", "b@example.com"]


def test_create_app_exposes_seed_error_and_session_middleware(
    settings, session_factory, blob_store, clock
):
    # Point config_dir at a non-existent path so the seed lifespan does not run.
    settings.config_dir = settings.local_storage_dir / "no-config"

    app = create_app(settings, session_factory=session_factory, blob_store=blob_store, clock=clock)
    middleware_classes = [m.cls for m in app.user_middleware]
    assert SessionMiddleware in middleware_classes

    # TestClient enters the lifespan, which exposes seed_error on app.state.
    with TestClient(app):
        assert hasattr(app.state, "seed_error")
        assert app.state.seed_error is None


def _base(**kw):
    return dict(
        _env_file=None,
        database_url="sqlite://",
        public_base_url="http://test",
        admin_session_secret="a" * 32,
        **kw,
    )


def test_default_provider_stays_dev_and_needs_no_credentials():
    s = Settings(**_base())
    assert s.admin_auth_provider == "dev" and s.startup_problems() == []


def test_password_mode_constructs_without_credentials_but_reports_problems():
    s = Settings(**_base(admin_auth_provider="password"))
    problems = s.startup_problems()
    assert any("ADMIN_BOOTSTRAP_EMAIL" in p for p in problems)
    assert any("ADMIN_BOOTSTRAP_PASSWORD" in p for p in problems)


def test_password_mode_with_credentials_is_ready():
    s = Settings(
        **_base(
            admin_auth_provider="password",
            admin_bootstrap_email="Boss@Example.com",
            admin_bootstrap_password="correct-horse-battery",
        )
    )
    assert s.startup_problems() == []
    assert s.admin_bootstrap_password.get_secret_value() == "correct-horse-battery"


def test_short_bootstrap_password_rejected():
    with pytest.raises(ValueError, match="at least 12"):
        Settings(**_base(admin_bootstrap_password="short"))


def test_invalid_bootstrap_email_rejected():
    with pytest.raises(ValueError):
        Settings(**_base(admin_bootstrap_email="not-an-email"))


def test_empty_strings_are_treated_as_unset():
    s = Settings(
        **_base(admin_bootstrap_email="", admin_bootstrap_password="", admin_entra_tenant_id="")
    )
    assert s.admin_bootstrap_email is None and s.admin_bootstrap_password is None
    assert s.admin_entra_tenant_id is None


def test_entra_configured_requires_all_five_fields():
    full = {
        "admin_entra_tenant_id": "t",
        "admin_entra_client_id": "c",
        "admin_entra_client_secret": "s",
        "admin_entra_redirect_uri": "http://test/api/admin/auth/callback",
        "admin_entra_group_object_id": "g",
    }
    assert Settings(**_base(admin_auth_provider="password", **full)).entra_configured is True
    assert (
        Settings(**_base(admin_auth_provider="password", admin_entra_tenant_id="t")).entra_configured
        is False
    )


def test_entra_mode_still_requires_entra_fields_but_not_password():
    with pytest.raises(ValueError, match="admin_entra_tenant_id"):
        Settings(**_base(admin_auth_provider="entra"))


def test_create_app_refuses_password_mode_without_credentials(session_factory, blob_store, tmp_path):
    s = Settings(
        **_base(
            admin_auth_provider="password",
            storage_backend="local",
            local_storage_dir=tmp_path / "b",
            config_dir=tmp_path / "none",
        )
    )
    with pytest.raises(RuntimeError, match="ADMIN_BOOTSTRAP_EMAIL"):
        create_app(s, session_factory=session_factory, blob_store=blob_store)


def test_create_app_in_password_mode_seeds_bootstrap_admin(session_factory, blob_store, tmp_path):
    s = Settings(
        **_base(
            admin_auth_provider="password",
            storage_backend="local",
            local_storage_dir=tmp_path / "b",
            config_dir=tmp_path / "none",
            admin_bootstrap_email="boss@example.com",
            admin_bootstrap_password="correct-horse-battery",
        )
    )
    with TestClient(create_app(s, session_factory=session_factory, blob_store=blob_store)) as c:
        resp = c.post(
            "/api/admin/auth/password",
            json={"email": "boss@example.com", "password": "correct-horse-battery"},
        )
        assert resp.status_code == 200


def test_create_app_in_entra_mode_starts_without_credentials(session_factory, blob_store, tmp_path):
    s = Settings(
        **_base(
            admin_auth_provider="entra",
            storage_backend="local",
            local_storage_dir=tmp_path / "b",
            config_dir=tmp_path / "none",
            admin_entra_tenant_id="t",
            admin_entra_client_id="c",
            admin_entra_client_secret="s",
            admin_entra_redirect_uri="http://test/api/admin/auth/callback",
            admin_entra_group_object_id="g",
        )
    )
    with TestClient(create_app(s, session_factory=session_factory, blob_store=blob_store)) as c:
        assert c.get("/api/admin/auth/provider").json()["methods"] == {
            "password": True,
            "entra": True,
            "dev": False,
        }
