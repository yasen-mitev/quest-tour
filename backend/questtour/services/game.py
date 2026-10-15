from datetime import datetime, timedelta
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from questtour.models import AnswerAttempt, Assignment, Game, GameRun, RunDevice, RunTask
from questtour.normalize import is_correct

HINT_PENALTIES: dict[int, int] = {1: 10, 2: 15}   # R-4 (fixed, not per game)
COMPASS_PENALTY_MINUTES: int = 5                   # R-26
PHOTO_GRACE_SECONDS = 5 * 60                       # issue #49: each task pause is free for 5 minutes
WARNING_SECONDS = 15 * 60                         # R-8, R-14
TIMED_OUT = frozenset({"max_duration", "window_closed"})


class Outcome(StrEnum):
    OK = "ok"
    ALREADY_STARTED = "already_started"
    CORRECT = "correct"
    WRONG = "wrong"
    STALE = "stale"
    LOCKED = "locked"
    NOT_AVAILABLE = "not_available"
    GAME_OVER = "game_over"


def load_run(session: Session, assignment_id: int) -> GameRun | None:
    """Locks the run row: every action is serialised per team (technical §3, R-18)."""
    stmt = (
        select(GameRun)
        .where(GameRun.assignment_id == assignment_id)
        .with_for_update()
        .options(selectinload(GameRun.tasks).selectinload(RunTask.landmark))
    )
    return session.scalars(stmt).one_or_none()


def current_task(run: GameRun) -> RunTask | None:
    return run.tasks[run.current_position] if run.current_position < len(run.tasks) else None


def run_status(run: GameRun) -> str:
    if run.end_reason is None:
        return "playing"
    return "finished" if run.end_reason == "finished" else "timed_out"


def effective_deadline(run: GameRun, assignment: Assignment) -> tuple[int, str]:
    """Active-time budgets (R-8): the run ends when its active time reaches the game's max
    duration or the assignment's remaining window (valid_until - started_at), whichever is
    smaller. Solving time spends the budget, and so does a pause past its 5-minute grace (issue #49)."""
    by_duration = assignment.game.max_duration_minutes * 60
    by_window = max(0, int((assignment.valid_until - run.started_at).total_seconds()))
    if by_window < by_duration:
        return by_window, "window_closed"
    return by_duration, "max_duration"


def is_service(assignment: Assignment) -> bool:
    """R-25: a service (test) team's links ignore every time limit and can be reset."""
    return assignment.team.is_service


def apply_time_limits(run: GameRun, assignment: Assignment, now: datetime) -> None:
    """R-8: called on every request; the end time is the moment the budget was spent, not the
    request time. A paused run spends nothing for the first 5 minutes of its pause; past that
    grace the pause counts like solving time and can end the run (issue #49).
    Service runs (R-25) never end by time."""
    if run.end_reason is not None or is_service(assignment):
        return
    task = current_task(run)
    if task is None or task.shown_at is None:
        return
    budget, reason = effective_deadline(run, assignment)
    solved = sum(
        (t.completed_at - t.shown_at).total_seconds()
        for t in run.tasks
        if t.shown_at is not None and t.completed_at is not None
    )
    if task.completed_at is None:                    # riddle on the clock
        spent = solved + pause_overage_seconds(run, now)   # earlier pauses are all closed here
        left = budget - spent
        if (now - task.shown_at).total_seconds() >= left:
            run.ended_at = task.shown_at + timedelta(seconds=max(0, left))
            run.end_reason = reason
            bump(run)
    else:                                            # paused between tasks (issue #49)
        # Passing completed_at as `now` zeroes the still-open pause, so only the closed pauses'
        # overages count toward what is already spent; the open pause spends budget from
        # completed_at + grace onwards.
        spent = solved + pause_overage_seconds(run, task.completed_at)
        left = budget - spent
        free_until = task.completed_at + timedelta(seconds=PHOTO_GRACE_SECONDS)
        if (now - free_until).total_seconds() >= left:
            run.ended_at = free_until + timedelta(seconds=max(0, left))
            run.end_reason = reason
            bump(run)


def bump(run: GameRun) -> None:
    """Every write that changes what players see increments the version (client ordering, §9.4)."""
    run.version += 1


def _pause_seconds(run: GameRun, index: int, now: datetime) -> float:
    """Length of task `index`'s pause: from its completed_at to the moment the next task was
    shown; the still-open pause of the current completed task runs to `ended_at` (or `now`).
    A task that is not completed has no pause, and the last task's completion ends the run
    (finished_at == completed_at), so a finished run has none either."""
    task = run.tasks[index]
    if task.completed_at is None:
        return 0.0
    following = run.tasks[index + 1] if index + 1 < len(run.tasks) else None
    if following is not None and following.shown_at is not None:
        end: datetime = following.shown_at
    else:
        end = run.ended_at or now
    return max(0.0, (end - task.completed_at).total_seconds())


def pause_overage_seconds(run: GameRun, now: datetime) -> float:
    """The part of every task pause beyond the 5-minute grace (issue #49); past the grace a
    pause counts like solving time. Each pause gets its own grace."""
    return sum(
        max(0.0, _pause_seconds(run, index, now) - PHOTO_GRACE_SECONDS)
        for index, task in enumerate(run.tasks)
        if task.completed_at is not None
    )


def active_seconds(run: GameRun, now: datetime) -> int:
    """Active time on the clock: the sum of per-task solving intervals shown_at → completed_at
    (the still-open interval of the unfinished current task running to `ended_at` or `now`), plus
    the part of every pause beyond the 5-minute grace (issue #49). The first 5 minutes of a pause
    count toward nothing — no score, no deadline."""
    total = 0.0
    for task in run.tasks:
        if task.shown_at is None:
            continue
        end = task.completed_at if task.completed_at is not None else run.ended_at or now
        total += max(0, (end - task.shown_at).total_seconds())
    return int(total + pause_overage_seconds(run, now))


def elapsed_seconds(run: GameRun, now: datetime) -> int:
    """Alias of active_seconds: every clock in the app runs on active time."""
    return active_seconds(run, now)


def penalty_minutes(run: GameRun) -> int:
    return sum(t.hint_penalty_minutes + t.reveal_penalty_minutes for t in run.tasks)


def hints_used(run: GameRun) -> int:
    # R-12: the leaderboard "hints used" column counts hints + compasses.
    return sum(
        (t.hint1_at is not None) + (t.hint2_at is not None) + (t.compass_opened_at is not None)
        for t in run.tasks
    )


def total_seconds(run: GameRun) -> int:
    """R-7: active riddle-solving time + penalties. Only meaningful for finished runs."""
    assert run.finished_at is not None
    return active_seconds(run, run.finished_at) + 60 * penalty_minutes(run)


def reveal_unlocked(task: RunTask, game: Game, now: datetime, *, instant: bool = False) -> bool:
    """R-6: after N wrong attempts or X minutes on the task, whichever comes first.
    `instant` (service links, R-25) unlocks it as soon as the task is shown."""
    return (
        instant
        or task.wrong_attempts >= game.reveal_after_attempts
        or now >= task.shown_at + timedelta(minutes=game.reveal_after_minutes)
    )


def touch_device(session: Session, run: GameRun, device_id: str | None, now: datetime) -> None:
    if device_id is None:
        return
    device = session.get(RunDevice, (run.id, device_id))
    if device is None:
        session.add(
            RunDevice(run_id=run.id, device_id=device_id, first_seen_at=now, last_seen_at=now)
        )
    else:
        device.last_seen_at = now


def start_run(session: Session, assignment: Assignment, now: datetime) -> GameRun:
    """Caller holds the assignment row lock and has checked no run exists. Snapshots the landmark order.
    Starts above assignment.version_floor so a reset (R-25) never makes phones drop newer states."""
    run = GameRun(
        assignment=assignment,
        started_at=now,
        current_position=0,
        version=assignment.version_floor + 1,
    )
    for position, game_task in enumerate(assignment.game.tasks):
        run.tasks.append(
            RunTask(
                position=position,
                landmark_id=game_task.landmark_id,
                hint_penalty_minutes=0,
                reveal_penalty_minutes=0,
                wrong_attempts=0,
                photo_count=0,
            )
        )
    run.tasks[0].shown_at = now
    session.add(run)
    session.flush()
    return run


def _open_task(run: GameRun, position: int) -> tuple[RunTask | None, Outcome | None]:
    if run.end_reason in TIMED_OUT:
        return None, Outcome.GAME_OVER
    task = current_task(run)
    if run.current_position != position or task is None or task.completed_at is not None:
        return None, Outcome.STALE
    return task, None


def _complete(run: GameRun, task: RunTask, kind: str, now: datetime) -> None:
    task.completed_at, task.completion = now, kind
    bump(run)
    if task.position == len(run.tasks) - 1:          # R-2: clock stops at the last completion
        run.finished_at = run.ended_at = now
        run.end_reason = "finished"


def submit_answer(
    session: Session,
    run: GameRun,
    position: int,
    answer: str,
    now: datetime,
    device_id: str | None,
) -> Outcome:
    task, blocked = _open_task(run, position)
    if blocked:
        if blocked == Outcome.STALE and 0 <= position < len(run.tasks):   # R-5: log teammates' late answers too
            late = run.tasks[position]
            session.add(
                AnswerAttempt(
                    run_task_id=late.id,
                    device_id=device_id,
                    submitted_at=now,
                    answer_text=answer,
                    correct=is_correct(answer, late.landmark.accepted_answers),
                )
            )
        return blocked
    correct = is_correct(answer, task.landmark.accepted_answers)
    session.add(
        AnswerAttempt(
            run_task_id=task.id,
            device_id=device_id,
            submitted_at=now,
            answer_text=answer,
            correct=correct,
        )
    )                                                  # R-5: every attempt logged
    if not correct:
        task.wrong_attempts += 1
        bump(run)                                      # wrong_attempts may unlock Reveal on other phones
        return Outcome.WRONG
    _complete(run, task, "answered", now)
    return Outcome.CORRECT


def open_hint(run: GameRun, position: int, number: int, now: datetime) -> Outcome:
    task, blocked = _open_task(run, position)
    if blocked:
        return blocked
    landmark = task.landmark
    text = landmark.hint1 if number == 1 else landmark.hint2
    if not text or (number == 2 and task.hint1_at is None):
        return Outcome.NOT_AVAILABLE
    attr = "hint1_at" if number == 1 else "hint2_at"
    if getattr(task, attr) is None:                    # R-18: charged at most once
        setattr(task, attr, now)
        task.hint_penalty_minutes += HINT_PENALTIES[number]
        bump(run)
    return Outcome.OK


def open_compass(run: GameRun, now: datetime) -> Outcome:
    task, blocked = _open_task(run, run.current_position)
    if blocked:
        return blocked
    if task.landmark.coordinates_lat is None or task.landmark.coordinates_lon is None:
        return Outcome.NOT_AVAILABLE
    if task.compass_opened_at is None:  # R-18/R-26: charged at most once
        task.compass_opened_at = now
        task.hint_penalty_minutes += COMPASS_PENALTY_MINUTES
        bump(run)
    return Outcome.OK


def reveal_answer(
    run: GameRun, game: Game, position: int, now: datetime, *, instant: bool = False
) -> Outcome:
    task, blocked = _open_task(run, position)
    if blocked:
        return blocked
    if not reveal_unlocked(task, game, now, instant=instant):
        return Outcome.LOCKED
    task.revealed_at = now
    task.reveal_penalty_minutes = game.reveal_penalty_minutes   # frozen at charge time
    _complete(run, task, "revealed", now)
    return Outcome.OK


def advance(run: GameRun, position: int, now: datetime, *, service: bool = False) -> Outcome:
    """'Next riddle' / 'See results' (D1). Requires completion + at least one photo (R-1, R-10).

    Service runs (R-25) may advance without a photo: for the test team the photo is optional.
    """
    if run.end_reason in TIMED_OUT:
        return Outcome.GAME_OVER
    task = current_task(run)
    if run.current_position != position or task is None:
        return Outcome.STALE
    if task.completed_at is None or (task.photo_count == 0 and not service):
        return Outcome.LOCKED
    run.current_position += 1
    bump(run)
    following = current_task(run)
    if following is not None:
        following.shown_at = now
    return Outcome.OK
