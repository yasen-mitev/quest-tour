from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import func, select

from questtour.auth import AdminSession, require_admin
from questtour.auth.passwords import (
    ENTRA_FLAG,
    MIN_PASSWORD_LENGTH,
    entra_flag,
    find_admin,
    hash_password,
    normalize_email,
    set_flag,
    verify_password,
)
from questtour.models import AdminUser

router = APIRouter(prefix="/account", tags=["account"])


class AuthSettingsIn(BaseModel):
    entra_enabled: bool


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH)


class NewAdmin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=MIN_PASSWORD_LENGTH)


class PasswordReset(BaseModel):
    password: str = Field(min_length=MIN_PASSWORD_LENGTH)


class AdminOut(BaseModel):
    id: int
    email: str
    is_bootstrap: bool
    model_config = ConfigDict(from_attributes=True)


def _require_password_admin(admin: AdminSession) -> None:
    if admin["provider"] != "password":
        raise HTTPException(status_code=403, detail="available to password admins only")


@router.get("/auth-settings")
def get_auth_settings(request: Request, admin: Annotated[AdminSession, Depends(require_admin)]):
    settings = request.app.state.settings
    with request.app.state.session_factory() as db:
        enabled = settings.admin_auth_provider != "dev" and entra_flag(settings, db)
    return {
        "mode": settings.admin_auth_provider,
        "entra_configured": settings.entra_configured,
        "entra_enabled": enabled,  # the stored toggle; the button shows only if also configured
        "session_provider": admin["provider"],
    }


@router.put("/auth-settings")
def put_auth_settings(
    body: AuthSettingsIn,
    request: Request,
    admin: Annotated[AdminSession, Depends(require_admin)],
):
    settings = request.app.state.settings
    if settings.admin_auth_provider == "dev":
        raise HTTPException(status_code=409, detail="Entra sign-in is not available in dev mode")
    if body.entra_enabled and not settings.entra_configured:
        raise HTTPException(
            status_code=409,
            detail="Entra is not configured for this deployment (tenant/client/secret/group)",
        )
    with request.app.state.session_factory() as db:
        if not body.entra_enabled and db.scalar(select(func.count(AdminUser.id))) == 0:
            raise HTTPException(
                status_code=409,
                detail="Create a password admin first; disabling Entra would lock everyone out",
            )
        set_flag(db, ENTRA_FLAG, body.entra_enabled)
    return {"entra_enabled": body.entra_enabled}


@router.post("/password")
def change_password(
    body: PasswordChange,
    request: Request,
    admin: Annotated[AdminSession, Depends(require_admin)],
):
    _require_password_admin(admin)
    with request.app.state.session_factory() as db:
        user = verify_password(db, admin["email"], body.current_password)
        if user is None:
            raise HTTPException(status_code=400, detail="current password is wrong")  # never 401
        user.password_hash = hash_password(body.new_password)
        db.commit()
    return {"ok": True}


@router.get("/admins", response_model=list[AdminOut])
def list_admins(request: Request, admin: Annotated[AdminSession, Depends(require_admin)]):
    _require_password_admin(admin)
    with request.app.state.session_factory() as db:
        return db.scalars(select(AdminUser).order_by(AdminUser.email)).all()


@router.post("/admins", response_model=AdminOut)
def create_admin(
    body: NewAdmin,
    request: Request,
    admin: Annotated[AdminSession, Depends(require_admin)],
):
    _require_password_admin(admin)
    with request.app.state.session_factory() as db:
        if find_admin(db, body.email) is not None:
            raise HTTPException(status_code=409, detail="an admin with this email already exists")
        user = AdminUser(
            email=normalize_email(body.email), password_hash=hash_password(body.password)
        )
        db.add(user)
        db.commit()
        return user


@router.delete("/admins/{admin_id}")
def delete_admin(
    admin_id: int,
    request: Request,
    admin: Annotated[AdminSession, Depends(require_admin)],
):
    _require_password_admin(admin)
    with request.app.state.session_factory() as db:
        user = db.get(AdminUser, admin_id)
        if user is None:
            raise HTTPException(status_code=404)
        if user.email == normalize_email(admin["email"]):
            raise HTTPException(status_code=409, detail="you cannot remove yourself")
        if db.scalar(select(func.count(AdminUser.id))) <= 1:
            raise HTTPException(status_code=409, detail="the last admin cannot be removed")
        db.delete(user)
        db.commit()
    return {"ok": True}


@router.put("/admins/{admin_id}/password")
def reset_admin_password(
    admin_id: int,
    body: PasswordReset,
    request: Request,
    admin: Annotated[AdminSession, Depends(require_admin)],
):
    _require_password_admin(admin)
    with request.app.state.session_factory() as db:
        user = db.get(AdminUser, admin_id)
        if user is None:
            raise HTTPException(status_code=404)
        user.password_hash = hash_password(body.password)
        db.commit()
    return {"ok": True}
