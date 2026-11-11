from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import EmailStr, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_ENTRA_FIELDS = (
    "admin_entra_tenant_id",
    "admin_entra_client_id",
    "admin_entra_client_secret",
    "admin_entra_redirect_uri",
    "admin_entra_group_object_id",
)
MIN_BOOTSTRAP_PASSWORD_LENGTH = 12


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str
    database_auth: Literal["password", "azure_ad"] = "password"
    database_owner_role: str | None = None  # prod: NOLOGIN role that owns the tables (db-setup)
    host_id: str = "default"
    public_base_url: str
    storage_backend: Literal["azure", "local"] = "azure"
    azure_storage_connection_string: str | None = None
    azure_storage_account_url: str | None = None
    local_storage_dir: Path = Path(".storage")
    photos_container: str = "photos"
    images_container: str = "images"
    albums_container: str = "albums"  # stored memories-album PDFs (issue #33)
    static_dir: Path | None = None
    max_photo_bytes: int = 20 * 1024 * 1024
    # Version shown by /api/health; unset, the packaged VERSION file is used (questtour/version.py).
    app_version: str | None = None

    # Admin auth / session settings
    admin_auth_provider: Literal["dev", "password", "entra"] = "dev"
    admin_session_secret: str = "dev-secret-do-not-use-in-production-with-claude-code"
    admin_session_max_age_minutes: int = 12 * 60
    admin_session_secure: bool = False

    admin_entra_tenant_id: str | None = None
    admin_entra_client_id: str | None = None
    admin_entra_client_secret: str | None = None
    admin_entra_redirect_uri: str | None = None
    admin_entra_group_object_id: str | None = None

    # Not required by Settings itself (alembic, sync-config and CLIs build it without them);
    # startup_problems() reports them missing in "password" mode and create_app refuses to start.
    admin_bootstrap_email: EmailStr | None = None
    admin_bootstrap_password: SecretStr | None = None

    # NoDecode: the env source hands the raw string to _split_admin_dev_emails
    # (comma-separated per .env.example) instead of JSON-decoding it first.
    admin_dev_emails: Annotated[list[str], NoDecode] = []
    config_dir: Path = Path("config")

    # Game play requests (issue #61): the public form on the website posts to /api/public/*.
    # Origin of the website (no trailing slash); CORS for /api/public is enabled only when set.
    public_site_origin: str | None = None
    request_max_teams: int = 10
    request_max_pending: int = 50
    request_max_per_hour: int = 20
    request_retention_days: int = 30  # decided requests are purged this long after the decision
    request_min_fill_seconds: int = Field(3, ge=0)
    request_challenge_max_number: int = 50000  # proof-of-work difficulty
    request_challenge_secret: str = "dev-request-challenge-secret-do-not-use-in-production"
    default_exit_message: str = ""

    @field_validator("admin_session_secret")
    @classmethod
    def _validate_admin_session_secret(cls, value: str) -> str:
        if len(value) < 32:
            raise ValueError("admin_session_secret must be at least 32 characters")
        return value

    @field_validator("request_challenge_secret")
    @classmethod
    def _validate_request_challenge_secret(cls, value: str) -> str:
        if len(value) < 32:
            raise ValueError("request_challenge_secret must be at least 32 characters")
        return value

    @field_validator("public_site_origin", mode="before")
    @classmethod
    def _normalize_public_site_origin(cls, value):
        if isinstance(value, str):
            return value.strip().rstrip("/") or None
        return value

    @field_validator("admin_dev_emails", mode="before")
    @classmethod
    def _split_admin_dev_emails(cls, value):
        if isinstance(value, str):
            return [email.strip() for email in value.split(",") if email.strip()]
        return value

    @field_validator(
        "admin_bootstrap_email", "admin_bootstrap_password", *_ENTRA_FIELDS, mode="before"
    )
    @classmethod
    def _empty_to_none(cls, value):
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("admin_bootstrap_password")
    @classmethod
    def _validate_bootstrap_password(cls, value):
        if value is not None and len(value.get_secret_value()) < MIN_BOOTSTRAP_PASSWORD_LENGTH:
            raise ValueError("ADMIN_BOOTSTRAP_PASSWORD must be at least 12 characters")
        return value

    @model_validator(mode="after")
    def _validate_entra_config(self):
        if self.admin_auth_provider == "entra":
            missing = [field for field in _ENTRA_FIELDS if not getattr(self, field)]
            if missing:
                raise ValueError(f"admin_auth_provider='entra' requires: {', '.join(missing)}")
        return self

    @property
    def entra_configured(self) -> bool:
        return all(getattr(self, field) for field in _ENTRA_FIELDS)

    def startup_problems(self) -> list[str]:
        if self.admin_auth_provider != "password":
            return []
        hint = " (existing Entra deployments: set the GitHub variable ADMIN_AUTH_PROVIDER=entra)"
        problems = []
        if not self.admin_bootstrap_email:
            problems.append(
                "ADMIN_BOOTSTRAP_EMAIL is required when ADMIN_AUTH_PROVIDER=password" + hint
            )
        if not self.admin_bootstrap_password:
            problems.append(
                "ADMIN_BOOTSTRAP_PASSWORD is required when ADMIN_AUTH_PROVIDER=password" + hint
            )
        return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()
