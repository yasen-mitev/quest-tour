import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from questtour.api.deps import DeviceDep, NowDep, SessionDep
from questtour.api.schemas import (
    ActionResult,
    AlbumOut,
    AnswerIn,
    FeedbackIn,
    GameState,
    HintIn,
    PositionIn,
    RateIn,
)
from questtour.imagetypes import sniff_photo
from questtour.models import Assignment, GameRun
from questtour.services import game as rules
from questtour.services.access import ensure_link_usable, find_assignment
from questtour.services.album import album_available, build_album, find_run_photo
from questtour.services.album_store import PDF, album_file_name, ensure_album
from questtour.services.photos import save_photo
from questtour.services.rating import rate_task, submit_feedback
from questtour.services.reset import delete_photo_blobs, reset_run
from questtour.services.state import build_state
from questtour.storage import StorageUnavailable

log = logging.getLogger("questtour.play")
router = APIRouter(prefix="/api/play/{token}", tags=["play"])


@dataclass
class Ctx:
    session: Session
    assignment: Assignment
    run: GameRun | None
    now: datetime
    device_id: str | None


def _open(
    session: Session,
    token: str,
    now: datetime,
    device_id: str | None,
    *,
    lock_assignment: bool = False,
) -> Ctx:
    assignment = find_assignment(session, token, lock=lock_assignment)
    run = rules.load_run(session, assignment.id)
    ensure_link_usable(assignment, run, now)
    if run is not None:
        rules.apply_time_limits(run, assignment, now)
        rules.touch_device(session, run, device_id, now)
    return Ctx(session, assignment, run, now, device_id)


def _respond(ctx: Ctx, outcome: rules.Outcome, action: str) -> ActionResult:
    state = build_state(ctx.session, ctx.assignment, ctx.run, ctx.now, ctx.device_id)
    ctx.session.commit()
    log.info("action=%s assignment=%s outcome=%s", action, ctx.assignment.id, outcome)
    return ActionResult(outcome=outcome, state=state)


@router.get("", response_model=GameState)
def get_state(token: str, session: SessionDep, now: NowDep, device_id: DeviceDep) -> GameState:
    ctx = _open(session, token, now, device_id)
    state = build_state(session, ctx.assignment, ctx.run, now, device_id)
    session.commit()
    return state


@router.post("/start", response_model=ActionResult)
def start(token: str, session: SessionDep, now: NowDep, device_id: DeviceDep) -> ActionResult:
    ctx = _open(session, token, now, device_id, lock_assignment=True)
    if ctx.run is not None:
        return _respond(ctx, rules.Outcome.ALREADY_STARTED, "start")
    ctx.run = rules.start_run(session, ctx.assignment, now)
    rules.touch_device(session, ctx.run, device_id, now)
    return _respond(ctx, rules.Outcome.OK, "start")


@router.post("/answer", response_model=ActionResult)
def answer(
    token: str, body: AnswerIn, session: SessionDep, now: NowDep, device_id: DeviceDep
) -> ActionResult:
    ctx = _open(session, token, now, device_id)
    outcome = (
        rules.Outcome.STALE
        if ctx.run is None
        else rules.submit_answer(session, ctx.run, body.position, body.answer, now, device_id)
    )
    return _respond(ctx, outcome, "answer")


@router.post("/hint", response_model=ActionResult)
def hint(
    token: str, body: HintIn, session: SessionDep, now: NowDep, device_id: DeviceDep
) -> ActionResult:
    ctx = _open(session, token, now, device_id)
    outcome = (
        rules.Outcome.STALE
        if ctx.run is None
        else rules.open_hint(ctx.run, body.position, body.hint, now)
    )
    return _respond(ctx, outcome, "hint")


@router.post("/compass", response_model=ActionResult)
def compass(
    token: str, session: SessionDep, now: NowDep, device_id: DeviceDep
) -> ActionResult:
    ctx = _open(session, token, now, device_id)
    outcome = (
        rules.Outcome.STALE
        if ctx.run is None
        else rules.open_compass(ctx.run, now)
    )
    return _respond(ctx, outcome, "compass")


@router.post("/reveal", response_model=ActionResult)
def reveal(
    token: str, body: PositionIn, session: SessionDep, now: NowDep, device_id: DeviceDep
) -> ActionResult:
    ctx = _open(session, token, now, device_id)
    outcome = (
        rules.Outcome.STALE
        if ctx.run is None
        else rules.reveal_answer(
            ctx.run,
            ctx.assignment.game,
            body.position,
            now,
            instant=rules.is_service(ctx.assignment),
        )
    )
    return _respond(ctx, outcome, "reveal")


@router.post("/rate", response_model=ActionResult)
def rate(
    token: str, body: RateIn, session: SessionDep, now: NowDep, device_id: DeviceDep
) -> ActionResult:
    """Issue #38: one to five stars for a completed riddle, one rating per phone, changeable."""
    ctx = _open(session, token, now, device_id)
    outcome = (
        rules.Outcome.STALE
        if ctx.run is None
        else rate_task(session, ctx.run, body.position, body.stars, device_id, now)
    )
    return _respond(ctx, outcome, "rate")


@router.post("/feedback", response_model=ActionResult)
def feedback(
    token: str, body: FeedbackIn, session: SessionDep, now: NowDep, device_id: DeviceDep
) -> ActionResult:
    """Issue #38: a word for the host once the game is over, one per phone."""
    ctx = _open(session, token, now, device_id)
    outcome = (
        rules.Outcome.STALE
        if ctx.run is None
        else submit_feedback(session, ctx.run, body.text, device_id, now)
    )
    return _respond(ctx, outcome, "feedback")


@router.post("/advance", response_model=ActionResult)
def advance(
    token: str, body: PositionIn, session: SessionDep, now: NowDep, device_id: DeviceDep
) -> ActionResult:
    ctx = _open(session, token, now, device_id)
    outcome = (
        rules.Outcome.STALE
        if ctx.run is None
        else rules.advance(
            ctx.run, body.position, now, service=rules.is_service(ctx.assignment)
        )
    )
    return _respond(ctx, outcome, "advance")


@router.post("/photo", response_model=ActionResult)
def photo(
    token: str,
    request: Request,
    session: SessionDep,
    now: NowDep,
    device_id: DeviceDep,
    position: Annotated[int, Form(ge=0)],
    file: Annotated[UploadFile, File()],
) -> ActionResult:
    settings = request.app.state.settings
    ctx = _open(session, token, now, device_id)
    data = file.file.read(settings.max_photo_bytes + 1)
    if len(data) > settings.max_photo_bytes:
        raise HTTPException(413, "Photo is larger than 20 MB")
    kind = sniff_photo(data[:32])
    if kind is None:
        raise HTTPException(415, "Unsupported photo type (JPEG, PNG, HEIC or WebP)")
    if ctx.run is None:
        return _respond(ctx, rules.Outcome.STALE, "photo")
    try:
        outcome = save_photo(
            session,
            request.app.state.blob_store,
            settings.photos_container,
            ctx.run,
            ctx.assignment,
            position,
            data,
            kind,
            now,
            device_id,
        )
    except StorageUnavailable as exc:
        log.exception("photo upload failed")
        raise HTTPException(503, "Storage unavailable, please retry") from exc
    return _respond(ctx, outcome, "photo")


@router.get("/album", response_model=AlbumOut)
def album(token: str, session: SessionDep, now: NowDep, device_id: DeviceDep) -> AlbumOut:
    """The memories album (issue #33). 409 until the run has ended: during the game players never
    see their photos (R-10)."""
    ctx = _open(session, token, now, device_id)
    if not album_available(ctx.run):
        session.commit()
        raise HTTPException(409, "album_not_ready")
    result = build_album(session, ctx.assignment, ctx.run, token, now)
    session.commit()
    return result


@router.get("/album.pdf")
def album_pdf(
    token: str, request: Request, session: SessionDep, now: NowDep, device_id: DeviceDep
) -> Response:
    """The album as a PDF file, rendered once and stored for the host (issue #33). 409 while the
    game is on; 410 once the host has removed the album."""
    ctx = _open(session, token, now, device_id)
    if not album_available(ctx.run):
        session.commit()
        raise HTTPException(409, "album_not_ready")
    settings = request.app.state.settings
    store = request.app.state.blob_store
    try:
        record = ensure_album(session, store, settings, ctx.assignment, ctx.run, now)
        found = store.get(settings.albums_container, record.blob_name) if record else None
    except StorageUnavailable as exc:
        session.rollback()
        raise HTTPException(503, "Storage unavailable, please retry") from exc
    session.commit()
    if record is None:
        raise HTTPException(410, "album_removed")
    if found is None:
        raise HTTPException(404, "Not Found")
    data, _content_type = found
    return Response(
        data,
        media_type=PDF,
        headers={
            "Content-Disposition": f'attachment; filename="{album_file_name(ctx.assignment.team.name)}"',
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/photos/{photo_id}")
def album_photo(
    token: str, photo_id: int, request: Request, session: SessionDep, now: NowDep, device_id: DeviceDep
) -> Response:
    """A team photo for the album: this run's own, live photos only, and only once the run has ended."""
    ctx = _open(session, token, now, device_id)
    photo = find_run_photo(session, ctx.run, photo_id) if album_available(ctx.run) else None
    session.commit()
    if photo is None:
        raise HTTPException(404, "Not Found")
    settings = request.app.state.settings
    try:
        found = request.app.state.blob_store.get(settings.photos_container, photo.blob_name)
    except StorageUnavailable as exc:
        raise HTTPException(503, "Storage unavailable, please retry") from exc
    if found is None:
        raise HTTPException(404, "Not Found")
    data, content_type = found
    return Response(
        data,
        media_type=content_type,
        headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"},
    )


@router.post("/reset", response_model=ActionResult)
def reset(
    token: str, request: Request, session: SessionDep, now: NowDep, device_id: DeviceDep
) -> ActionResult:
    """R-25: service (test) links only — wipe the run so the same link starts from scratch."""
    assignment = find_assignment(session, token, lock=True)
    if not rules.is_service(assignment):
        raise HTTPException(404, "Not Found")  # invisible to real teams
    run = rules.load_run(session, assignment.id)
    blob_names = reset_run(session, assignment, run) if run is not None else []
    result = _respond(Ctx(session, assignment, None, now, device_id), rules.Outcome.OK, "reset")
    settings = request.app.state.settings
    delete_photo_blobs(request.app.state.blob_store, settings.photos_container, blob_names)
    return result
