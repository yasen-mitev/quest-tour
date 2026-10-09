"""Admin: what the players thought (issue #38) – the average stars per riddle across every team, and
the words teams left for the host."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select

from questtour.admin.crud import get_admin_host_id
from questtour.api.deps import SessionDep
from questtour.auth import AdminSession, require_admin
from questtour.models import (
    Assignment,
    Game,
    GameRun,
    Landmark,
    RiddleRating,
    RunFeedback,
    RunTask,
    Team,
)

router = APIRouter(prefix="/feedback", tags=["admin-feedback"])


class RiddleRatingOut(BaseModel):
    landmark_id: int
    landmark_name: str
    average: float
    count: int


class TeamCommentOut(BaseModel):
    id: int
    team_name: str
    game_name: str
    submitted_at: datetime
    text: str


class FeedbackOut(BaseModel):
    riddles: list[RiddleRatingOut]  # best rated first
    comments: list[TeamCommentOut]  # newest first


@router.get("", response_model=FeedbackOut)
def feedback(
    session: SessionDep,
    admin: Annotated[AdminSession, Depends(require_admin)],
    host_id: str = Depends(get_admin_host_id),
):
    riddles = session.execute(
        select(
            Landmark.id,
            Landmark.name,
            func.avg(RiddleRating.stars).label("average"),
            func.count(RiddleRating.id).label("count"),
        )
        .join(RunTask, RunTask.landmark_id == Landmark.id)
        .join(RiddleRating, RiddleRating.run_task_id == RunTask.id)
        .where(Landmark.host_id == host_id)
        .group_by(Landmark.id, Landmark.name)
        .order_by(func.avg(RiddleRating.stars).desc(), Landmark.name)
    ).all()
    comments = session.execute(
        select(RunFeedback.id, Team.name, Game.name, RunFeedback.submitted_at, RunFeedback.text)
        .join(GameRun, RunFeedback.run_id == GameRun.id)
        .join(Assignment, GameRun.assignment_id == Assignment.id)
        .join(Team, Assignment.team_id == Team.id)
        .join(Game, Assignment.game_id == Game.id)
        .where(Assignment.host_id == host_id)
        .order_by(RunFeedback.submitted_at.desc(), RunFeedback.id.desc())
    ).all()
    return FeedbackOut(
        riddles=[
            RiddleRatingOut(landmark_id=lid, landmark_name=name, average=round(float(avg), 2), count=count)
            for lid, name, avg, count in riddles
        ],
        comments=[
            TeamCommentOut(id=fid, team_name=team, game_name=game, submitted_at=at, text=text)
            for fid, team, game, at, text in comments
        ],
    )
