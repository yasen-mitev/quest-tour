import io
import logging
from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from alembic import command
from questtour import models  # noqa: F401
from questtour.db import Base

BACKEND = Path(__file__).resolve().parents[1]


def test_migration_matches_models(tmp_path):
    url = f"sqlite:///{tmp_path / 'm.db'}"
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    with create_engine(url).connect() as conn:
        ctx = MigrationContext.configure(conn, opts={"compare_type": False})
        diffs = [d for d in compare_metadata(ctx, Base.metadata)]
    assert diffs == []


def test_photo_deleted_at_is_nullable_and_indexed(tmp_path):
    url = f"sqlite:///{tmp_path / 'm.db'}"
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    engine = create_engine(url)
    inspector = inspect(engine)
    columns = {c["name"]: c for c in inspector.get_columns("photos")}
    assert columns["deleted_at"]["nullable"] is True
    indexes = {idx["name"] for idx in inspector.get_indexes("photos")}
    assert "ix_photos_deleted_at" in indexes


def test_admin_tables_exist_at_head(tmp_path):
    url = f"sqlite:///{tmp_path / 'a.db'}"
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    tables = inspect(create_engine(url)).get_table_names()
    assert "admin_users" in tables
    assert "app_settings" in tables


def test_sqlite_upgrade_emits_no_native_alter_column(tmp_path):
    """SQLite cannot run ``ALTER TABLE ... ALTER COLUMN ... SET NOT NULL`` (only added in
    SQLite >= 3.53; ubuntu-latest runners ship an older sqlite3). Migrations must use the
    batch table-rebuild strategy instead, which every supported SQLite version can run."""
    url = f"sqlite:///{tmp_path / 'p.db'}"
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logger = logging.getLogger("sqlalchemy.engine")
    previous_level = logger.level
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    try:
        command.upgrade(cfg, "head")
    finally:
        handler.close()
        logger.removeHandler(handler)
        logger.setLevel(previous_level)

    ddl = stream.getvalue()
    assert "ALTER COLUMN" not in ddl
    assert "_alembic_tmp" in ddl  # batch table-rebuild actually ran, not a silent no-op


def _alembic_cfg(url: str) -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def test_game_requests_table_and_requestable_column_at_head(tmp_path):
    url = f"sqlite:///{tmp_path / 'r.db'}"
    command.upgrade(_alembic_cfg(url), "head")
    inspector = inspect(create_engine(url))

    columns = {c["name"]: c for c in inspector.get_columns("game_requests")}
    assert set(columns) == {
        "id", "host_id", "game_id", "play_date", "teams", "contact_name", "contact_email",
        "contact_phone", "message", "exit_message", "status", "terms_accepted_at",
        "terms_version", "challenge", "decided_at", "decided_by", "created_at", "updated_at",
    }
    assert columns["game_id"]["nullable"] is True
    assert columns["contact_email"]["nullable"] is True
    assert columns["decided_at"]["nullable"] is True
    assert columns["challenge"]["nullable"] is False
    assert columns["created_at"]["nullable"] is False
    uniques = {u["name"]: u["column_names"] for u in inspector.get_unique_constraints("game_requests")}
    assert uniques["uq_game_requests_challenge"] == ["challenge"]
    indexes = {i["name"]: i["column_names"] for i in inspector.get_indexes("game_requests")}
    assert indexes["ix_game_requests_host_status"] == ["host_id", "status"]
    fks = inspector.get_foreign_keys("game_requests")
    assert [(f["referred_table"], f["options"].get("ondelete")) for f in fks] == [
        ("games", "SET NULL")
    ]

    requestable = {c["name"]: c for c in inspector.get_columns("games")}["requestable"]
    assert requestable["nullable"] is False


def test_requestable_defaults_to_false_for_existing_games(tmp_path):
    url = f"sqlite:///{tmp_path / 'd.db'}"
    cfg = _alembic_cfg(url)
    command.upgrade(cfg, "0008")
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO games (host_id, key, name, intro, time_zone, max_duration_minutes, "
            "reveal_after_attempts, reveal_after_minutes, reveal_penalty_minutes, updated_at) "
            "VALUES ('default', 'g', 'G', 'i', 'UTC', 60, 5, 20, 30, '2026-01-01 00:00:00')"
        )
    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT requestable FROM games").scalar() in (0, False)


def test_game_requests_downgrade_removes_table_and_column(tmp_path):
    url = f"sqlite:///{tmp_path / 'x.db'}"
    cfg = _alembic_cfg(url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0008")
    inspector = inspect(create_engine(url))
    assert "game_requests" not in inspector.get_table_names()
    assert "requestable" not in {c["name"] for c in inspector.get_columns("games")}
    command.upgrade(cfg, "head")  # and back up again
    assert "game_requests" in inspect(create_engine(url)).get_table_names()


def test_upgrade_head_with_password_mode_env_without_credentials(tmp_path, monkeypatch):
    """Running migrations must not depend on the app's startup checks (no bootstrap credentials)."""
    from questtour.settings import get_settings

    monkeypatch.setenv("ADMIN_AUTH_PROVIDER", "password")
    monkeypatch.delenv("ADMIN_BOOTSTRAP_EMAIL", raising=False)
    monkeypatch.delenv("ADMIN_BOOTSTRAP_PASSWORD", raising=False)
    get_settings.cache_clear()
    try:
        url = f"sqlite:///{tmp_path / 'pw.db'}"
        cfg = Config(str(BACKEND / "alembic.ini"))
        cfg.set_main_option("script_location", str(BACKEND / "alembic"))
        cfg.set_main_option("sqlalchemy.url", url)
        command.upgrade(cfg, "head")
        assert "admin_users" in inspect(create_engine(url)).get_table_names()
    finally:
        get_settings.cache_clear()
