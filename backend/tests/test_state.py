from datetime import timedelta

import pytest
from pydantic import ValidationError

from questtour.api.schemas import ActionResult, AnswerIn, GameState, HintIn, PositionIn
from questtour.models import Assignment
from questtour.services import game as rules
from questtour.services.game import Outcome
from questtour.services.state import (
    build_clock,
    build_game,
    build_state,
    build_task,
    image_url,
    run_phase,
)


def test_compass_in_state_when_landmark_has_coordinates(session, assignment, run, clock):
    run.tasks[0].landmark.coordinates_lat = 42.7
    run.tasks[0].landmark.coordinates_lon = 23.3
    task = build_task(run.tasks[0], assignment.game, clock.now)
    assert task.compass.opened is False
    assert task.compass.lat == 42.7
    assert task.compass.lon == 23.3
    assert task.compass.penalty_minutes == 5
    rules.open_compass(run, clock.now)
    task = build_task(run.tasks[0], assignment.game, clock.now)
    assert task.compass.opened is True


def test_task_without_coordinates_has_no_compass(session, assignment, run, clock):
    task = build_task(run.tasks[0], assignment.game, clock.now)
    assert task.compass is None



@pytest.fixture
def session(session_factory):
    with session_factory() as s:
        yield s


@pytest.fixture
def assignment(session, seed):
    return session.get(Assignment, seed.assignment_id)


@pytest.fixture
def run(session, assignment, clock):
    run = rules.start_run(session, assignment, clock.now)
    session.commit()
    return run


def add_photo(run):
    run.tasks[run.current_position].photo_count += 1
    rules.bump(run)


def test_image_url():
    assert image_url("abc.svg") == "/api/images/abc.svg"
    assert image_url(None) is None


def test_not_started_state_has_no_run_parts(session, assignment, clock):
    state = build_state(session, assignment, None, clock.now)
    assert state.status == "not_started"
    assert state.version == 0
    assert state.phase is None
    assert (state.clock, state.task, state.results) == (None, None, None)
    assert state.team.name == "The Explorers"
    assert state.game.task_count == 3
    assert state.game.hint_penalties == [10, 15]


def test_phase_walks_task_photo_info_results(session, assignment, run, clock):
    assert run_phase(run, assignment, clock.now) == "task"
    rules.submit_answer(session, run, 0, "Nevsky", clock.now, None)
    assert run_phase(run, assignment, clock.now) == "task"  # wrong answer
    rules.submit_answer(session, run, 0, "Alexander Nevsky", clock.now, None)
    assert run_phase(run, assignment, clock.now) == "photo"
    add_photo(run)
    assert run_phase(run, assignment, clock.now) == "info"
    rules.advance(run, 0, clock.now)
    assert run_phase(run, assignment, clock.now) == "task"


def test_finished_run_is_results_and_leaderboard_only_then(session, assignment, run, clock):
    playing = build_state(session, assignment, run, clock.now)
    assert playing.results is None
    for position, answer in enumerate(["Alexander Nevsky", "St George Rotunda", "Serdika"]):
        clock.advance(minutes=10)
        rules.submit_answer(session, run, position, answer, clock.now, None)
        add_photo(run)
        rules.advance(run, position, clock.now)
    state = build_state(session, assignment, run, clock.now)
    assert (state.status, state.phase, state.task) == ("finished", "results", None)
    assert state.results.end_reason == "finished"
    assert state.results.total_seconds == 30 * 60
    assert state.results.rank == 1
    assert state.results.tasks_completed == 3
    assert [r.is_you for r in state.results.leaderboard] == [True]
    assert state.clock.running is False


def test_finished_team_before_advancing_still_sees_last_task_flow(session, assignment, run, clock):
    run.current_position = 2
    rules.submit_answer(session, run, 2, "Serdika", clock.now, None)
    assert run.end_reason == "finished"
    assert run_phase(run, assignment, clock.now) == "photo"
    assignment.valid_until = clock.now
    assert run_phase(run, assignment, clock.now) == "results"


def test_timed_out_run_goes_to_results_with_deadline_as_end(session, assignment, run, clock):
    clock.advance(minutes=241)
    state = build_state(session, assignment, run, clock.now)
    assert (state.status, state.phase) == ("timed_out", "results")
    assert state.results.end_reason == "max_duration"
    assert state.results.total_seconds is None
    assert state.results.rank is None
    assert state.clock.elapsed_seconds == 240 * 60
    assert state.clock.running is False
    assert state.clock.remaining_seconds is None


def test_clock_remaining_is_rounded_up_and_warning_threshold(session, assignment, run, clock):
    clock.advance(seconds=1)
    assert build_clock(run, assignment, clock.now).remaining_seconds == 240 * 60 - 1
    clock.now = run.started_at + timedelta(minutes=240) - timedelta(milliseconds=500)
    out = build_clock(run, assignment, clock.now)
    assert out.remaining_seconds == 1
    assert out.warning is True
    clock.now = run.started_at + timedelta(minutes=240 - 16)
    assert build_clock(run, assignment, clock.now).warning is False
    clock.now = run.started_at + timedelta(minutes=240 - 15)
    assert build_clock(run, assignment, clock.now).warning is True


def test_clock_uses_window_close_when_earlier(session, assignment, run, clock):
    assignment.valid_until = clock.now + timedelta(minutes=30)
    assert build_clock(run, assignment, clock.now).remaining_seconds == 30 * 60


def test_clock_freezes_while_the_task_is_completed(session, assignment, run, clock):
    clock.advance(minutes=5)
    rules.submit_answer(session, run, 0, "Alexander Nevsky", clock.now, None)
    clock.advance(minutes=3)                       # photo/landmark screens: within the grace
    out = build_clock(run, assignment, clock.now)
    assert (out.running, out.elapsed_seconds, out.remaining_seconds) == (
        False, 5 * 60, (240 - 5) * 60,
    )
    clock.advance(minutes=4)                       # the grace is spent: the overage counts
    out = build_clock(run, assignment, clock.now)
    assert (out.running, out.elapsed_seconds, out.remaining_seconds) == (
        False, 7 * 60, (240 - 7) * 60,
    )
    run.tasks[0].photo_count += 1
    rules.advance(run, 0, clock.now)               # the next riddle restarts the clock
    clock.advance(minutes=1)
    out = build_clock(run, assignment, clock.now)
    assert (out.running, out.elapsed_seconds, out.remaining_seconds) == (
        True, 8 * 60, (240 - 8) * 60,
    )


def test_task_never_leaks_unopened_hint_text_or_landmark(session, assignment, run, clock):
    task = build_task(run.tasks[0], assignment.game, clock.now)
    assert task.number == 1
    assert task.landmark is None
    assert task.picture_url == "/api/images/" + "a" * 64 + ".svg"
    assert [(h.number, h.available, h.opened, h.text) for h in task.hints] == [
        (1, True, False, None),
        (2, False, False, None),
    ]
    assert "golden domes" not in task.model_dump_json()


def test_hint_availability_follows_opening_order(session, assignment, run, clock):
    rules.open_hint(run, 0, 1, clock.now)
    task = build_task(run.tasks[0], assignment.game, clock.now)
    assert [(h.available, h.opened) for h in task.hints] == [(False, True), (True, False)]
    assert task.hints[0].text.startswith("Look for the largest golden domes")
    assert task.hints[0].penalty_minutes == 10
    assert task.hints[1].penalty_minutes == 15


def test_task_without_hint_text_has_no_hint_entries(session, assignment, run, clock):
    for later in run.tasks[1:]:
        later.shown_at = clock.now  # build_task is only ever called on a shown (current) task
    assert build_task(run.tasks[2], assignment.game, clock.now).hints == []
    second = build_task(run.tasks[1], assignment.game, clock.now)
    assert [h.number for h in second.hints] == [1]


def test_reveal_countdown_and_unlock(session, assignment, run, clock):
    game = assignment.game
    task = build_task(run.tasks[0], game, clock.now)
    assert (task.reveal_unlocked, task.reveal_unlocks_in_seconds) == (False, 20 * 60)
    clock.advance(minutes=19, seconds=59, milliseconds=500)
    assert build_task(run.tasks[0], game, clock.now).reveal_unlocks_in_seconds == 1
    clock.advance(seconds=1)
    unlocked = build_task(run.tasks[0], game, clock.now)
    assert (unlocked.reveal_unlocked, unlocked.reveal_unlocks_in_seconds) == (True, None)


def test_reveal_unlocks_after_wrong_attempts(session, assignment, run, clock):
    for _ in range(5):
        rules.submit_answer(session, run, 0, "nope", clock.now, None)
    task = build_task(run.tasks[0], assignment.game, clock.now)
    assert (task.wrong_attempts, task.reveal_unlocked) == (5, True)


def test_revealed_task_exposes_answer_landmark_and_frozen_penalty(session, assignment, run, clock):
    clock.advance(minutes=21)
    rules.reveal_answer(run, assignment.game, 0, clock.now)
    state = build_state(session, assignment, run, clock.now)
    task = state.task
    assert state.phase == "photo"
    assert task.completion == "revealed"
    assert task.revealed_answer == "Alexander Nevsky Cathedral"
    assert task.reveal_penalty_minutes == 30
    assert task.reveal_unlocked is False
    assert task.reveal_unlocks_in_seconds is None
    assert task.landmark.name == "Alexander Nevsky Cathedral"
    assert task.landmark.picture_url is None
    assert state.clock.penalty_minutes == 30
    assert all(not h.available for h in task.hints)


def test_answered_task_does_not_reveal_answer(session, assignment, run, clock):
    rules.submit_answer(session, run, 0, "Alexander Nevsky", clock.now, None)
    task = build_task(run.tasks[0], assignment.game, clock.now)
    assert (task.completion, task.revealed_answer) == ("answered", None)
    assert task.landmark is not None


def test_game_out_carries_rules_for_the_client(session, assignment, run, clock):
    state = build_state(session, assignment, run, clock.now)
    assert state.game == build_game(assignment.game, run.tasks)
    assert (state.game.reveal_after_attempts, state.game.reveal_after_minutes) == (5, 20)
    assert state.game.reveal_penalty_minutes == 30


def test_build_state_applies_time_limits_and_bumps_version(session, assignment, run, clock):
    before = run.version
    clock.advance(minutes=241)
    state = build_state(session, assignment, run, clock.now)
    assert run.end_reason == "max_duration"
    assert state.version == before + 1


def test_action_result_serialises_outcome(session, assignment, clock):
    state = build_state(session, assignment, None, clock.now)
    payload = ActionResult(outcome=Outcome.OK, state=state).model_dump(mode="json")
    assert payload["outcome"] == "ok"
    assert GameState.model_validate(payload["state"]) == state


def test_request_models_validate():
    assert AnswerIn(position=0, answer="x").answer == "x"
    assert HintIn(position=1, hint=2).hint == 2
    assert PositionIn(position=3).position == 3
    with pytest.raises(ValidationError):
        AnswerIn(position=0, answer="")
    with pytest.raises(ValidationError):
        AnswerIn(position=-1, answer="x")
    with pytest.raises(ValidationError):
        HintIn(position=0, hint=3)
