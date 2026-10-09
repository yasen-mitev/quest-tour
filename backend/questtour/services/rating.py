"""Riddle ratings and the closing word for the host (issue #38).

Each phone may rate every riddle the team has completed with one to five stars, right after the
riddle and changeable later; the team's average on the end screen is over all those ratings. Once
the run has ended, each phone may send one comment to the host. Neither costs anything, neither
changes the game, and neither bumps the run version (teammates need not see each other's stars).
"""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from questtour.models import GameRun, RiddleRating, RunFeedback, RunTask
from questtour.services.game import Outcome

MAX_STARS = 5


def rate_task(
    session: Session, run: GameRun, position: int, stars: int, device_id: str | None, now: datetime
) -> Outcome:
    if device_id is None or not 1 <= stars <= MAX_STARS:
        return Outcome.NOT_AVAILABLE
    if not 0 <= position < len(run.tasks):
        return Outcome.STALE
    task = run.tasks[position]
    if task.completed_at is None:
        return Outcome.STALE                                   # rate a riddle once it is solved or revealed
    rating = session.scalar(
        select(RiddleRating).where(
            RiddleRating.run_task_id == task.id, RiddleRating.device_id == device_id
        )
    )
    if rating is None:
        session.add(RiddleRating(run_task_id=task.id, device_id=device_id, stars=stars, rated_at=now))
    else:
        rating.stars, rating.rated_at = stars, now
    return Outcome.OK


def device_rating(session: Session, task: RunTask, device_id: str | None) -> int | None:
    if device_id is None:
        return None
    return session.scalar(
        select(RiddleRating.stars).where(
            RiddleRating.run_task_id == task.id, RiddleRating.device_id == device_id
        )
    )


def run_average(session: Session, run: GameRun) -> tuple[float | None, int]:
    """(average, count) over every rating of the run's tasks, from every phone."""
    row = session.execute(
        select(func.avg(RiddleRating.stars), func.count(RiddleRating.id))
        .join(RunTask, RiddleRating.run_task_id == RunTask.id)
        .where(RunTask.run_id == run.id)
    ).one()
    average, count = row
    return (round(float(average), 2) if count else None), int(count or 0)


def submit_feedback(
    session: Session, run: GameRun, text: str, device_id: str | None, now: datetime
) -> Outcome:
    if device_id is None:
        return Outcome.NOT_AVAILABLE
    if run.end_reason is None:
        return Outcome.STALE                                   # only after the game is over
    existing = session.scalar(
        select(RunFeedback).where(RunFeedback.run_id == run.id, RunFeedback.device_id == device_id)
    )
    if existing is None:                                       # one per phone; the first one stands
        session.add(RunFeedback(run_id=run.id, device_id=device_id, text=text.strip(), submitted_at=now))
    return Outcome.OK


def feedback_submitted(session: Session, run: GameRun, device_id: str | None) -> bool:
    if device_id is None:
        return False
    return (
        session.scalar(
            select(RunFeedback.id).where(RunFeedback.run_id == run.id, RunFeedback.device_id == device_id)
        )
        is not None
    )
