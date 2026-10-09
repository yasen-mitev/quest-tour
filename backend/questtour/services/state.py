import math
from collections.abc import Sequence
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from questtour.api.schemas import (
    ClockOut,
    CompassOut,
    GameOut,
    GameState,
    HintOut,
    LandmarkOut,
    ResultsOut,
    TaskOut,
    TeamOut,
)
from questtour.models import Assignment, Game, GameRun, GameTask, RunTask
from questtour.services.game import (
    COMPASS_PENALTY_MINUTES,
    HINT_PENALTIES,
    TIMED_OUT,
    WARNING_SECONDS,
    active_seconds,
    apply_time_limits,
    current_task,
    effective_deadline,
    elapsed_seconds,
    hints_used,
    is_service,
    penalty_minutes,
    reveal_unlocked,
    run_status,
    total_seconds,
)
from questtour.services.i18n import pick_text
from questtour.services.leaderboard import leaderboard_rows
from questtour.services.rating import device_rating, feedback_submitted, run_average


def image_url(blob_name: str | None) -> str | None:
    return f"/api/images/{blob_name}" if blob_name else None


def run_phase(run: GameRun, assignment: Assignment, now: datetime) -> str:
    if run.end_reason in TIMED_OUT:
        return "results"
    task = current_task(run)
    if task is None:
        return "results"
    if run.end_reason == "finished" and not is_service(assignment) and now >= assignment.valid_until:
        return "results"  # finished team re-opening after the window: straight to Finish
    if task.completed_at is None:
        return "task"
    return "photo" if task.photo_count == 0 else "info"


def build_game(game: Game, tasks: Sequence[GameTask | RunTask]) -> GameOut:
    languages = {
        code
        for task in tasks
        if (landmark := getattr(task, "landmark", None))
        for col in (
            landmark.name_i18n,
            landmark.task_text_i18n,
            landmark.hint1_i18n,
            landmark.hint2_i18n,
            landmark.info_text_i18n,
        )
        if col
        for code in col
    }
    return GameOut(
        name=game.name,
        intro=game.intro,
        task_count=len(tasks),
        time_zone=game.time_zone,
        max_duration_minutes=game.max_duration_minutes,
        hint_penalties=[HINT_PENALTIES[1], HINT_PENALTIES[2]],
        reveal_after_attempts=game.reveal_after_attempts,
        reveal_after_minutes=game.reveal_after_minutes,
        reveal_penalty_minutes=game.reveal_penalty_minutes,
        available_languages=sorted(languages),
    )


def build_clock(run: GameRun, assignment: Assignment, now: datetime) -> ClockOut:
    task = current_task(run)
    # The clock freezes on the photo/landmark screens: the pause between completing the current
    # task and showing the next one is not active time (R-7), so `running` goes false there.
    running = run.end_reason is None and task is not None and task.completed_at is None
    remaining = None
    if run.end_reason is None and not is_service(assignment):  # R-25: service runs have no deadline
        budget, _ = effective_deadline(run, assignment)
        # Rounded UP: 0 only once the budget is spent (and then apply_time_limits has already ended
        # the run). Flooring would send `running: true, remaining_seconds: 0` during the last second, and
        # GameHeader would re-request on every response until the deadline (§10.1 onTimeUp).
        # During a pause active_seconds stands still, so the countdown freezes with the clock.
        remaining = max(0, math.ceil(budget - active_seconds(run, now)))
    return ClockOut(
        elapsed_seconds=elapsed_seconds(run, now),
        running=running,
        penalty_minutes=penalty_minutes(run),
        remaining_seconds=remaining,
        warning=remaining is not None and remaining <= WARNING_SECONDS,
    )


def build_task(
    task: RunTask,
    game: Game,
    now: datetime,
    *,
    instant: bool = False,
    rating: int | None = None,
) -> TaskOut:
    landmark = task.landmark
    completed = task.completed_at is not None
    hints: list[HintOut] = []
    for number, text, i18n, opened_at in (
        (1, landmark.hint1, landmark.hint1_i18n, task.hint1_at),
        (2, landmark.hint2, landmark.hint2_i18n, task.hint2_at),
    ):
        if not text and opened_at is None:
            continue
        opened = opened_at is not None
        hints.append(
            HintOut(
                number=number,
                penalty_minutes=HINT_PENALTIES[number],
                opened=opened,
                available=not opened and not completed and (number == 1 or task.hint1_at is not None),
                text=(pick_text(text or "", i18n, "en") if opened else None),  # unopened hint text never leaves the server
                text_i18n=(i18n or {}) if opened else {},
            )
        )
    unlocked = not completed and reveal_unlocked(task, game, now, instant=instant)
    unlocks_in = None
    if not completed and not unlocked:
        due = task.shown_at + timedelta(minutes=game.reveal_after_minutes)
        unlocks_in = max(0, math.ceil((due - now).total_seconds()))
    compass = None
    if landmark.coordinates_lat is not None and landmark.coordinates_lon is not None:
        compass = CompassOut(
            opened=task.compass_opened_at is not None,
            lat=landmark.coordinates_lat,
            lon=landmark.coordinates_lon,
            penalty_minutes=COMPASS_PENALTY_MINUTES,
        )
    return TaskOut(
        number=task.position + 1,
        text=landmark.task_text,
        text_i18n=landmark.task_text_i18n or {},
        picture_url=image_url(landmark.task_image),
        hints=hints,
        wrong_attempts=task.wrong_attempts,
        reveal_unlocked=unlocked,
        reveal_unlocks_in_seconds=unlocks_in,
        completion=task.completion,
        revealed_answer=landmark.accepted_answers[0] if task.completion == "revealed" else None,
        reveal_penalty_minutes=task.reveal_penalty_minutes,
        landmark=LandmarkOut(
            name=landmark.name,
            name_i18n=landmark.name_i18n or {},
            info=landmark.info_text,
            info_i18n=landmark.info_text_i18n or {},
            picture_url=image_url(landmark.info_image),
        )
        if completed
        else None,
        photo_count=task.photo_count,
        compass=compass,
        rating=rating if completed else None,
    )


def build_results(
    session: Session,
    run: GameRun,
    assignment: Assignment,
    now: datetime,
    device_id: str | None = None,
) -> ResultsOut:
    rows = leaderboard_rows(session, assignment.game_id, viewer_run_id=run.id)
    me = next((row for row in rows if row.is_you), None)
    average, count = run_average(session, run)
    return ResultsOut(
        elapsed_seconds=elapsed_seconds(run, now),
        hints_used=hints_used(run),
        hint_penalty_minutes=sum(t.hint_penalty_minutes for t in run.tasks),
        reveals_used=sum(1 for t in run.tasks if t.revealed_at is not None),
        reveal_penalty_minutes=sum(t.reveal_penalty_minutes for t in run.tasks),
        total_seconds=total_seconds(run) if run.end_reason == "finished" else None,
        rank=me.rank if me else None,
        shared_rank=me is not None and sum(1 for row in rows if row.rank == me.rank) > 1,
        tasks_completed=sum(1 for t in run.tasks if t.completed_at is not None),
        end_reason=run.end_reason,
        exit_message=assignment.exit_message,
        leaderboard=rows,
        average_rating=average,
        ratings_count=count,
        feedback_submitted=feedback_submitted(session, run, device_id),
    )


def build_state(
    session: Session,
    assignment: Assignment,
    run: GameRun | None,
    now: datetime,
    device_id: str | None = None,
) -> GameState:
    game, team = assignment.game, assignment.team
    service = is_service(assignment)
    if run is None:
        return GameState(
            version=assignment.version_floor,
            service=service,
            status="not_started",
            phase=None,
            position=0,
            game=build_game(game, game.tasks),
            team=TeamOut(name=team.name),
            clock=None,
            task=None,
            results=None,
        )
    apply_time_limits(run, assignment, now)
    phase = run_phase(run, assignment, now)
    task = current_task(run) if phase != "results" else None
    return GameState(
        version=run.version,
        service=service,
        status=run_status(run),
        phase=phase,
        position=run.current_position,
        game=build_game(game, run.tasks),
        team=TeamOut(name=team.name),
        clock=build_clock(run, assignment, now),
        task=(
            build_task(task, game, now, instant=service, rating=device_rating(session, task, device_id))
            if task is not None
            else None
        ),
        results=build_results(session, run, assignment, now, device_id) if phase == "results" else None,
    )
