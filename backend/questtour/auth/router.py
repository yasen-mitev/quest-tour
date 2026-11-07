import logging
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel, EmailStr

from questtour.auth.passwords import (
    LoginThrottle,
    auth_methods,
    normalize_email,
    verify_password,
)
from questtour.settings import Settings

from .deps import get_auth_provider

auth_router = APIRouter()
log = logging.getLogger(__name__)


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _methods(request: Request, settings: Settings) -> dict[str, bool]:
    if settings.admin_auth_provider == "dev":
        return auth_methods(settings, None)  # no DB access in dev mode
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        return auth_methods(settings, None)
    with factory() as db:
        return auth_methods(settings, db)


def _require_entra(request: Request, settings: Settings) -> None:
    if not _methods(request, settings)["entra"]:
        raise HTTPException(status_code=404)


def _throttle(request: Request) -> LoginThrottle:
    state = request.app.state
    if getattr(state, "login_throttle", None) is None:
        state.login_throttle = LoginThrottle()
    return state.login_throttle


class MagicRequest(BaseModel):
    email: EmailStr


class PasswordLogin(BaseModel):
    email: EmailStr
    password: str


@auth_router.get("/api/admin/auth/provider")
def admin_auth_provider(request: Request, settings: Annotated[Settings, Depends(_settings)]):
    """Tells the login screen which sign-in methods to offer."""
    return {"provider": settings.admin_auth_provider, "methods": _methods(request, settings)}


@auth_router.post("/api/admin/auth/password")
def password_login(
    request: Request,
    body: PasswordLogin,
    settings: Annotated[Settings, Depends(_settings)],
):
    if not _methods(request, settings)["password"]:
        raise HTTPException(status_code=404)
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise HTTPException(status_code=503, detail="password sign-in needs a database")
    throttle = _throttle(request)
    host = request.client.host if request.client else "?"
    key = f"{host}|{normalize_email(body.email)}"
    if throttle.blocked(key):
        raise HTTPException(status_code=429, detail="too many attempts, try again later")
    with factory() as db:
        user = verify_password(db, body.email, body.password)
        email = user.email if user else None
    if email is None:
        throttle.fail(key)
        # 400, not 401: adminRequest redirects to /admin/login on every 401
        raise HTTPException(status_code=400, detail="invalid email or password")
    throttle.clear(key)
    request.session.clear()  # fresh session on privilege change
    request.session["admin"] = {"email": email, "provider": "password"}
    return {"ok": True}


@auth_router.get("/api/admin/auth/login")
async def admin_login(
    request: Request,
    settings: Annotated[Settings, Depends(_settings)],
):
    _require_entra(request, settings)
    provider = get_auth_provider(settings)
    result = await provider.login_url(request)
    if isinstance(result, Response):
        return result
    return RedirectResponse(result)


@auth_router.get("/api/admin/auth/callback")
async def admin_callback(
    request: Request,
    settings: Annotated[Settings, Depends(_settings)],
):
    _require_entra(request, settings)
    provider = get_auth_provider(settings)
    email = await provider.process_callback(request)
    request.session["admin"] = {"email": email, "provider": "entra"}
    return RedirectResponse("/admin")


@auth_router.post("/api/admin/auth/logout")
async def admin_logout(request: Request):
    request.session.clear()
    return {"ok": True}


@auth_router.post("/api/admin/auth/magic/request")
async def request_magic(
    request: Request,
    body: MagicRequest,
    settings: Annotated[Settings, Depends(_settings)],
):
    if settings.admin_auth_provider != "dev":
        raise HTTPException(status_code=404)
    provider = get_auth_provider(settings)
    token = await provider.request_magic(request, body.email)
    base = settings.public_base_url.rstrip("/")
    url = f"{base}/api/admin/auth/magic/verify?{urlencode({'token': token, 'email': body.email})}"
    log.info("dev magic link for %s: %s", body.email, url)
    return {"url": url}


@auth_router.get("/api/admin/auth/magic/verify")
async def verify_magic(
    request: Request,
    token: str,
    email: str,
    settings: Annotated[Settings, Depends(_settings)],
):
    if settings.admin_auth_provider != "dev":
        raise HTTPException(status_code=404)
    provider = get_auth_provider(settings)
    verified_email = await provider.consume_magic(request, token, email)
    request.session["admin"] = {"email": verified_email, "provider": "dev"}
    return RedirectResponse("/admin")
