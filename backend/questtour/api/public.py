"""Public API for the website's game play request form (issue #61). No auth; always the
configured host. POST /requests runs its checks in the order fixed by the plan's "Public API"
contract, commits once at the end and logs reason codes only, never personal data."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from questtour.admin.crud import handle_integrity
from questtour.admin.errors import AdminValidationError, FieldError
from questtour.api.deps import NowDep, SessionDep
from questtour.models import Game
from questtour.requests import challenge, service

log = logging.getLogger("questtour.requests")
router = APIRouter(prefix="/api/public", tags=["public"])

MAX_BODY_BYTES = 16 * 1024


class PublicGameOut(BaseModel):
    key: str
    name: str
    intro: str


async def read_limited_body(request: Request) -> bytes:
    """Step 1: refuse a body over 16 KB from Content-Length and from the bytes actually read, so a
    chunked body cannot bypass the limit."""
    length = request.headers.get("content-length", "")
    if length.isdigit() and int(length) > MAX_BODY_BYTES:
        raise HTTPException(413, "too_large")
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > MAX_BODY_BYTES:
            raise HTTPException(413, "too_large")
    return bytes(body)


def _outcome(code: str) -> None:
    log.info("game request outcome=%s", code)


def _altcha_error() -> AdminValidationError:
    """One message for every challenge failure; the reason code goes to the log only."""
    return AdminValidationError(
        [FieldError(field="altcha", message="The anti-spam check failed, please try again")]
    )


@router.get("/games", response_model=list[PublicGameOut])
def list_games(request: Request, session: SessionDep) -> list[PublicGameOut]:
    host_id = request.app.state.settings.host_id
    games = session.scalars(
        select(Game).where(Game.host_id == host_id, Game.requestable).order_by(Game.name)
    )
    return [PublicGameOut(key=game.key, name=game.name, intro=game.intro) for game in games]


@router.get("/requests/challenge")
def get_challenge(request: Request, response: Response, now: NowDep) -> dict:
    """A fresh signed challenge (D4) plus the timing the form must respect (D2)."""
    settings = request.app.state.settings
    response.headers["Cache-Control"] = "no-store"
    return {
        **challenge.issue(
            settings.request_challenge_secret, settings.request_challenge_max_number, now
        ),
        "min_fill_seconds": settings.request_min_fill_seconds,
        "expires_in_seconds": challenge.CHALLENGE_TTL_SECONDS,
    }


@router.post("/requests", status_code=201)
def submit_request(
    request: Request,
    raw: Annotated[bytes, Depends(read_limited_body)],
    session: SessionDep,
    now: NowDep,
):
    settings = request.app.state.settings
    host_id = settings.host_id
    data = service.parse_request(raw, settings.request_max_teams)  # step 2

    if data.website is not None:  # step 3
        _outcome("honeypot")
        return {}

    try:  # step 4
        issued_at = challenge.verify(
            data.altcha,
            settings.request_challenge_secret,
            now,
            max_number=settings.request_challenge_max_number,
        )
    except challenge.ChallengeError as exc:
        _outcome(exc.code)
        raise _altcha_error() from exc
    token = data.altcha["challenge"]
    if service.challenge_used(session, token):
        _outcome("challenge_reused")
        raise _altcha_error()

    if (now - issued_at).total_seconds() < settings.request_min_fill_seconds:  # step 5
        _outcome("too_fast")
        return {}

    service.purge_decided_requests(session, now, settings.request_retention_days)  # step 6

    refusal = service.capacity_refusal(  # steps 7 and 8
        session,
        host_id,
        now,
        max_pending=settings.request_max_pending,
        max_per_hour=settings.request_max_per_hour,
    )
    if refusal is not None:
        _outcome(refusal)
        raise HTTPException(503, "not_accepting")

    game = service.requestable_game(session, host_id, data.game_key)  # step 9
    if game is None:
        raise AdminValidationError(
            [FieldError(field="game_key", message="This game cannot be requested")]
        )
    if not service.play_date_allowed(game, data.play_date, now):
        raise AdminValidationError(
            [FieldError(field="play_date", message="Pick a day within the next year")]
        )

    duplicate = service.duplicate_field(session, host_id, game.id, data)  # step 10
    if duplicate is not None:
        _outcome("duplicate")
        return JSONResponse(
            status_code=409,
            content={"errors": [{"field": duplicate, "message": service.DUPLICATE_MESSAGE}]},
        )

    clashes = service.team_clashes(  # step 11
        session, host_id, [team.model_dump() for team in data.teams]
    )
    if clashes:
        raise AdminValidationError(clashes)

    row = service.new_request(host_id, game.id, data, token, now)  # step 12
    session.add(row)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        mapped = handle_integrity(exc, {"challenge": "altcha"})
        if mapped.errors[0].field != "altcha":
            raise mapped from exc
        _outcome("challenge_reused")
        raise _altcha_error() from exc
    _outcome("stored")
    return {}
