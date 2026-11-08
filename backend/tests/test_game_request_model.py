from datetime import UTC, date, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from questtour.admin.crud import handle_integrity
from questtour.models import Game, GameRequest


def _game() -> Game:
    return Game(
        host_id="default", key="g", name="G", intro="i", time_zone="UTC",
        max_duration_minutes=60, reveal_after_attempts=5, reveal_after_minutes=20,
        reveal_penalty_minutes=30,
    )


def _request(challenge: str, game_id: int | None = None) -> GameRequest:
    now = datetime(2026, 10, 14, 8, 0, tzinfo=UTC)
    return GameRequest(
        host_id="default",
        game_id=game_id,
        play_date=date(2026, 10, 20),
        teams=[{"name": "Foxes", "key": "foxes", "participants": 4, "valid_from": None,
                "valid_until": None, "team_id": None}],
        contact_name="Ann",
        terms_accepted_at=now,
        terms_version="11 October 2026",
        challenge=challenge,
        created_at=now,
    )


def test_game_is_not_requestable_by_default(session_factory):
    with session_factory() as s:
        game = _game()
        s.add(game)
        s.commit()
        assert game.requestable is False


def test_game_request_defaults_and_round_trip(session_factory):
    with session_factory() as s:
        game = _game()
        s.add(game)
        s.flush()
        s.add(_request("c1", game.id))
        s.commit()
    with session_factory() as s:
        row = s.query(GameRequest).one()
        assert row.status == "pending"
        assert row.contact_email is None and row.contact_phone is None
        assert row.message is None and row.exit_message is None
        assert row.decided_at is None and row.decided_by is None
        assert row.created_at == datetime(2026, 10, 14, 8, 0, tzinfo=UTC)
        assert row.teams[0]["key"] == "foxes"
        assert row.play_date == date(2026, 10, 20)


def test_duplicate_challenge_is_a_unique_violation(session_factory):
    with session_factory() as s:
        s.add(_request("same"))
        s.commit()
    with session_factory() as s:
        s.add(_request("same"))
        with pytest.raises(IntegrityError) as exc:
            s.commit()
        s.rollback()
    # SQLite names the column, not the constraint, so the caller's field_map handles it there.
    error = handle_integrity(exc.value, {"challenge": "altcha"})
    assert [e.field for e in error.errors] == ["altcha"]


def test_postgres_challenge_constraint_maps_to_altcha():
    orig = Exception(
        'duplicate key value violates unique constraint "uq_game_requests_challenge"\n'
        "DETAIL:  Key (challenge)=(abc) already exists."
    )
    error = handle_integrity(IntegrityError("INSERT", {}, orig), {})
    assert [e.field for e in error.errors] == ["altcha"]
