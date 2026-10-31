from typing import TypedDict

from fastapi import HTTPException, Request, status
from sqlalchemy import select

from questtour.auth.passwords import normalize_email
from questtour.models import AdminUser


class AdminSession(TypedDict):
    email: str
    provider: str


def require_admin(request: Request) -> AdminSession:
    session = request.session
    admin = session.get("admin")
    if not admin or not isinstance(admin, dict) or "email" not in admin:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="admin session required"
        )
    if admin.get("provider") == "password":
        factory = getattr(request.app.state, "session_factory", None)
        if factory is not None:
            with factory() as db:
                found = db.scalar(
                    select(AdminUser.id).where(AdminUser.email == normalize_email(admin["email"]))
                )
            if found is None:
                request.session.clear()
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED, detail="admin session required"
                )
    return AdminSession(email=admin["email"], provider=admin.get("provider", ""))
