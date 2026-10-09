from typing import Annotated

from fastapi import APIRouter, Depends, Request

from questtour.auth import AdminSession, require_admin

admin_router = APIRouter(prefix="/api/admin")

from questtour.admin.photos import router as photos_router
from questtour.admin.router_albums import router as albums_router
from questtour.admin.router_assignments import router as assignments_router
from questtour.admin.router_feedback import router as feedback_router
from questtour.admin.router_games import router as games_router
from questtour.admin.router_landmarks import router as landmarks_router
from questtour.admin.router_teams import router as teams_router

admin_router.include_router(landmarks_router)
admin_router.include_router(games_router)
admin_router.include_router(teams_router)
admin_router.include_router(assignments_router)
admin_router.include_router(photos_router)
admin_router.include_router(albums_router)
admin_router.include_router(feedback_router)


@admin_router.get("/seed-error")
def seed_error(
    request: Request,
    admin: Annotated[AdminSession, Depends(require_admin)],
):
    return {"error": getattr(request.app.state, "seed_error", None)}
