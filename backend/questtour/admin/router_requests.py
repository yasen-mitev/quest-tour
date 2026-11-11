"""Admin API for game play requests (issue #61): list, read, edit, approve and reject.

Approval creates the teams, their assignments and tokens in one transaction and happens at most
once; a decided request is read-only (409 with the current detail). Every time comes from the
injected clock (``NowDep``); only ``updated_at`` keeps the real clock, for ``require_fresh``.
"""

from datetime import UTC, date, datetime, time
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import and_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from questtour.admin.crud import get_admin_host_id, handle_integrity, issue_token, require_fresh
from questtour.admin.errors import AdminValidationError, ConflictError, FieldError
from questtour.admin.schemas import (
    GameRequestDecision,
    GameRequestListItem,
    GameRequestOut,
    GameRequestTeamOut,
    GameRequestUpdate,
    RequestTeamIn,
    TokenReveal,
    _validate_team,
)
from questtour.api.deps import NowDep, SessionDep
from questtour.auth import AdminSession, require_admin
from questtour.models import Assignment, Game, GameRequest, Team
from questtour.requests import service
from questtour.settings import Settings
from questtour.sync.schema import parse_window_time

router = APIRouter(prefix="/requests", tags=["admin-requests"])

MAX_KEY_LENGTH = 100  # Team.key
MAX_NAME_LENGTH = 200  # Team.name
WINDOW_FIELDS = ("valid_from", "valid_until")


def _host_request(session: Session, id: int, host_id: str) -> GameRequest:
    row = session.get(GameRequest, id)
    if row is None or row.host_id != host_id:
        raise HTTPException(status_code=404)
    return row


def _host_game(session: Session, game_id: int | None, host_id: str) -> Game | None:
    game = session.get(Game, game_id) if game_id is not None else None
    return game if game is not None and game.host_id == host_id else None


def _day_window(play_date: date, time_zone: str) -> tuple[datetime, datetime]:
    """D1: the default window is the play date, 00:00 to 23:59:59 in the game's time zone."""
    tz = ZoneInfo(time_zone)
    return (
        datetime.combine(play_date, time(0, 0), tz).astimezone(UTC),
        datetime.combine(play_date, time(23, 59, 59), tz).astimezone(UTC),
    )


def _team_window(
    team: dict, game: Game | None, play_date: date
) -> tuple[datetime | None, datetime | None]:
    """The stored window (UTC ISO) of a request team, a null bound resolved to the default."""
    default = _day_window(play_date, game.time_zone) if game else (None, None)
    return tuple(
        datetime.fromisoformat(team[field]) if team[field] else fallback
        for field, fallback in zip(WINDOW_FIELDS, default, strict=True)
    )


def _exit_message(row: GameRequest, settings: Settings) -> str:
    return row.exit_message if row.exit_message is not None else settings.default_exit_message


def _detail(session: Session, row: GameRequest, settings: Settings) -> GameRequestOut:
    game = _host_game(session, row.game_id, row.host_id)
    teams = []
    for team in row.teams:
        valid_from, valid_until = _team_window(team, game, row.play_date)
        teams.append(
            GameRequestTeamOut(
                name=team["name"],
                key=team["key"],
                participants=team["participants"],
                valid_from=valid_from,
                valid_until=valid_until,
                team_id=team["team_id"],
            )
        )
    return GameRequestOut(
        id=row.id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        status=row.status,
        game_id=row.game_id,
        game_name=game.name if game else None,
        game_time_zone=game.time_zone if game else None,
        play_date=row.play_date,
        contact_name=row.contact_name,
        contact_email=row.contact_email,
        contact_phone=row.contact_phone,
        message=row.message,
        exit_message=_exit_message(row, settings),
        terms_accepted_at=row.terms_accepted_at,
        terms_version=row.terms_version,
        decided_at=row.decided_at,
        decided_by=row.decided_by,
        teams=teams,
    )


def _conflict(session: Session, row: GameRequest, settings: Settings) -> ConflictError:
    """The UI reloads the current detail from the 409 body and switches to read-only."""
    return ConflictError(
        entity="GameRequest", current=_detail(session, row, settings).model_dump(mode="json")
    )


def _require_pending(session: Session, row: GameRequest, settings: Settings) -> None:
    if row.status != service.PENDING:
        raise _conflict(session, row, settings)


def _decide(session: Session, row: GameRequest, status: str, now: datetime, email: str) -> bool:
    """Flip a still-pending request; False when someone else decided it first."""
    result = session.execute(
        update(GameRequest)
        .where(GameRequest.id == row.id, GameRequest.status == service.PENDING)
        .values(status=status, decided_at=now, decided_by=email)
    )
    return result.rowcount == 1


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat() if value else None


def _validated_teams(teams: list[RequestTeamIn], game: Game, play_date: date) -> list[dict]:
    """The teams as stored (windows as UTC ISO, null = default); raises 422 ``teams.<i>.*``."""
    errors: list[FieldError] = []
    keys: set[str] = set()
    names: set[str] = set()
    stored = []
    for i, team in enumerate(teams):
        prefix = f"teams.{i}"
        try:
            _validate_team(team)
        except AdminValidationError as exc:
            # TeamBaseCfg (the YAML schema) calls the key "id".
            errors += [
                FieldError(field=f"{prefix}.{'key' if e.field == 'id' else e.field}", message=e.message)
                for e in exc.errors
            ]
        if len(team.key) > MAX_KEY_LENGTH:
            errors.append(FieldError(field=f"{prefix}.key", message="Key is too long"))
        if len(team.name) > MAX_NAME_LENGTH:
            errors.append(FieldError(field=f"{prefix}.name", message="Name is too long"))
        if team.key in keys:
            errors.append(FieldError(field=f"{prefix}.key", message="Team keys must differ"))
        if team.name.casefold() in names:
            errors.append(FieldError(field=f"{prefix}.name", message="Team names must differ"))
        keys.add(team.key)
        names.add(team.name.casefold())

        window: dict[str, datetime | None] = {}
        for field in WINDOW_FIELDS:
            value = getattr(team, field)
            try:
                window[field] = parse_window_time(value, game.time_zone) if value else None
            except ValueError as exc:
                errors.append(FieldError(field=f"{prefix}.{field}", message=str(exc)))
        if len(window) == len(WINDOW_FIELDS):
            default_from, default_until = _day_window(play_date, game.time_zone)
            if (window["valid_from"] or default_from) >= (window["valid_until"] or default_until):
                errors.append(
                    FieldError(
                        field=f"{prefix}.valid_until", message="valid_until must be after valid_from"
                    )
                )
        stored.append(
            {
                "name": team.name,
                "key": team.key,
                "participants": team.participants,
                "valid_from": _iso(window.get("valid_from")),
                "valid_until": _iso(window.get("valid_until")),
                "team_id": None,
            }
        )
    if errors:
        raise AdminValidationError(errors)
    return stored


@router.get("", response_model=list[GameRequestListItem])
def list_requests(
    session: SessionDep,
    request: Request,
    now: NowDep,
    admin: Annotated[AdminSession, Depends(require_admin)],
    host_id: str = Depends(get_admin_host_id),
    status: Literal["pending", "approved", "rejected", "all"] = "pending",
):
    service.purge_decided_requests(
        session, now, request.app.state.settings.request_retention_days
    )  # D5
    session.commit()
    query = (
        select(GameRequest, Game.name)
        .outerjoin(Game, and_(Game.id == GameRequest.game_id, Game.host_id == host_id))
        .where(GameRequest.host_id == host_id)
        .order_by(GameRequest.created_at.desc(), GameRequest.id.desc())
    )
    if status != "all":
        query = query.where(GameRequest.status == status)
    return [
        GameRequestListItem(
            id=row.id,
            created_at=row.created_at,
            contact_name=row.contact_name,
            game_id=row.game_id,
            game_name=game_name,
            play_date=row.play_date,
            team_count=len(row.teams),
            status=row.status,
        )
        for row, game_name in session.execute(query)
    ]


@router.get("/{id}", response_model=GameRequestOut)
def get_request(
    id: int,
    session: SessionDep,
    request: Request,
    admin: Annotated[AdminSession, Depends(require_admin)],
    host_id: str = Depends(get_admin_host_id),
):
    return _detail(session, _host_request(session, id, host_id), request.app.state.settings)


@router.put("/{id}", response_model=GameRequestOut)
def update_request(
    id: int,
    data: GameRequestUpdate,
    session: SessionDep,
    request: Request,
    admin: Annotated[AdminSession, Depends(require_admin)],
    host_id: str = Depends(get_admin_host_id),
):
    settings = request.app.state.settings
    row = _host_request(session, id, host_id)
    _require_pending(session, row, settings)
    require_fresh(row, data.seen_at)
    game = _host_game(session, data.game_id, host_id)  # need not be requestable
    if game is None:
        raise AdminValidationError([FieldError(field="game_id", message="Unknown game")])
    row.teams = _validated_teams(data.teams, game, row.play_date)
    row.game_id = game.id
    row.exit_message = data.exit_message
    session.commit()
    return _detail(session, row, settings)


@router.post("/{id}/approve", response_model=list[TokenReveal])
def approve_request(
    id: int,
    data: GameRequestDecision,
    session: SessionDep,
    request: Request,
    now: NowDep,
    admin: Annotated[AdminSession, Depends(require_admin)],
    host_id: str = Depends(get_admin_host_id),
):
    settings = request.app.state.settings
    row = _host_request(session, id, host_id)
    _require_pending(session, row, settings)
    require_fresh(row, data.seen_at)
    game = _host_game(session, row.game_id, host_id)
    if game is None:
        raise AdminValidationError(
            [FieldError(field="game_id", message="Choose a game before approving")]
        )
    specs = list(row.teams)
    clashes = service.team_clashes(session, host_id, specs)
    if clashes:
        raise AdminValidationError(clashes)
    windows = [_team_window(spec, game, row.play_date) for spec in specs]
    exit_message = _exit_message(row, settings)

    if not _decide(session, row, "approved", now, admin["email"]):
        session.rollback()
        raise _conflict(session, row, settings)
    try:
        created = []
        for spec, (valid_from, valid_until) in zip(specs, windows, strict=True):
            team = Team(
                host_id=host_id, key=spec["key"], name=spec["name"], participants=spec["participants"]
            )
            assignment = Assignment(
                host_id=host_id,
                team=team,
                game_id=game.id,
                valid_from=valid_from,
                valid_until=valid_until,
                exit_message=exit_message,
            )
            session.add_all([team, assignment])
            created.append((team, assignment))
        session.flush()  # real ids for the reveals and team_id
        reveals = [
            issue_token(assignment, settings.public_base_url, now) for _, assignment in created
        ]
        # A new list: in-place changes to a plain JSON column are not tracked.
        row.teams = [
            {**spec, "team_id": team.id} for spec, (team, _) in zip(specs, created, strict=True)
        ]
        session.commit()
    except IntegrityError as exc:
        # A team created since the check: nothing is kept and the request stays pending.
        session.rollback()
        clashes = service.team_clashes(session, host_id, specs)
        if clashes:
            raise AdminValidationError(clashes) from exc
        raise handle_integrity(exc, {"key": "key", "name": "name"}) from exc
    return reveals


@router.post("/{id}/reject", response_model=GameRequestOut)
def reject_request(
    id: int,
    data: GameRequestDecision,
    session: SessionDep,
    request: Request,
    now: NowDep,
    admin: Annotated[AdminSession, Depends(require_admin)],
    host_id: str = Depends(get_admin_host_id),
):
    settings = request.app.state.settings
    row = _host_request(session, id, host_id)
    _require_pending(session, row, settings)
    require_fresh(row, data.seen_at)
    if not _decide(session, row, "rejected", now, admin["email"]):
        session.rollback()
        raise _conflict(session, row, settings)
    session.commit()
    return _detail(session, row, settings)
