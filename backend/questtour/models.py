from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from questtour.clock import utc_now
from questtour.db import Base, UTCDateTime


class Timestamped:
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
        server_default=func.now(),
    )


class Landmark(Timestamped, Base):
    __tablename__ = "landmarks"
    __table_args__ = (UniqueConstraint("host_id", "key", name="uq_landmarks_host_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    host_id: Mapped[str] = mapped_column(String(64))
    key: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(200))
    name_i18n: Mapped[dict[str, str] | None] = mapped_column(JSON)
    task_text: Mapped[str] = mapped_column(Text)
    task_text_i18n: Mapped[dict[str, str] | None] = mapped_column(JSON)
    task_image: Mapped[str | None] = mapped_column(String(200))  # blob name in images container
    accepted_answers: Mapped[list[str]] = mapped_column(JSON)  # [0] = answer shown on reveal
    hint1: Mapped[str | None] = mapped_column(Text)
    hint1_i18n: Mapped[dict[str, str] | None] = mapped_column(JSON)
    hint2: Mapped[str | None] = mapped_column(Text)
    hint2_i18n: Mapped[dict[str, str] | None] = mapped_column(JSON)
    info_text: Mapped[str] = mapped_column(Text)
    info_text_i18n: Mapped[dict[str, str] | None] = mapped_column(JSON)
    info_image: Mapped[str | None] = mapped_column(String(200))
    coordinates_lat: Mapped[float | None] = mapped_column(Float)
    coordinates_lon: Mapped[float | None] = mapped_column(Float)


class Game(Timestamped, Base):
    __tablename__ = "games"
    __table_args__ = (UniqueConstraint("host_id", "key", name="uq_games_host_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    host_id: Mapped[str] = mapped_column(String(64))
    key: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(200))
    intro: Mapped[str] = mapped_column(Text)
    time_zone: Mapped[str] = mapped_column(String(64))
    max_duration_minutes: Mapped[int] = mapped_column(Integer)
    reveal_after_attempts: Mapped[int] = mapped_column(Integer)  # N
    reveal_after_minutes: Mapped[int] = mapped_column(Integer)  # X
    reveal_penalty_minutes: Mapped[int] = mapped_column(Integer)  # P
    tasks: Mapped[list["GameTask"]] = relationship(
        order_by="GameTask.position", cascade="all, delete-orphan"
    )


class GameTask(Base):
    __tablename__ = "game_tasks"
    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer, primary_key=True)  # 0-based
    landmark_id: Mapped[int] = mapped_column(ForeignKey("landmarks.id"))
    landmark: Mapped[Landmark] = relationship()


class Team(Timestamped, Base):
    __tablename__ = "teams"
    __table_args__ = (
        UniqueConstraint("host_id", "key", name="uq_teams_host_key"),
        UniqueConstraint("host_id", "name", name="uq_teams_host_name"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    host_id: Mapped[str] = mapped_column(String(64))
    key: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(200))
    participants: Mapped[int | None] = mapped_column(Integer)
    # R-25: service (test) team — no time limits, resettable runs, never on a leaderboard
    is_service: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())


class Assignment(Timestamped, Base):
    __tablename__ = "assignments"
    __table_args__ = (UniqueConstraint("team_id", "game_id", name="uq_assignments_team_game"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    host_id: Mapped[str] = mapped_column(String(64))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)  # NULL = deactivated
    valid_from: Mapped[datetime] = mapped_column(UTCDateTime)
    valid_until: Mapped[datetime] = mapped_column(UTCDateTime)
    exit_message: Mapped[str] = mapped_column(Text)
    # R-25: a reset bumps this past the deleted run's version so phones never drop the fresh state
    version_floor: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    issued_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    team: Mapped[Team] = relationship()
    game: Mapped[Game] = relationship()


class GameRun(Base):
    __tablename__ = "game_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("assignments.id"), unique=True)  # R-13
    started_at: Mapped[datetime] = mapped_column(UTCDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)  # last task completed
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime)  # clock stopped (any reason)
    end_reason: Mapped[str | None] = mapped_column(
        String(20)
    )  # finished|max_duration|window_closed
    current_position: Mapped[int] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer)  # +1 on every state change; clients drop older
    assignment: Mapped[Assignment] = relationship()
    tasks: Mapped[list["RunTask"]] = relationship(
        order_by="RunTask.position", cascade="all, delete-orphan"
    )


class RunTask(Base):
    """Snapshot of the ordered landmark list at Start, plus per-task progress (R-3)."""

    __tablename__ = "run_tasks"
    __table_args__ = (UniqueConstraint("run_id", "position", name="uq_run_tasks_run_position"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("game_runs.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    landmark_id: Mapped[int] = mapped_column(ForeignKey("landmarks.id"))
    shown_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    completion: Mapped[str | None] = mapped_column(String(10))  # answered|revealed
    hint1_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    hint2_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    compass_opened_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    revealed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    hint_penalty_minutes: Mapped[int] = mapped_column(Integer)
    reveal_penalty_minutes: Mapped[int] = mapped_column(Integer)
    wrong_attempts: Mapped[int] = mapped_column(Integer)
    photo_count: Mapped[int] = mapped_column(Integer)
    landmark: Mapped[Landmark] = relationship()


class AnswerAttempt(Base):
    __tablename__ = "answer_attempts"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_task_id: Mapped[int] = mapped_column(ForeignKey("run_tasks.id", ondelete="CASCADE"))
    device_id: Mapped[str | None] = mapped_column(String(64))
    submitted_at: Mapped[datetime] = mapped_column(UTCDateTime)
    answer_text: Mapped[str] = mapped_column(Text)
    correct: Mapped[bool] = mapped_column(Boolean)


class Photo(Base):
    __tablename__ = "photos"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_task_id: Mapped[int] = mapped_column(ForeignKey("run_tasks.id", ondelete="CASCADE"))
    device_id: Mapped[str | None] = mapped_column(String(64))
    uploaded_at: Mapped[datetime] = mapped_column(UTCDateTime)
    blob_name: Mapped[str] = mapped_column(String(500), unique=True)
    content_type: Mapped[str] = mapped_column(String(50))
    size_bytes: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utc_now, onupdate=utc_now, nullable=False, server_default=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True, index=True)


class RiddleRating(Base):
    """One to five stars for a riddle (issue #38): one per phone per task, changeable."""

    __tablename__ = "riddle_ratings"
    __table_args__ = (UniqueConstraint("run_task_id", "device_id", name="uq_riddle_ratings_task_device"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    run_task_id: Mapped[int] = mapped_column(ForeignKey("run_tasks.id", ondelete="CASCADE"))
    device_id: Mapped[str] = mapped_column(String(64))
    stars: Mapped[int] = mapped_column(Integer)
    rated_at: Mapped[datetime] = mapped_column(UTCDateTime)


class RunFeedback(Base):
    """A word for the host at the end of the game (issue #38): one per phone per run."""

    __tablename__ = "run_feedback"
    __table_args__ = (UniqueConstraint("run_id", "device_id", name="uq_run_feedback_run_device"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("game_runs.id", ondelete="CASCADE"))
    device_id: Mapped[str] = mapped_column(String(64))
    text: Mapped[str] = mapped_column(Text)
    submitted_at: Mapped[datetime] = mapped_column(UTCDateTime)


class TeamAlbum(Base):
    """The stored memories album PDF of a finished run (issue #33): one per assignment, kept in the
    albums container for the host; ``deleted_at`` set means the host removed it (players get 410)."""

    __tablename__ = "team_albums"
    id: Mapped[int] = mapped_column(primary_key=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("assignments.id"), unique=True)
    blob_name: Mapped[str] = mapped_column(String(500), unique=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    generated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    assignment: Mapped[Assignment] = relationship()


class RunDevice(Base):
    __tablename__ = "run_devices"
    run_id: Mapped[int] = mapped_column(
        ForeignKey("game_runs.id", ondelete="CASCADE"), primary_key=True
    )
    device_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    first_seen_at: Mapped[datetime] = mapped_column(UTCDateTime)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime)
