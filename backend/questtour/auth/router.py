import logging
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel, EmailStr

from questtour.settings import Settings

from .deps import get_auth_provider

auth_router = APIRouter()
log = logging.getLogger(__name__)


def _settings(request: Request) -> Settings:
    return request.app.state.settings


class MagicRequest(BaseModel):
    email: EmailStr


@auth_router.get("/api/admin/auth/provider")
def admin_auth_provider(settings: Annotated[Settings, Depends(_settings)]):
    """Tells the login screen which sign-in to offer: Entra redirect or dev magic link."""
    return {"provider": settings.admin_auth_provider}


@auth_router.get("/api/admin/auth/login")
async def admin_login(
    request: Request,
    settings: Annotated[Settings, Depends(_settings)],
):
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
    provider = get_auth_provider(settings)
    email = await provider.process_callback(request)
    request.session["admin"] = {"email": email, "provider": settings.admin_auth_provider}
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
