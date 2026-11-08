from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select

from questtour.admin.crud import get_admin_host_id, issue_token
from questtour.admin.schemas import AssignmentOut, TokenReveal
from questtour.api.deps import SessionDep
from questtour.auth import AdminSession, require_admin
from questtour.clock import utc_now
from questtour.models import Assignment, Team

router = APIRouter(prefix="/assignments", tags=["admin-assignments"])


@router.post("/{id}/reissue", response_model=TokenReveal)
def reissue_assignment(
    id: int,
    session: SessionDep,
    request: Request,
    admin: Annotated[AdminSession, Depends(require_admin)],
    host_id: str = Depends(get_admin_host_id),
):
    assignment = session.get(Assignment, id)
    if assignment is None or assignment.host_id != host_id:
        raise HTTPException(status_code=404)
    reveal = issue_token(assignment, request.app.state.settings.public_base_url, utc_now())
    session.commit()
    return reveal


@router.get("/team/{team_id}", response_model=list[AssignmentOut])
def list_team_assignments(
    team_id: int,
    session: SessionDep,
    admin: Annotated[AdminSession, Depends(require_admin)],
    host_id: str = Depends(get_admin_host_id),
):
    team = session.get(Team, team_id)
    if team is None or team.host_id != host_id:
        raise HTTPException(status_code=404)
    assignments = session.scalars(
        select(Assignment).where(Assignment.team_id == team_id).order_by(Assignment.id)
    ).all()
    return [
        AssignmentOut(
            id=a.id,
            game_id=a.game_id,
            game_name=a.game.name,
            valid_from=a.valid_from,
            valid_until=a.valid_until,
            exit_message=a.exit_message,
            token_issued=a.token_hash is not None,
            issued_at=a.issued_at,
            updated_at=a.updated_at,
        )
        for a in assignments
    ]
