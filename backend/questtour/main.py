import hashlib
import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker
from starlette.middleware.sessions import SessionMiddleware

from questtour.admin import admin_router
from questtour.admin.errors import register_admin_exception_handlers
from questtour.api import health, images, play
from questtour.auth import auth_router
from questtour.auth.passwords import LoginThrottle, seed_auth_state
from questtour.clock import Clock, utc_now
from questtour.db import make_engine
from questtour.models import Landmark
from questtour.services.access import LinkNotValid
from questtour.settings import Settings, get_settings
from questtour.storage import BlobStore, make_blob_store
from questtour.version import resolve_version
from questtour.web import install_frontend


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


async def link_not_valid_handler(request: Request, exc: LinkNotValid) -> JSONResponse:
    return JSONResponse(
        status_code=403,
        content={
            "error": {
                "code": "link_not_valid",
                "reason": exc.reason,
                "opens_at": _iso(exc.opens_at),
                "expired_at": _iso(exc.expired_at),
                "time_zone": exc.time_zone,
            }
        },
    )


log = logging.getLogger("questtour")
UPLOAD_OVERHEAD_BYTES = 1024 * 1024  # multipart boundaries + the position field


def _acquire_seed_lock(session, settings: Settings) -> None:
    """Use a deterministic Postgres advisory lock id derived from the host id.

    Advisory locks are Postgres-specific; other dialects (e.g. SQLite in tests) skip locking
    because they do not run concurrent app instances.
    """
    if session.bind.dialect.name != "postgresql":
        return
    lock_input = f"{settings.host_id}:questtour_seed".encode()
    lock_id = int(hashlib.sha256(lock_input).hexdigest()[:16], 16) & 0x7FFFFFFFFFFFFFFF
    session.execute(select(func.pg_advisory_xact_lock(lock_id)))


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = app.state.settings
    app.state.seed_error = None
    if settings.admin_auth_provider in ("password", "entra"):
        with app.state.session_factory() as db:
            seed_auth_state(db, settings)
        if settings.admin_auth_provider == "entra" and not (
            settings.admin_bootstrap_email and settings.admin_bootstrap_password
        ):
            log.warning(
                "entra mode without ADMIN_BOOTSTRAP_EMAIL/PASSWORD: "
                "password sign-in has no bootstrap admin yet"
            )
    if settings.config_dir.is_dir():
        try:
            with app.state.session_factory() as session:  # noqa: SIM117
                with session.begin():
                    _acquire_seed_lock(session, settings)
                    count = session.scalar(
                        select(func.count(Landmark.id)).where(Landmark.host_id == settings.host_id)
                    )
                    if count == 0:
                        from questtour.services.seed import import_yaml

                        result = import_yaml(
                            session=session,
                            store=app.state.blob_store,
                            settings=settings,
                            write_back=False,
                            autocommit=False,
                        )
                        if isinstance(result, list):
                            app.state.seed_error = "; ".join(result)
                            raise RuntimeError("seed validation failed")
        except Exception:
            log.exception("seed import failed")
            if app.state.seed_error is None:
                app.state.seed_error = "seed import failed; see logs"
    yield


def create_app(
    settings: Settings | None = None,
    *,
    session_factory=None,
    blob_store: BlobStore | None = None,
    clock: Clock = utc_now,
) -> FastAPI:
    logging.basicConfig(level=logging.INFO)
    settings = settings or get_settings()
    problems = settings.startup_problems()
    if problems:
        raise RuntimeError("Admin sign-in is not configured: " + "; ".join(problems))
    app = FastAPI(
        title="Quest City Tour",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    register_admin_exception_handlers(app)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.admin_session_secret,
        session_cookie="questtour_admin_session",
        max_age=settings.admin_session_max_age_minutes * 60,
        same_site="lax",
        https_only=settings.admin_session_secure,
    )
    app.state.settings = settings
    app.state.version = resolve_version(settings)
    log.info("Quest City Tour %s", app.state.version)
    app.state.session_factory = session_factory or sessionmaker(
        make_engine(settings), expire_on_commit=False
    )
    app.state.blob_store = blob_store or make_blob_store(settings)
    app.state.clock = clock
    app.state.login_throttle = LoginThrottle()
    app.include_router(auth_router)  # full /api/admin/auth/* routes
    app.include_router(admin_router)  # prefix /api/admin
    if blob_store is None:
        _ensure_containers(app.state.blob_store, settings)

    @app.middleware("http")
    async def refuse_oversized_photo(request: Request, call_next):
        """FastAPI parses (and spools to disk) the whole multipart body before the endpoint runs, before
        the token is even checked. Refuse obviously oversized uploads from Content-Length first."""
        if request.method == "POST" and request.url.path.endswith("/photo"):
            length = request.headers.get("content-length", "")
            if length.isdigit() and int(length) > settings.max_photo_bytes + UPLOAD_OVERHEAD_BYTES:
                return JSONResponse(
                    status_code=413, content={"detail": "Photo is larger than 20 MB"}
                )
        return await call_next(request)

    app.include_router(health.router)
    app.include_router(play.router)
    app.include_router(images.router)
    app.add_exception_handler(LinkNotValid, link_not_valid_handler)
    install_frontend(app, settings.static_dir)
    return app


def _ensure_containers(store: BlobStore, settings: Settings) -> None:
    """A fresh or reset Azurite has no containers. Without this, every upload would be a 503
    until someone re-ran sync-config. Storage being down must not stop the app from starting."""
    try:
        for container in (settings.photos_container, settings.images_container, settings.albums_container):
            store.ensure_container(container)
    except Exception:  # any SDK/network error: log it; uploads will report 503
        log.exception("could not create blob containers; uploads fail until storage is reachable")
