from datetime import timedelta

import pytest

from questtour.models import AnswerAttempt, Assignment, RunDevice
from questtour.services import game as rules
from questtour.services.game import Outcome
from tests.factories import add_service_assignment, seed_game


@pytest.fixture
def session(session_factory):
    with session_factory() as s:
        yield s


@pytest.fixture
def assignment(session, clock, seed):
    return session.get(Assignment, seed.assignment_id)


@pytest.fixture
def run(session, assignment, clock):
    run = rules.start_run(session, assignment, clock.now)
    session.commit()
    return run


def add_photo(run, position=None):
    """Stands in for services.photos.save_photo: one more photo, one version bump (§5.4)."""
    run.tasks[run.current_position if position is None else position].photo_count += 1
    rules.bump(run)


def test_start_snapshots_tasks_and_sets_version_one(run, clock):
    assert run.version == 1
    assert run.current_position == 0
    assert [t.position for t in run.tasks] == [0, 1, 2]
    assert run.tasks[0].shown_at == clock.now
    assert run.tasks[1].shown_at is None
    assert rules.run_status(run) == "playing"
    assert rules.current_task(run) is run.tasks[0]


def test_version_increases_on_each_change(session, run, clock):
    versions = [run.version]
    assert (
        rules.submit_answer(session, run, 0, "nope", clock.now, "d1") == Outcome.WRONG
    )
    versions.append(run.version)
    assert (
        rules.submit_answer(session, run, 0, "Alexander Nevsky", clock.now, "d1")
        == Outcome.CORRECT
    )
    versions.append(run.version)
    add_photo(run)
    versions.append(run.version)
    assert rules.advance(run, 0, clock.now) == Outcome.OK
    versions.append(run.version)
    assert versions == [1, 2, 3, 4, 5]


def test_repeated_hint_keeps_version(run, clock):
    assert rules.open_hint(run, 0, 1, clock.now) == Outcome.OK
    version = run.version
    assert rules.open_hint(run, 0, 1, clock.now + timedelta(minutes=1)) == Outcome.OK
    assert run.version == version


def test_non_changes_do_not_bump(session, run, clock):
    version = run.version
    assert rules.open_hint(run, 0, 2, clock.now) == Outcome.NOT_AVAILABLE
    assert rules.reveal_answer(run, run.assignment.game, 0, clock.now) == Outcome.LOCKED
    assert rules.advance(run, 0, clock.now) == Outcome.LOCKED
    assert rules.submit_answer(session, run, 1, "x", clock.now, None) == Outcome.STALE
    rules.touch_device(session, run, "d1", clock.now)
    assert run.version == version


def test_answer_is_normalised_and_every_attempt_logged(session, run, clock):
    assert rules.submit_answer(session, run, 0, "wrong", clock.now, "d1") == Outcome.WRONG
    assert run.tasks[0].wrong_attempts == 1
    assert run.tasks[0].completed_at is None
    assert (
        rules.submit_answer(session, run, 0, "  alexander-NEVSKY ", clock.now, "d2")
        == Outcome.CORRECT
    )
    task = run.tasks[0]
    assert task.completion == "answered" and task.completed_at == clock.now
    session.flush()
    attempts = session.query(AnswerAttempt).order_by(AnswerAttempt.id).all()
    assert [(a.answer_text, a.correct, a.device_id) for a in attempts] == [
        ("wrong", False, "d1"),
        ("  alexander-NEVSKY ", True, "d2"),
    ]


def test_second_correct_answer_is_stale_but_logged(session, run, clock):
    rules.submit_answer(session, run, 0, "Alexander Nevsky", clock.now, "d1")
    version = run.version
    assert (
        rules.submit_answer(session, run, 0, "Alexander Nevsky", clock.now, "d2")
        == Outcome.STALE
    )
    assert run.version == version
    session.flush()
    assert session.query(AnswerAttempt).count() == 2


def test_out_of_range_position_is_stale_and_not_logged(session, run, clock):
    assert rules.submit_answer(session, run, 9, "x", clock.now, None) == Outcome.STALE
    assert rules.submit_answer(session, run, -1, "x", clock.now, None) == Outcome.STALE
    session.flush()
    assert session.query(AnswerAttempt).count() == 0


def test_hints_in_order_and_charged_once(run, clock):
    assert rules.open_hint(run, 0, 2, clock.now) == Outcome.NOT_AVAILABLE
    assert rules.open_hint(run, 0, 1, clock.now) == Outcome.OK
    assert rules.penalty_minutes(run) == 10
    assert rules.open_hint(run, 0, 1, clock.now) == Outcome.OK
    assert rules.penalty_minutes(run) == 10
    assert rules.open_hint(run, 0, 2, clock.now) == Outcome.OK
    assert rules.penalty_minutes(run) == 25
    assert rules.hints_used(run) == 2


def test_compass_charged_once_and_adds_five_minutes(run, clock):
    run.tasks[0].landmark.coordinates_lat = 42.7
    run.tasks[0].landmark.coordinates_lon = 23.3
    assert rules.open_compass(run, clock.now) == rules.Outcome.OK
    assert run.tasks[0].compass_opened_at == clock.now
    assert run.tasks[0].hint_penalty_minutes == 5
    assert rules.hints_used(run) == 1  # R-12: compasses count as hints used
    assert rules.open_compass(run, clock.now) == rules.Outcome.OK
    assert run.tasks[0].hint_penalty_minutes == 5  # once only
    assert rules.hints_used(run) == 1
    assert run.version == 2


def test_compass_not_available_without_coordinates(run, clock):
    assert rules.open_compass(run, clock.now) == rules.Outcome.NOT_AVAILABLE


def test_hint_without_text_is_not_available(session, run, clock):
    # Rotunda (position 1) has hint1 only; Serdika (position 2) has none.
    rules.submit_answer(session, run, 0, "Alexander Nevsky", clock.now, None)
    add_photo(run)
    rules.advance(run, 0, clock.now)
    assert rules.open_hint(run, 1, 1, clock.now) == Outcome.OK
    assert rules.open_hint(run, 1, 2, clock.now) == Outcome.NOT_AVAILABLE
    rules.submit_answer(session, run, 1, "Rotunda of St George", clock.now, None)
    add_photo(run)
    rules.advance(run, 1, clock.now)
    assert rules.open_hint(run, 2, 1, clock.now) == Outcome.NOT_AVAILABLE


def test_hint_on_stale_position(run, clock):
    assert rules.open_hint(run, 1, 1, clock.now) == Outcome.STALE


def test_reveal_locked_until_n_wrong_attempts(session, run, clock):
    game = run.assignment.game
    for _ in range(game.reveal_after_attempts - 1):
        rules.submit_answer(session, run, 0, "nope", clock.now, None)
    assert rules.reveal_unlocked(run.tasks[0], game, clock.now) is False
    assert rules.reveal_answer(run, game, 0, clock.now) == Outcome.LOCKED
    rules.submit_answer(session, run, 0, "nope", clock.now, None)
    assert rules.reveal_unlocked(run.tasks[0], game, clock.now) is True
    assert rules.reveal_answer(run, game, 0, clock.now) == Outcome.OK
    task = run.tasks[0]
    assert task.completion == "revealed"
    assert task.revealed_at == clock.now
    assert task.reveal_penalty_minutes == game.reveal_penalty_minutes == 30
    assert rules.penalty_minutes(run) == 30


def test_reveal_unlocks_after_x_minutes(run, clock):
    game = run.assignment.game
    almost = clock.now + timedelta(minutes=game.reveal_after_minutes) - timedelta(seconds=1)
    assert rules.reveal_unlocked(run.tasks[0], game, almost) is False
    at = clock.now + timedelta(minutes=game.reveal_after_minutes)
    assert rules.reveal_answer(run, game, 0, at) == Outcome.OK


def test_advance_requires_completion_and_photo(session, run, clock):
    assert rules.advance(run, 0, clock.now) == Outcome.LOCKED       # not completed
    rules.submit_answer(session, run, 0, "Alexander Nevsky", clock.now, None)
    assert rules.advance(run, 0, clock.now) == Outcome.LOCKED       # no photo yet (R-10)
    add_photo(run)
    later = clock.now + timedelta(minutes=5)
    assert rules.advance(run, 0, later) == Outcome.OK
    assert run.current_position == 1
    assert run.tasks[1].shown_at == later
    assert rules.advance(run, 0, later) == Outcome.STALE            # double press by a teammate


def test_service_advance_needs_no_photo(session, run, clock):
    """R-25: the service (test) team may advance without a photo; regular teams cannot (R-1, R-10)."""
    rules.submit_answer(session, run, 0, "Alexander Nevsky", clock.now, None)
    assert rules.advance(run, 0, clock.now) == Outcome.LOCKED
    assert rules.advance(run, 0, clock.now, service=True) == Outcome.OK
    assert run.current_position == 1


def test_advance_wrong_position_is_stale(run, clock):
    assert rules.advance(run, 2, clock.now) == Outcome.STALE


def test_finish_at_last_task(session, run, clock):
    answers = ["Alexander Nevsky", "Rotunda of St George", "Serdika"]
    for position, answer in enumerate(answers):
        clock.advance(minutes=10)
        rules.submit_answer(session, run, position, answer, clock.now, None)
        if position < 2:
            assert run.end_reason is None
            add_photo(run)
            rules.advance(run, position, clock.now)
    assert run.finished_at == run.ended_at == clock.now
    assert run.end_reason == "finished"
    assert rules.run_status(run) == "finished"
    assert rules.total_seconds(run) == 30 * 60
    add_photo(run)
    assert rules.advance(run, 2, clock.now) == Outcome.OK
    assert rules.current_task(run) is None


def test_total_seconds_includes_penalties(session, run, clock):
    rules.open_hint(run, 0, 1, clock.now)
    for position, answer in enumerate(["Alexander Nevsky", "Rotunda of St George", "Serdika"]):
        clock.advance(minutes=10)
        rules.submit_answer(session, run, position, answer, clock.now, None)
        add_photo(run)
        rules.advance(run, position, clock.now)
    assert rules.total_seconds(run) == 30 * 60 + 10 * 60


def test_time_limits_use_the_earlier_deadline(session, clock):
    seed = seed_game(
        session, clock.now, valid_until=clock.now + timedelta(hours=1), max_duration_minutes=240
    )
    assignment = session.get(Assignment, seed.assignment_id)
    run = rules.start_run(session, assignment, clock.now)
    assert rules.effective_deadline(run, assignment) == (60 * 60, "window_closed")

    assignment.valid_until = clock.now + timedelta(hours=10)
    assert rules.effective_deadline(run, assignment) == (4 * 60 * 60, "max_duration")


def test_apply_time_limits_ends_run_at_the_deadline(run, assignment, clock):
    version = run.version
    rules.apply_time_limits(run, assignment, clock.now + timedelta(hours=4, minutes=-1))
    assert run.end_reason is None and run.version == version

    rules.apply_time_limits(run, assignment, clock.now + timedelta(hours=5))
    assert run.end_reason == "max_duration"
    assert run.ended_at == clock.now + timedelta(hours=4)       # the deadline, not "now"
    assert run.finished_at is None
    assert run.version == version + 1
    assert rules.run_status(run) == "timed_out"
    assert rules.elapsed_seconds(run, clock.now + timedelta(days=1)) == 4 * 3600

    rules.apply_time_limits(run, assignment, clock.now + timedelta(hours=6))
    assert run.version == version + 1                            # idempotent


def test_window_closed_reason(run, assignment, clock):
    assignment.valid_until = clock.now + timedelta(hours=1)
    rules.apply_time_limits(run, assignment, clock.now + timedelta(hours=2))
    assert run.end_reason == "window_closed"
    assert run.ended_at == clock.now + timedelta(hours=1)


def test_actions_after_timeout_are_game_over(session, run, assignment, clock):
    rules.apply_time_limits(run, assignment, clock.now + timedelta(hours=5))
    now = clock.now + timedelta(hours=5)
    game = assignment.game
    assert rules.submit_answer(session, run, 0, "x", now, None) == Outcome.GAME_OVER
    assert rules.open_hint(run, 0, 1, now) == Outcome.GAME_OVER
    assert rules.reveal_answer(run, game, 0, now) == Outcome.GAME_OVER
    assert rules.advance(run, 0, now) == Outcome.GAME_OVER


def test_compass_game_over_after_timeout(run, clock, assignment):
    run.tasks[0].landmark.coordinates_lat = 42.7
    run.tasks[0].landmark.coordinates_lon = 23.3
    clock.advance(minutes=assignment.game.max_duration_minutes + 1)
    rules.apply_time_limits(run, assignment, clock.now)
    assert rules.open_compass(run, clock.now) == rules.Outcome.GAME_OVER


def test_elapsed_seconds_while_playing(run, clock):
    assert rules.elapsed_seconds(run, clock.now + timedelta(seconds=90)) == 90
    assert rules.elapsed_seconds(run, clock.now - timedelta(seconds=5)) == 0


def test_active_seconds_sums_intervals_and_skips_pauses(session, run, clock):
    clock.advance(minutes=5)
    rules.submit_answer(session, run, 0, "Alexander Nevsky", clock.now, None)
    clock.advance(minutes=3)                       # photo screen: inside the grace, the clock is stopped
    run.tasks[0].photo_count += 1
    rules.advance(run, 0, clock.now)
    clock.advance(minutes=2)
    assert rules.active_seconds(run, clock.now) == 7 * 60
    assert rules.elapsed_seconds(run, clock.now) == 7 * 60


def test_pause_over_the_grace_counts_as_solving_time(session, run, clock):
    clock.advance(minutes=5)
    rules.submit_answer(session, run, 0, "Alexander Nevsky", clock.now, None)
    clock.advance(minutes=8)                       # 5 min grace + 3 min overage
    run.tasks[0].photo_count += 1
    rules.advance(run, 0, clock.now)
    clock.advance(minutes=2)
    assert rules.active_seconds(run, clock.now) == (5 + 3 + 2) * 60


def test_each_pause_gets_its_own_grace(session, run, clock):
    # task 1 pauses 7 min (2 min overage); task 2 pauses 3 min (free); task 3 solved in 5
    for position, answer in enumerate(["Alexander Nevsky", "Rotunda of St George", "Serdika"]):
        clock.advance(minutes=5)
        rules.submit_answer(session, run, position, answer, clock.now, None)
        clock.advance(minutes=7 if position == 0 else 3)
        run.tasks[position].photo_count += 1
        rules.advance(run, position, clock.now)
    assert rules.active_seconds(run, clock.now) == (5 + 2 + 5 + 5) * 60


def test_pause_of_exactly_five_minutes_is_free(session, run, clock):
    clock.advance(minutes=5)
    rules.submit_answer(session, run, 0, "Alexander Nevsky", clock.now, None)
    clock.advance(minutes=5)                       # exactly the grace: nothing spent
    run.tasks[0].photo_count += 1
    rules.advance(run, 0, clock.now)
    clock.advance(minutes=1)
    assert rules.active_seconds(run, clock.now) == 6 * 60


def test_active_seconds_caps_at_ended_at_for_a_timed_out_run(run, assignment, clock):
    clock.advance(minutes=241)
    rules.apply_time_limits(run, assignment, clock.now)
    assert run.ended_at == clock.now - timedelta(minutes=1)
    assert rules.active_seconds(run, clock.now) == 240 * 60


def test_total_seconds_counts_active_time_only(session, run, clock):
    for position, answer in enumerate(["Alexander Nevsky", "Rotunda of St George", "Serdika"]):
        clock.advance(minutes=10)
        rules.submit_answer(session, run, position, answer, clock.now, None)
        clock.advance(minutes=5)                   # savouring the story: free
        run.tasks[position].photo_count += 1
        rules.advance(run, position, clock.now)
    assert rules.total_seconds(run) == 30 * 60


def test_max_duration_ends_during_the_pause_past_the_grace(session, run, assignment, clock):
    clock.advance(minutes=239)
    rules.submit_answer(session, run, 0, "Alexander Nevsky", clock.now, None)
    clock.advance(minutes=4)                       # inside the grace: nothing is spent yet
    rules.apply_time_limits(run, assignment, clock.now)
    assert run.end_reason is None
    clock.advance(minutes=2)                       # 6 min into the pause: the budget runs out
    rules.apply_time_limits(run, assignment, clock.now)
    assert run.end_reason == "max_duration"
    assert run.ended_at == run.tasks[0].completed_at + timedelta(minutes=6)


def test_window_budget_ends_during_the_pause_past_the_grace(session, run, assignment, clock):
    assignment.valid_until = clock.now + timedelta(hours=1)
    clock.advance(minutes=59)
    rules.submit_answer(session, run, 0, "Alexander Nevsky", clock.now, None)
    clock.advance(minutes=6)                       # 5 min grace + 1 min left on the window
    rules.apply_time_limits(run, assignment, clock.now)
    assert run.end_reason == "window_closed"
    assert run.ended_at == run.tasks[0].completed_at + timedelta(minutes=6)


def test_pause_within_the_grace_does_not_time_the_run_out(session, run, assignment, clock):
    clock.advance(minutes=239)
    rules.submit_answer(session, run, 0, "Alexander Nevsky", clock.now, None)
    clock.advance(minutes=5)                       # exactly the grace, not a second more
    rules.apply_time_limits(run, assignment, clock.now)
    assert run.end_reason is None


def test_touch_device_records_first_and_last_seen(session, run, clock):
    rules.touch_device(session, run, None, clock.now)
    rules.touch_device(session, run, "d1", clock.now)
    later = clock.now + timedelta(minutes=3)
    rules.touch_device(session, run, "d1", later)
    session.flush()
    devices = session.query(RunDevice).all()
    assert len(devices) == 1
    assert devices[0].first_seen_at == clock.now and devices[0].last_seen_at == later


def test_load_run_returns_run_for_assignment(session, run, seed):
    assert rules.load_run(session, seed.assignment_id) is run
    assert rules.load_run(session, 999) is None


def test_constants():
    assert rules.HINT_PENALTIES == {1: 10, 2: 15}
    assert rules.COMPASS_PENALTY_MINUTES == 5
    assert rules.PHOTO_GRACE_SECONDS == 300
    assert rules.WARNING_SECONDS == 900
    assert rules.TIMED_OUT == frozenset({"max_duration", "window_closed"})


def _service_assignment(session, clock):
    seed = seed_game(session, clock.now)
    token = add_service_assignment(session, seed, clock.now)
    from questtour.services.access import find_assignment

    return find_assignment(session, token)


def test_service_run_never_hits_time_limits(session_factory, clock):
    with session_factory() as session:
        assignment = _service_assignment(session, clock)
        run = rules.start_run(session, assignment, clock.now)
        clock.advance(days=10)
        rules.apply_time_limits(run, assignment, clock.now)
        assert run.end_reason is None and run.ended_at is None


def test_service_reveal_is_instant(session_factory, clock):
    with session_factory() as session:
        assignment = _service_assignment(session, clock)
        run = rules.start_run(session, assignment, clock.now)
        task, game = run.tasks[0], assignment.game
        assert rules.reveal_unlocked(task, game, clock.now) is False
        assert rules.reveal_unlocked(task, game, clock.now, instant=True) is True
        assert rules.reveal_answer(run, game, 0, clock.now, instant=True) == rules.Outcome.OK
        assert run.tasks[0].completion == "revealed"


def test_start_run_starts_above_version_floor(session_factory, clock):
    with session_factory() as session:
        seed = seed_game(session, clock.now)
        assignment = session.get(Assignment, seed.assignment_id)
        assert rules.start_run(session, assignment, clock.now).version == 1
        other = session.query(Assignment).filter(Assignment.id != assignment.id).one()
        other.version_floor = 9
        assert rules.start_run(session, other, clock.now).version == 10
