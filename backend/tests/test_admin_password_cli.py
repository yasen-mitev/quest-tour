import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from questtour.auth.passwords import find_admin, hash_password, verify_password
from questtour.cli import admin_password
from questtour.models import AdminUser
from questtour.settings import Settings

OLD = "old-password-123"
NEW = "brand-new-password-1"


@pytest.fixture
def run_cli(monkeypatch, engine):
    settings = Settings(
        _env_file=None,
        database_url="sqlite://",
        public_base_url="http://test",
        admin_session_secret="a" * 32,
        admin_auth_provider="password",
    )
    monkeypatch.setattr(admin_password, "get_settings", lambda: settings)
    monkeypatch.setattr(admin_password, "make_engine", lambda _settings: engine)

    def run(*prompts: str, email: str = "Boss@Example.com") -> int:
        answers = iter(prompts)
        monkeypatch.setattr(admin_password.getpass, "getpass", lambda _prompt="": next(answers))
        return admin_password.main(["--email", email])

    return run


def test_creates_a_new_admin(run_cli, engine):
    assert run_cli(NEW, NEW) == 0
    with Session(engine) as db:
        assert verify_password(db, "boss@example.com", NEW) is not None


def test_resets_an_existing_admin(run_cli, engine):
    with Session(engine) as db:
        db.add(AdminUser(email="boss@example.com", password_hash=hash_password(OLD)))
        db.commit()
    assert run_cli(NEW, NEW) == 0
    with Session(engine) as db:
        assert verify_password(db, "boss@example.com", OLD) is None
        assert verify_password(db, "boss@example.com", NEW) is not None
        assert len(db.scalars(select(AdminUser)).all()) == 1


@pytest.mark.parametrize("prompts", [(NEW, NEW + "x"), ("short",)])
def test_rejects_mismatched_or_short_password(run_cli, engine, prompts):
    with Session(engine) as db:
        db.add(AdminUser(email="boss@example.com", password_hash=hash_password(OLD)))
        db.commit()
    assert run_cli(*prompts) == 1
    with Session(engine) as db:
        assert verify_password(db, "boss@example.com", OLD) is not None
        assert find_admin(db, "other@example.com") is None
