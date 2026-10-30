"""The memories album (issue #33): everything a finished run collected, in reading order.

One chapter per task the team completed – the landmark, its story, how long the riddle took and
every photo the team took there – plus the facts of the day. Available only once the run has ended (finished or timed out):
during the game players never see photos (R-10). Photo bytes are served by the player API through
``photo_url``, which checks the same things again.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from questtour.api.schemas import AlbumChapterOut, AlbumOut, AlbumPhotoOut
from questtour.models import Assignment, GameRun, Photo, RunTask
from questtour.services.game import total_seconds
from questtour.services.leaderboard import leaderboard_rows


def album_available(run: GameRun | None) -> bool:
    return run is not None and run.end_reason is not None


def photo_url(token: str, photo_id: int) -> str:
    return f"/api/play/{token}/photos/{photo_id}"


def run_photos(session: Session, run: GameRun) -> dict[int, list[Photo]]:
    """Live photos of the run, by run task id, oldest first."""
    rows = session.scalars(
        select(Photo)
        .join(RunTask, Photo.run_task_id == RunTask.id)
        .where(RunTask.run_id == run.id, Photo.deleted_at.is_(None))
        .order_by(Photo.uploaded_at, Photo.id)
    ).all()
    by_task: dict[int, list[Photo]] = {}
    for photo in rows:
        by_task.setdefault(photo.run_task_id, []).append(photo)
    return by_task


def find_run_photo(session: Session, run: GameRun, photo_id: int) -> Photo | None:
    """A live photo of *this* run, or None: a photo id from another team's run is simply unknown."""
    return session.scalar(
        select(Photo)
        .join(RunTask, Photo.run_task_id == RunTask.id)
        .where(Photo.id == photo_id, RunTask.run_id == run.id, Photo.deleted_at.is_(None))
    )


def build_album(
    session: Session, assignment: Assignment, run: GameRun, token: str, now: datetime
) -> AlbumOut:
    game, team = assignment.game, assignment.team
    photos = run_photos(session, run)
    rows = leaderboard_rows(session, assignment.game_id, viewer_run_id=run.id)
    me = next((row for row in rows if row.is_you), None)
    chapters = [
        AlbumChapterOut(
            number=task.position + 1,
            landmark=task.landmark.name,
            landmark_i18n=task.landmark.name_i18n or {},
            story=task.landmark.info_text,
            story_i18n=task.landmark.info_text_i18n or {},
            reached_at=task.completed_at,
            seconds=(
                max(0, int((task.completed_at - task.shown_at).total_seconds()))
                if task.shown_at is not None
                else None
            ),
            hints=(task.hint1_at is not None) + (task.hint2_at is not None) + (task.compass_opened_at is not None),
            penalty_minutes=task.hint_penalty_minutes + task.reveal_penalty_minutes,
            photos=[
                AlbumPhotoOut(id=photo.id, url=photo_url(token, photo.id), taken_at=photo.uploaded_at)
                for photo in photos.get(task.id, [])
            ],
        )
        for task in run.tasks
        if task.completed_at is not None
    ]
    return AlbumOut(
        game=game.name,
        team=team.name,
        time_zone=game.time_zone,
        played_on=run.started_at,
        ended_at=run.ended_at or now,
        end_reason=run.end_reason,
        task_count=len(run.tasks),
        total_seconds=total_seconds(run) if run.end_reason == "finished" else None,
        rank=me.rank if me else None,
        shared_rank=me is not None and sum(1 for row in rows if row.rank == me.rank) > 1,
        host_message=assignment.exit_message,
        chapters=chapters,
    )
