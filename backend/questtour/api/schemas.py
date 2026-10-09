from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from questtour.services.game import Outcome


class HintOut(BaseModel):
    number: Literal[1, 2]
    penalty_minutes: int
    available: bool
    opened: bool
    text: str | None
    text_i18n: dict[str, str]


class LandmarkOut(BaseModel):
    name: str
    name_i18n: dict[str, str]
    info: str
    info_i18n: dict[str, str]
    picture_url: str | None


class CompassOut(BaseModel):
    opened: bool
    lat: float
    lon: float
    penalty_minutes: int


class TaskOut(BaseModel):
    number: int
    text: str
    text_i18n: dict[str, str]
    picture_url: str | None
    hints: list[HintOut]
    wrong_attempts: int
    reveal_unlocked: bool
    reveal_unlocks_in_seconds: int | None
    completion: Literal["answered", "revealed"] | None
    revealed_answer: str | None
    reveal_penalty_minutes: int  # charged on this task (0 unless revealed); frozen, unlike game.P
    landmark: LandmarkOut | None
    photo_count: int
    compass: CompassOut | None
    rating: int | None  # this phone's 1–5 stars for the riddle (issue #38), once completed


class ClockOut(BaseModel):
    elapsed_seconds: int
    running: bool
    penalty_minutes: int
    remaining_seconds: int | None
    warning: bool


class GameOut(BaseModel):
    name: str
    intro: str
    task_count: int
    time_zone: str
    max_duration_minutes: int
    hint_penalties: list[int]
    reveal_after_attempts: int
    reveal_after_minutes: int
    reveal_penalty_minutes: int
    available_languages: list[str]


class TeamOut(BaseModel):
    name: str


class LeaderboardRowOut(BaseModel):
    rank: int
    team_name: str
    total_seconds: int
    hints_used: int
    is_you: bool


class ResultsOut(BaseModel):
    elapsed_seconds: int
    hints_used: int
    hint_penalty_minutes: int
    reveals_used: int
    reveal_penalty_minutes: int
    total_seconds: int | None
    rank: int | None
    shared_rank: bool
    tasks_completed: int
    end_reason: Literal["finished", "max_duration", "window_closed"]
    exit_message: str
    leaderboard: list[LeaderboardRowOut]
    average_rating: float | None  # the team's average over its riddle ratings (issue #38)
    ratings_count: int
    feedback_submitted: bool  # this phone has sent its word for the host


class GameState(BaseModel):
    version: int  # game_runs.version; assignments.version_floor before Start
    service: bool  # R-25: service (test) link — no time limits, Reset available
    status: Literal["not_started", "playing", "finished", "timed_out"]
    phase: Literal["task", "photo", "info", "results"] | None
    position: int
    game: GameOut
    team: TeamOut
    clock: ClockOut | None
    task: TaskOut | None
    results: ResultsOut | None


class ActionResult(BaseModel):
    outcome: Outcome
    state: GameState


# --- Memories album (issue #33): a finished run's photos and landmark stories ---------------------


class AlbumPhotoOut(BaseModel):
    id: int
    url: str  # /api/play/{token}/photos/{id}; only answers once the run has ended
    taken_at: datetime


class AlbumChapterOut(BaseModel):
    number: int
    landmark: str
    landmark_i18n: dict[str, str]
    story: str
    story_i18n: dict[str, str]
    reached_at: datetime
    photos: list[AlbumPhotoOut]


class AlbumOut(BaseModel):
    game: str
    team: str
    time_zone: str
    played_on: datetime
    ended_at: datetime
    end_reason: Literal["finished", "max_duration", "window_closed"]
    task_count: int
    total_seconds: int | None  # None unless the run finished
    rank: int | None
    shared_rank: bool
    host_message: str
    chapters: list[AlbumChapterOut]


class PositionIn(BaseModel):
    position: int = Field(ge=0)


class AnswerIn(PositionIn):
    answer: str = Field(min_length=1, max_length=500)


class HintIn(PositionIn):
    hint: Literal[1, 2]


class RateIn(PositionIn):
    stars: int = Field(ge=1, le=5)


class FeedbackIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


RevealIn = AdvanceIn = PositionIn
