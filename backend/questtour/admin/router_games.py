from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from questtour.admin.crud import get_admin_host_id, handle_integrity, require_fresh
from questtour.admin.errors import AdminValidationError, FieldError
from questtour.admin.schemas import (
    GameCreate,
    GameOut,
    GameTasksUpdate,
    GameUpdate,
    RevealSettings,
    _validate_game,
)
from questtour.api.deps import SessionDep
from questtour.auth import AdminSession, require_admin
from questtour.clock import utc_now
from questtour.models import Assignment, Game, GameRequest, GameTask, Landmark

router = APIRouter(prefix="/games", tags=["admin-games"])


def _game_out(game: Game) -> GameOut:
    languages = {
        code
        for t in game.tasks
        for col in (
            t.landmark.name_i18n,
            t.landmark.task_text_i18n,
            t.landmark.hint1_i18n,
            t.landmark.hint2_i18n,
            t.landmark.info_text_i18n,
        )
        if col
        for code in col
    }
    return GameOut(
        id=game.id,
        key=game.key,
        name=game.name,
        intro=game.intro,
        time_zone=game.time_zone,
        max_duration_minutes=game.max_duration_minutes,
        reveal=RevealSettings(
            attempts=game.reveal_after_attempts,
            minutes=game.reveal_after_minutes,
            penalty_minutes=game.reveal_penalty_minutes,
        ),
        requestable=game.requestable,
        updated_at=game.updated_at,
        task_landmark_ids=[t.landmark_id for t in game.tasks],
        available_languages=sorted(languages),
    )


@router.get("", response_model=list[GameOut])
def list_games(
    session: SessionDep,
    admin: Annotated[AdminSession, Depends(require_admin)],
    host_id: str = Depends(get_admin_host_id),
):
    games = session.scalars(
        select(Game)
        .where(Game.host_id == host_id)
        .order_by(Game.name)
        .options(selectinload(Game.tasks).selectinload(GameTask.landmark))
    ).all()
    return [_game_out(g) for g in games]


@router.post("", response_model=GameOut, status_code=201)
def create_game(
    data: GameCreate,
    session: SessionDep,
    admin: Annotated[AdminSession, Depends(require_admin)],
    host_id: str = Depends(get_admin_host_id),
):
    _validate_game(data)
    game = Game(
        host_id=host_id,
        key=data.key,
        name=data.name,
        intro=data.intro,
        time_zone=data.time_zone,
        max_duration_minutes=data.max_duration_minutes,
        reveal_after_attempts=data.reveal.attempts,
        reveal_after_minutes=data.reveal.minutes,
        reveal_penalty_minutes=data.reveal.penalty_minutes,
        requestable=bool(data.requestable),
    )
    session.add(game)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise handle_integrity(exc, {"key": "key"})
    return _game_out(game)


@router.get("/{id}", response_model=GameOut)
def get_game(
    id: int,
    session: SessionDep,
    admin: Annotated[AdminSession, Depends(require_admin)],
    host_id: str = Depends(get_admin_host_id),
):
    game = session.scalars(
        select(Game)
        .where(Game.id == id)
        .options(selectinload(Game.tasks).selectinload(GameTask.landmark))
    ).first()
    if game is None or game.host_id != host_id:
        raise HTTPException(status_code=404)
    return _game_out(game)


@router.put("/{id}", response_model=GameOut)
def update_game(
    id: int,
    data: GameUpdate,
    session: SessionDep,
    admin: Annotated[AdminSession, Depends(require_admin)],
    host_id: str = Depends(get_admin_host_id),
):
    game = session.get(Game, id)
    if game is None or game.host_id != host_id:
        raise HTTPException(status_code=404)
    require_fresh(game, data.seen_at)
    _validate_game(data)
    game.key = data.key
    game.name = data.name
    game.intro = data.intro
    game.time_zone = data.time_zone
    game.max_duration_minutes = data.max_duration_minutes
    game.reveal_after_attempts = data.reveal.attempts
    game.reveal_after_minutes = data.reveal.minutes
    game.reveal_penalty_minutes = data.reveal.penalty_minutes
    if data.requestable is not None:
        game.requestable = data.requestable
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise handle_integrity(exc, {"key": "key"})
    return _game_out(game)


@router.put("/{id}/tasks")
def update_game_tasks(
    id: int,
    data: GameTasksUpdate,
    session: SessionDep,
    admin: Annotated[AdminSession, Depends(require_admin)],
    host_id: str = Depends(get_admin_host_id),
):
    game = session.get(Game, id)
    if game is None or game.host_id != host_id:
        raise HTTPException(status_code=404)
    require_fresh(game, data.seen_at)

    if len(set(data.landmark_ids)) != len(data.landmark_ids):
        raise AdminValidationError([FieldError(field="landmark_ids", message="duplicate landmark")])

    existing = set(
        session.scalars(
            select(Landmark.id).where(Landmark.host_id == host_id, Landmark.id.in_(data.landmark_ids))
        ).all()
    )
    missing = [lid for lid in data.landmark_ids if lid not in existing]
    if missing:
        raise AdminValidationError(
            [FieldError(field="landmark_ids", message=f"unknown landmarks: {missing}")]
        )

    # Runs keep their own snapshot; task reordering only affects future starts.
    game.tasks.clear()
    session.flush()
    game.tasks.extend(
        GameTask(position=i, landmark_id=lid) for i, lid in enumerate(data.landmark_ids)
    )
    # Bump parent timestamp so child mutations participate in optimistic concurrency.
    game.updated_at = utc_now()
    session.commit()
    return {"ok": True}


@router.get("/{id}/tasks")
def get_game_tasks(
    id: int,
    session: SessionDep,
    admin: Annotated[AdminSession, Depends(require_admin)],
    host_id: str = Depends(get_admin_host_id),
):
    game = session.get(Game, id)
    if game is None or game.host_id != host_id:
        raise HTTPException(status_code=404)
    return {"landmark_ids": [t.landmark_id for t in game.tasks]}


@router.delete("/{id}")
def delete_game(
    id: int,
    session: SessionDep,
    admin: Annotated[AdminSession, Depends(require_admin)],
    host_id: str = Depends(get_admin_host_id),
):
    game = session.get(Game, id)
    if game is None or game.host_id != host_id:
        raise HTTPException(status_code=404)
    assignments = session.scalar(select(func.count(Assignment.id)).where(Assignment.game_id == id))
    if assignments:
        raise HTTPException(status_code=409, detail="cannot delete a game that has assignments")
    pending = session.scalar(
        select(func.count(GameRequest.id)).where(
            GameRequest.game_id == id, GameRequest.status == "pending"
        )
    )
    if pending:
        raise HTTPException(status_code=409, detail="cannot delete a game that has pending requests")
    session.delete(game)  # cascade deletes GameTask children
    session.commit()
    return {"deleted": True}
