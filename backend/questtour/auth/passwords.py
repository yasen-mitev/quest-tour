import hashlib
import threading
import time
from collections.abc import Callable

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from questtour.models import AdminUser, AppSetting
from questtour.settings import MIN_BOOTSTRAP_PASSWORD_LENGTH, Settings

_hasher = PasswordHasher()
_DUMMY_HASH = _hasher.hash("not-a-real-password")
MIN_PASSWORD_LENGTH = MIN_BOOTSTRAP_PASSWORD_LENGTH
ENTRA_FLAG = "entra_enabled"
BOOTSTRAP_SEEDED_PREFIX = "bootstrap_seeded:"


def normalize_email(email: str) -> str:
    return email.strip().casefold()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def find_admin(session: Session, email: str) -> AdminUser | None:
    return session.scalar(select(AdminUser).where(AdminUser.email == normalize_email(email)))


def verify_password(session: Session, email: str, password: str) -> AdminUser | None:
    """Return the admin on success, else None. Unknown emails still pay one hash verification."""
    user = find_admin(session, email)
    stored = user.password_hash if user else _DUMMY_HASH
    try:
        _hasher.verify(stored, password)
    except (VerifyMismatchError, InvalidHashError):
        return None
    if user is None:
        return None
    if _hasher.check_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
        session.commit()
    return user


def get_flag(session: Session, key: str, default: bool = False) -> bool:
    row = session.get(AppSetting, key)
    return default if row is None else row.value == "true"


def set_flag(session: Session, key: str, value: bool) -> None:
    row = session.get(AppSetting, key)
    if row is None:
        session.add(AppSetting(key=key, value="true" if value else "false"))
    else:
        row.value = "true" if value else "false"
    session.commit()


def seed_auth_state(session: Session, settings: Settings) -> None:
    """Startup seeding. Never overwrites: the admin may have changed the password / toggle.
    The bootstrap row is created once per email: a marker in app_settings outlives the row, so an
    admin removed in the console is not re-created (with the deployment password) on restart.
    A concurrent instance inserting the same row (overlapped restart) is not an error."""
    email, password = settings.admin_bootstrap_email, settings.admin_bootstrap_password
    if email and password:
        digest = hashlib.sha256(normalize_email(email).encode()).hexdigest()  # key fits String(100)
        marker = f"{BOOTSTRAP_SEEDED_PREFIX}{digest}"
        try:
            if find_admin(session, email) is None:
                if session.get(AppSetting, marker) is None:
                    session.add(
                        AdminUser(
                            email=normalize_email(email),
                            is_bootstrap=True,
                            password_hash=hash_password(password.get_secret_value()),
                        )
                    )
                    session.add(AppSetting(key=marker, value="true"))
                    session.commit()
            elif session.get(AppSetting, marker) is None:
                session.add(AppSetting(key=marker, value="true"))
                session.commit()
        except IntegrityError:
            session.rollback()
    # Upgraded legacy deployment: Entra stays on, and keeps staying on if the owner later
    # switches ADMIN_AUTH_PROVIDER to 'password'.
    if settings.admin_auth_provider == "entra" and session.get(AppSetting, ENTRA_FLAG) is None:
        try:
            set_flag(session, ENTRA_FLAG, True)
        except IntegrityError:
            session.rollback()


def auth_methods(settings: Settings, db: Session | None) -> dict[str, bool]:
    """Which sign-in methods the login screen may offer right now. `db` is None when the app has
    no session factory (bare test apps); flag defaults then apply."""
    mode = settings.admin_auth_provider
    if mode == "dev":
        return {"password": False, "entra": False, "dev": True}
    entra = settings.entra_configured and entra_flag(settings, db)
    return {"password": True, "entra": entra, "dev": False}


def entra_flag(settings: Settings, db: Session | None) -> bool:
    """The stored console toggle (default: on for `entra` mode, off for `password`)."""
    default = settings.admin_auth_provider == "entra"
    return default if db is None else get_flag(db, ENTRA_FLAG, default)


class LoginThrottle:
    """`limit` failures per key within `window` seconds -> blocked until the oldest ages out.
    In-memory, per process (the app runs as a single App Service instance)."""

    def __init__(
        self, limit: int = 5, window: float = 600.0, clock: Callable[[], float] = time.monotonic
    ):
        self.limit, self.window, self._clock = limit, window, clock
        self._fails: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str) -> list[float]:
        cutoff = self._clock() - self.window
        recent = [t for t in self._fails.get(key, []) if t > cutoff]
        self._fails[key] = recent
        return recent

    def blocked(self, key: str) -> bool:
        with self._lock:
            return len(self._recent(key)) >= self.limit

    def fail(self, key: str) -> None:
        with self._lock:
            self._recent(key).append(self._clock())

    def clear(self, key: str) -> None:
        with self._lock:
            self._fails.pop(key, None)
