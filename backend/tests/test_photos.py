import pytest

from questtour.clock import utc_now
from questtour.imagetypes import JPEG, PNG
from questtour.models import Assignment, Photo
from questtour.services import game as rules
from questtour.services.game import Outcome, bump
from questtour.services.photos import save_photo

DATA = b"\xff\xd8\xff\xe0" + b"\x00" * 64


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


def answer_current(session, run, clock):
    position = run.current_position
    answers = ["Alexander Nevsky", "Rotunda of St George", "Serdika"]
    assert (
        rules.submit_answer(session, run, position, answers[position], clock.now, "d1")
        == Outcome.CORRECT
    )


def upload(session, blob_store, run, assignment, clock, position, kind=JPEG):
    return save_photo(
        session, blob_store, "photos", run, assignment, position, DATA, kind, clock.now, "d1"
    )


def test_upload_to_current_task(session, blob_store, assignment, run, clock):
    answer_current(session, run, clock)
    version = run.version
    assert upload(session, blob_store, run, assignment, clock, 0) == Outcome.OK
    assert blob_store.exists(
        "photos",
        "Sofia-Old-Town-Quest/The-Explorers/2026-10-14_11-00-00_01_Alexander-Nevsky-Cathedral.jpg",
    )
    assert run.tasks[0].photo_count == 1
    assert run.version == version + 1
    photo = session.query(Photo).one()
    assert (photo.content_type, photo.size_bytes, photo.device_id) == ("image/jpeg", len(DATA), "d1")


def test_name_collision_gets_numeric_suffix(session, blob_store, assignment, run, clock):
    answer_current(session, run, clock)
    upload(session, blob_store, run, assignment, clock, 0)
    upload(session, blob_store, run, assignment, clock, 0, kind=PNG)
    upload(session, blob_store, run, assignment, clock, 0)
    base = "Sofia-Old-Town-Quest/The-Explorers/2026-10-14_11-00-00_01_Alexander-Nevsky-Cathedral"
    assert blob_store.exists("photos", f"{base}.jpg")
    assert blob_store.exists("photos", f"{base}.png")
    assert blob_store.exists("photos", f"{base}_2.jpg")
    assert run.tasks[0].photo_count == 3


def test_late_photo_for_previous_task_is_kept(session, blob_store, assignment, run, clock):
    answer_current(session, run, clock)
    upload(session, blob_store, run, assignment, clock, 0)
    assert rules.advance(run, 0, clock.now) == Outcome.OK
    assert upload(session, blob_store, run, assignment, clock, 0) == Outcome.OK
    assert run.current_position == 1
    assert blob_store.exists(
        "photos",
        "Sofia-Old-Town-Quest/The-Explorers/2026-10-14_11-00-00_01_Alexander-Nevsky-Cathedral_2.jpg",
    )
    assert run.tasks[0].photo_count == 2


def test_photo_for_unreached_task_is_stale(session, blob_store, assignment, run, clock):
    answer_current(session, run, clock)
    upload(session, blob_store, run, assignment, clock, 0)
    rules.advance(run, 0, clock.now)
    version = run.version
    assert upload(session, blob_store, run, assignment, clock, 2) == Outcome.STALE
    assert upload(session, blob_store, run, assignment, clock, -1) == Outcome.STALE
    assert upload(session, blob_store, run, assignment, clock, 99) == Outcome.STALE
    assert run.version == version
    assert session.query(Photo).count() == 1


def test_photo_before_task_is_completed_is_stale(session, blob_store, assignment, run, clock):
    assert upload(session, blob_store, run, assignment, clock, 0) == Outcome.STALE
    assert run.tasks[0].photo_count == 0


def test_photo_after_timeout_is_game_over(session, blob_store, assignment, run, clock):
    clock.advance(minutes=241)                     # active time, so the run does time out
    rules.apply_time_limits(run, assignment, clock.now)
    assert run.end_reason == "max_duration"
    assert upload(session, blob_store, run, assignment, clock, 0) == Outcome.GAME_OVER
    assert session.query(Photo).count() == 0


def test_photo_within_the_grace_does_not_time_the_run_out(session, blob_store, assignment, run, clock):
    answer_current(session, run, clock)
    clock.advance(minutes=4)                       # parked on the photo screen: inside the 5-min grace
    rules.apply_time_limits(run, assignment, clock.now)
    assert run.end_reason is None
    assert upload(session, blob_store, run, assignment, clock, 0) == Outcome.OK
    assert session.query(Photo).count() == 1


def test_photo_past_the_grace_finds_the_run_timed_out(session, blob_store, assignment, run, clock):
    clock.advance(minutes=239)                     # nearly all of the 4-hour budget is spent
    answer_current(session, run, clock)
    clock.advance(minutes=30)                      # 25 min past the grace: the pause spends the rest
    rules.apply_time_limits(run, assignment, clock.now)
    assert run.end_reason == "max_duration"
    assert upload(session, blob_store, run, assignment, clock, 0) == Outcome.GAME_OVER
    assert session.query(Photo).count() == 0


def test_filename_uses_game_time_zone(session, blob_store, assignment, run, clock):
    answer_current(session, run, clock)
    clock.advance(minutes=30, seconds=5)
    upload(session, blob_store, run, assignment, clock, 0)
    assert blob_store.exists(
        "photos",
        "Sofia-Old-Town-Quest/The-Explorers/2026-10-14_11-30-05_01_Alexander-Nevsky-Cathedral.jpg",
    )


def test_soft_deleted_photo_decrements_count_and_allows_replacement(
    session, blob_store, assignment, run, clock
):
    answer_current(session, run, clock)
    upload(session, blob_store, run, assignment, clock, 0)
    photo = session.query(Photo).one()
    assert run.tasks[0].photo_count == 1

    photo.deleted_at = utc_now()
    run.tasks[0].photo_count -= 1
    bump(run)
    session.commit()

    assert run.tasks[0].photo_count == 0

    replacement = DATA + b"_replacement"
    assert (
        save_photo(
            session, blob_store, "photos", run, assignment, 0, replacement, JPEG, clock.now, "d1"
        )
        == Outcome.OK
    )
    assert run.tasks[0].photo_count == 1
