from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from questtour.admin.crud import get_admin_host_id, handle_integrity, issue_token, require_fresh
from questtour.admin.errors import AdminValidationError, FieldError
from questtour.admin.schemas import (
    AssignmentCreate,
    TeamAssignmentsUpdate,
    TeamCreate,
    TeamOut,
    TeamUpdate,
    TokenReveal,
    _validate_team,
)
from questtour.api.deps import SessionDep
from questtour.auth import AdminSession, require_admin
from questtour.clock import utc_now
from questtour.models import Assignment, Game, Team
from questtour.sync.schema import parse_window_time

router = APIRouter(prefix="/teams", tags=["admin-teams"])


def _validate_assignment_windows(assignments: list[AssignmentCreate], games: dict[int, Game]) -> None:
    for a in assignments:
        game = games[a.game_id]
        try:
            start = parse_window_time(a.valid_from, game.time_zone)
            end = parse_window_time(a.valid_until, game.time_zone)
        except ValueError as exc:
            raise AdminValidationError(
                [FieldError(field="assignments.valid_from", message=str(exc))]
            ) from exc
        if start >= end:
            raise AdminValidationError(
                [FieldError(field="assignments.valid_until", message="valid_until must be after valid_from")]
            )


@router.get("", response_model=list[TeamOut])
def list_teams(
    session: SessionDep,
    admin: Annotated[AdminSession, Depends(require_admin)],
    host_id: str = Depends(get_admin_host_id),
):
    return session.scalars(select(Team).where(Team.host_id == host_id).order_by(Team.name)).all()


@router.post("", response_model=TeamOut, status_code=201)
def create_team(
    data: TeamCreate,
    session: SessionDep,
    admin: Annotated[AdminSession, Depends(require_admin)],
    host_id: str = Depends(get_admin_host_id),
):
    _validate_team(data)
    team = Team(host_id=host_id, key=data.key, name=data.name, participants=data.participants)
    session.add(team)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise handle_integrity(exc, {"key": "key", "name": "name"})
    return team


@router.get("/{id}", response_model=TeamOut)
def get_team(
    id: int,
    session: SessionDep,
    admin: Annotated[AdminSession, Depends(require_admin)],
    host_id: str = Depends(get_admin_host_id),
):
    team = session.get(Team, id)
    if team is None or team.host_id != host_id:
        raise HTTPException(status_code=404)
    return team


@router.put("/{id}", response_model=TeamOut)
def update_team(
    id: int,
    data: TeamUpdate,
    session: SessionDep,
    admin: Annotated[AdminSession, Depends(require_admin)],
    host_id: str = Depends(get_admin_host_id),
):
    team = session.get(Team, id)
    if team is None or team.host_id != host_id:
        raise HTTPException(status_code=404)
    require_fresh(team, data.seen_at)
    _validate_team(data)
    team.key = data.key
    team.name = data.name
    team.participants = data.participants
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise handle_integrity(exc, {"key": "key", "name": "name"})
    return team


@router.delete("/{id}")
def delete_team(
    id: int,
    session: SessionDep,
    admin: Annotated[AdminSession, Depends(require_admin)],
    host_id: str = Depends(get_admin_host_id),
):
    team = session.get(Team, id)
    if team is None or team.host_id != host_id:
        raise HTTPException(status_code=404)
    assignments = session.scalar(
        select(func.count(Assignment.id)).where(Assignment.team_id == id)
    )
    if assignments:
        raise HTTPException(status_code=409, detail="cannot delete a team that has assignments")
    session.delete(team)
    session.commit()
    return {"deleted": True}


@router.put("/{id}/assignments", response_model=list[TokenReveal])
def update_team_assignments(
    id: int,
    data: TeamAssignmentsUpdate,
    session: SessionDep,
    request: Request,
    admin: Annotated[AdminSession, Depends(require_admin)],
    host_id: str = Depends(get_admin_host_id),
):
    team = session.get(Team, id)
    if team is None or team.host_id != host_id:
        raise HTTPException(status_code=404)
    require_fresh(team, data.seen_at)

    game_ids = {a.game_id for a in data.assignments}
    games = {
        g.id: g
        for g in session.scalars(
            select(Game).where(Game.host_id == host_id, Game.id.in_(game_ids))
        ).all()
    }
    missing_games = game_ids - set(games)
    if missing_games:
        raise AdminValidationError(
            [FieldError(field="assignments.game_id", message=f"unknown games: {sorted(missing_games)}")]
        )

    by_game = {a.game_id: a for a in data.assignments}
    if len(by_game) != len(data.assignments):
        raise AdminValidationError(
            [FieldError(field="assignments", message="duplicate game in assignments")]
        )

    _validate_assignment_windows(data.assignments, games)

    existing = {
        a.game_id: a
        for a in session.scalars(select(Assignment).where(Assignment.team_id == id)).all()
    }

    to_issue: list[Assignment] = []
    seen_games: set[int] = set()

    for game_id, a in by_game.items():
        game = games[game_id]
        seen_games.add(game_id)
        assignment = existing.get(game_id)
        is_new = assignment is None
        if is_new:
            assignment = Assignment(
                host_id=host_id,
                team_id=id,
                game_id=game_id,
            )
            session.add(assignment)
        assignment.valid_from = parse_window_time(a.valid_from, game.time_zone)
        assignment.valid_until = parse_window_time(a.valid_until, game.time_zone)
        assignment.exit_message = a.exit_message

        if is_new or assignment.token_hash is None:
            to_issue.append(assignment)

    for game_id, assignment in existing.items():
        if game_id not in seen_games and assignment.token_hash is not None:
            assignment.token_hash = None
            assignment.issued_at = None

    team.updated_at = utc_now()
    session.flush()  # new assignments get their ids for the reveals
    now = utc_now()
    base_url = request.app.state.settings.public_base_url
    reveals = [issue_token(assignment, base_url, now) for assignment in to_issue]
    session.commit()
    return reveals
