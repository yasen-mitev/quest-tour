"""Public game-play request API (issue #61): GET /api/public/games, the challenge, POST /requests.

POST runs its checks in a fixed order (plan "Public API"); each step has a test that also asserts
nothing was stored (I2) and, for refusals, that the log carries the reason code and no personal
data (I6)."""

import json
import logging
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from questtour.models import Game, GameRequest, Team
from questtour.requests import service
from questtour.requests.challenge import CHALLENGE_TTL_SECONDS
from tests.test_request_challenge import solve

MAX_NUMBER = 50
ORIGIN = "https://quest-tour.example"
EMAIL = "maria.ivanova@example.com"
CONTACT = "Maria Ivanova"
TEAM_NAME = "Red Foxes"
ALTCHA_FIELDS = ("algorithm", "challenge", "maxnumber", "salt", "signature")


@pytest.fixture
def settings(settings):
    return settings.model_copy(update={"request_challenge_max_number": MAX_NUMBER})


@pytest.fixture
def make_client(settings, session_factory, blob_store, clock):
    from questtour.main import create_app

    clients = []

    def make(**overrides) -> TestClient:
        app = create_app(
            settings.model_copy(update=overrides),
            session_factory=session_factory,
            blob_store=blob_store,
            clock=clock,
        )
        client = TestClient(app)
        client.__enter__()
        clients.append(client)
        return client

    yield make
    for client in clients:
        client.__exit__(None, None, None)


def _game(key: str, name: str, *, requestable: bool, host_id: str = "default", tz: str = "UTC"):
    return Game(
        host_id=host_id,
        key=key,
        name=name,
        intro=f"Intro of {name}",
        time_zone=tz,
        max_duration_minutes=120,
        reveal_after_attempts=5,
        reveal_after_minutes=20,
        reveal_penalty_minutes=30,
        requestable=requestable,
    )


@pytest.fixture(autouse=True)
def games(session_factory):
    with session_factory() as session:
        session.add_all(
            [
                _game("sofia-old-town", "Sofia Old Town Quest", requestable=True, tz="Europe/Sofia"),
                _game("plovdiv", "Plovdiv Hills", requestable=True),
                _game("secret", "Secret Test Game", requestable=False),
                _game("elsewhere", "Another Host Game", requestable=True, host_id="other"),
                Team(host_id="default", key="explorers", name="The Explorers"),
                Team(host_id="other", key="owls", name="Night Owls"),
            ]
        )
        session.commit()


@pytest.fixture
def logs(caplog):
    caplog.set_level(logging.INFO, logger="questtour.requests")
    return caplog


def _count(session_factory) -> int:
    with session_factory() as session:
        return session.scalar(select(func.count(GameRequest.id)))


def _solved(client) -> dict:
    issued = client.get("/api/public/requests/challenge").json()
    return {**{k: issued[k] for k in ALTCHA_FIELDS}, "number": solve(issued)}


def _body(altcha: dict, **overrides) -> dict:
    body = {
        "game_key": "sofia-old-town",
        "play_date": "2026-10-20",
        "teams": [{"name": TEAM_NAME, "key": "red-foxes", "participants": 4}],
        "contact_name": CONTACT,
        "contact_email": EMAIL,
        "contact_phone": "",
        "message": "",
        "terms_accepted": True,
        "terms_version": "11 October 2026",
        "website": "",
        "altcha": altcha,
    }
    body.update(overrides)
    return body


def _submit(client, clock, *, wait: int = 3, **overrides):
    """Fetch and solve a challenge, wait out the min fill time, then post."""
    altcha = _solved(client)
    clock.advance(seconds=wait)
    return client.post("/api/public/requests", json=_body(altcha, **overrides))


def _reasons(logs) -> list[str]:
    return [r.getMessage() for r in logs.records if r.name == "questtour.requests"]


def _assert_logged(logs, code: str) -> None:
    assert any(code in message for message in _reasons(logs)), _reasons(logs)
    for personal in (EMAIL, CONTACT, TEAM_NAME, "red-foxes", "+359"):
        assert personal not in logs.text


def _stored(session_factory, *, status: str = "pending", created_at: datetime, **fields) -> int:
    """Insert a request row directly, bypassing the API."""
    row = GameRequest(
        host_id="default",
        game_id=None,
        play_date=date(2026, 10, 20),
        teams=[{"name": "Old", "key": "old", "participants": None, "valid_from": None,
                "valid_until": None, "team_id": None}],
        contact_name="Someone",
        terms_accepted_at=created_at,
        terms_version="v1",
        challenge=f"seeded-{uuid4().hex}",
        status=status,
        created_at=created_at,
    )
    for name, value in fields.items():
        setattr(row, name, value)
    with session_factory() as session:
        session.add(row)
        session.commit()
        return row.id


# --- GET /games and the challenge ------------------------------------------------------------


def test_public_games_only_requestable_and_shape(client):
    response = client.get("/api/public/games")
    assert response.status_code == 200
    games = response.json()
    assert games == [
        {"key": "plovdiv", "name": "Plovdiv Hills", "intro": "Intro of Plovdiv Hills"},
        {
            "key": "sofia-old-town",
            "name": "Sofia Old Town Quest",
            "intro": "Intro of Sofia Old Town Quest",
        },
    ]
    assert all(set(game) == {"key", "name", "intro"} for game in games)


def test_challenge_response_carries_timing(make_client, clock):
    client = make_client(request_min_fill_seconds=7)
    response = client.get("/api/public/requests/challenge")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert set(body) == {*ALTCHA_FIELDS, "min_fill_seconds", "expires_in_seconds"}
    assert body["min_fill_seconds"] == 7
    assert body["expires_in_seconds"] == CHALLENGE_TTL_SECONDS == 600
    assert body["maxnumber"] == MAX_NUMBER
    assert body["salt"].endswith(f"?expires={int(clock.now.timestamp()) + 600}")


# --- POST /requests: the happy path -----------------------------------------------------------


def test_submit_happy_path(client, clock, session_factory, logs):
    altcha = _solved(client)
    clock.advance(seconds=3)
    response = client.post(
        "/api/public/requests",
        json=_body(
            altcha,
            contact_name=f"  {CONTACT}  ",
            contact_phone="  +359 88 123 4567 ",
            message="  We are six friends.  ",
            teams=[
                {"name": f" {TEAM_NAME} ", "key": "red-foxes", "participants": 4},
                {"name": "Blue Jays", "key": "blue-jays", "participants": None},
            ],
        ),
    )
    assert response.status_code == 201
    assert response.json() == {}
    with session_factory() as session:
        row = session.scalars(select(GameRequest)).one()
        game = session.scalars(select(Game).where(Game.key == "sofia-old-town")).one()
    assert row.host_id == "default"
    assert row.game_id == game.id
    assert row.play_date == date(2026, 10, 20)
    assert row.teams == [
        {"name": TEAM_NAME, "key": "red-foxes", "participants": 4, "valid_from": None,
         "valid_until": None, "team_id": None},
        {"name": "Blue Jays", "key": "blue-jays", "participants": None, "valid_from": None,
         "valid_until": None, "team_id": None},
    ]
    assert row.contact_name == CONTACT
    assert row.contact_email == EMAIL
    assert row.contact_phone == "+359 88 123 4567"
    assert row.message == "We are six friends."
    assert row.exit_message is None
    assert row.status == "pending"
    assert row.created_at == row.terms_accepted_at == clock.now
    assert row.terms_version == "11 October 2026"
    assert row.challenge == altcha["challenge"]
    assert row.decided_at is None and row.decided_by is None
    assert any("stored" in message for message in _reasons(logs))
    for personal in (EMAIL, CONTACT, TEAM_NAME):
        assert personal not in logs.text


def test_strings_are_stripped_before_length_checks(client, clock, session_factory):
    name = "N" * 200
    response = _submit(
        client,
        clock,
        contact_name=f"   {name}   ",
        teams=[{"name": f"  {name}  ", "key": "  long  ", "participants": 1}],
        contact_email=f"  {EMAIL}  ",
        terms_version="  v1  ",
        website="   ",
    )
    assert response.status_code == 201
    with session_factory() as session:
        row = session.scalars(select(GameRequest)).one()
    assert row.contact_name == name
    assert row.teams[0]["name"] == name and row.teams[0]["key"] == "long"
    assert row.contact_email == EMAIL
    assert row.contact_phone is None and row.message is None
    assert row.terms_version == "v1"


def test_submit_after_min_fill_from_issue_is_stored(client, clock, session_factory, settings):
    altcha = _solved(client)
    clock.advance(seconds=settings.request_min_fill_seconds)
    response = client.post("/api/public/requests", json=_body(altcha))
    assert response.status_code == 201
    assert _count(session_factory) == 1


def test_min_fill_zero_stores_immediately(make_client, clock, session_factory):
    client = make_client(request_min_fill_seconds=0)
    assert _submit(client, clock, wait=0).status_code == 201
    assert _count(session_factory) == 1


# --- Step 1: size -----------------------------------------------------------------------------


def test_too_large_by_content_length_413(client, session_factory):
    response = client.post(
        "/api/public/requests",
        content=b"{" + b" " * (16 * 1024) + b"}",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413
    assert response.json() == {"detail": "too_large"}
    assert _count(session_factory) == 0


def test_too_large_chunked_body_413(client, session_factory):
    def chunks():
        yield b"{"
        for _ in range(17):
            yield b" " * 1024
        yield b"}"

    response = client.post(
        "/api/public/requests", content=chunks(), headers={"Content-Type": "application/json"}
    )
    assert "content-length" not in {k.lower() for k in response.request.headers}
    assert response.status_code == 413
    assert response.json() == {"detail": "too_large"}
    assert _count(session_factory) == 0


def test_body_at_limit_is_not_too_large(client, clock, session_factory):
    altcha = _solved(client)
    clock.advance(seconds=3)
    raw = json.dumps(_body(altcha)).encode()
    padded = raw[:-1] + b" " * (16 * 1024 - len(raw)) + b"}"
    assert len(padded) == 16 * 1024
    response = client.post(
        "/api/public/requests", content=padded, headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 201
    assert _count(session_factory) == 1


# --- Step 2: schema ---------------------------------------------------------------------------


def _team(i: int, **overrides) -> dict:
    return {"name": f"Team {i}", "key": f"team-{i}", "participants": 2, **overrides}


SCHEMA_CASES = [
    ("missing game_key", {"game_key": None}, "game_key"),
    ("play_date not iso", {"play_date": "20.10.2026"}, "play_date"),
    ("play_date number", {"play_date": 1792000000}, "play_date"),
    ("no teams", {"teams": []}, "teams"),
    ("too many teams", {"teams": [_team(i) for i in range(11)]}, "teams"),
    ("blank team name", {"teams": [_team(0, name="   ")]}, "teams.0.name"),
    ("team name too long", {"teams": [_team(0, name="x" * 201)]}, "teams.0.name"),
    ("bad team key", {"teams": [_team(0, key="Bad Key")]}, "teams.0.key"),
    ("team key too long", {"teams": [_team(0, key="k" * 101)]}, "teams.0.key"),
    ("zero participants", {"teams": [_team(0, participants=0)]}, "teams.0.participants"),
    ("too many participants", {"teams": [_team(0, participants=501)]}, "teams.0.participants"),
    ("extra team field", {"teams": [_team(0, colour="red")]}, "teams.0.colour"),
    ("repeated name", {"teams": [_team(0, name="Foxes"), _team(1, name=" FOXES ")]}, "teams.1.name"),
    ("repeated key", {"teams": [_team(0, key="foxes"), _team(1, key="foxes")]}, "teams.1.key"),
    ("blank contact name", {"contact_name": "  "}, "contact_name"),
    ("contact name too long", {"contact_name": "x" * 201}, "contact_name"),
    ("no email or phone", {"contact_email": " ", "contact_phone": None}, "contact_email"),
    ("bad email", {"contact_email": "not-an-email"}, "contact_email"),
    ("bad phone", {"contact_email": None, "contact_phone": "call me"}, "contact_phone"),
    ("phone too short", {"contact_phone": "12345"}, "contact_phone"),
    ("message too long", {"message": "m" * 2001}, "message"),
    ("terms not accepted", {"terms_accepted": False}, "terms_accepted"),
    ("blank terms version", {"terms_version": "  "}, "terms_version"),
    ("terms version too long", {"terms_version": "v" * 65}, "terms_version"),
    ("honeypot too long", {"website": "w" * 201}, "website"),
    ("missing altcha", {"altcha": None}, "altcha"),
    ("extra field", {"ip": "1.2.3.4"}, "ip"),
]


@pytest.mark.parametrize(
    ("overrides", "field"),
    [case[1:] for case in SCHEMA_CASES],
    ids=[case[0] for case in SCHEMA_CASES],
)
def test_schema_422(client, clock, session_factory, overrides, field):
    body = {**_body(_solved(client)), **overrides}
    for key, value in overrides.items():
        if value is None and key in ("game_key", "altcha"):
            del body[key]
    clock.advance(seconds=3)
    response = client.post("/api/public/requests", json=body)
    assert response.status_code == 422
    errors = response.json()["errors"]
    assert field in {error["field"] for error in errors}, errors
    assert all(set(error) == {"field", "message"} for error in errors)
    assert _count(session_factory) == 0


def test_invalid_json_422(client, session_factory):
    response = client.post(
        "/api/public/requests", content=b"{not json", headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 422
    assert "errors" in response.json()
    assert _count(session_factory) == 0


def test_max_teams_comes_from_settings(make_client, clock, session_factory):
    client = make_client(request_max_teams=2)
    response = _submit(client, clock, teams=[_team(i) for i in range(3)])
    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == "teams"
    assert _submit(client, clock, teams=[_team(i) for i in range(2)]).status_code == 201


# --- Step 3: honeypot -------------------------------------------------------------------------


def test_honeypot_silent_201(client, clock, session_factory, logs):
    # The honeypot is checked before the challenge, so even a garbage challenge gets the 201.
    response = client.post(
        "/api/public/requests",
        json=_body({"algorithm": "SHA-256"}, website="https://spam.example"),
    )
    assert response.status_code == 201
    assert response.json() == {}
    assert _count(session_factory) == 0
    _assert_logged(logs, "honeypot")


# --- Step 4: challenge ------------------------------------------------------------------------


def _tamper_signature(altcha: dict) -> None:
    altcha["signature"] = ("0" if altcha["signature"][0] != "0" else "1") + altcha["signature"][1:]


def _wrong_number(altcha: dict) -> None:
    altcha["number"] = (altcha["number"] + 1) % (MAX_NUMBER + 1)


def _number_above_max(altcha: dict) -> None:
    altcha["number"] = altcha["number"] + (MAX_NUMBER + 1) * 1000
    altcha["maxnumber"] = 10**9  # the server's own setting wins over the payload's


CHALLENGE_CASES = [
    ("signature", _tamper_signature, 3, "challenge_signature"),
    ("expired", lambda altcha: None, CHALLENGE_TTL_SECONDS, "challenge_expired"),
    ("wrong number", _wrong_number, 3, "challenge_solution"),
    ("number above max", _number_above_max, 3, "challenge_solution"),
]


@pytest.mark.parametrize(
    ("tamper", "wait", "code"),
    [case[1:] for case in CHALLENGE_CASES],
    ids=[case[0] for case in CHALLENGE_CASES],
)
def test_challenge_failure_422(client, clock, session_factory, logs, tamper, wait, code):
    altcha = _solved(client)
    tamper(altcha)
    clock.advance(seconds=wait)
    response = client.post("/api/public/requests", json=_body(altcha))
    assert response.status_code == 422
    assert [error["field"] for error in response.json()["errors"]] == ["altcha"]
    assert _count(session_factory) == 0
    _assert_logged(logs, code)


def test_challenge_checked_before_fill_time(client, session_factory, logs):
    altcha = _solved(client)
    _wrong_number(altcha)
    response = client.post("/api/public/requests", json=_body(altcha))  # no wait: too fast too
    assert response.status_code == 422
    _assert_logged(logs, "challenge_solution")


def test_challenge_reuse_422(client, clock, session_factory, logs):
    altcha = _solved(client)
    clock.advance(seconds=3)
    assert client.post("/api/public/requests", json=_body(altcha)).status_code == 201
    again = _body(
        altcha,
        contact_email="other@example.com",
        teams=[{"name": "Other", "key": "other", "participants": 2}],
    )
    response = client.post("/api/public/requests", json=again)
    assert response.status_code == 422
    assert [error["field"] for error in response.json()["errors"]] == ["altcha"]
    assert _count(session_factory) == 1
    _assert_logged(logs, "challenge_reused")


def test_challenge_reuse_race_maps_integrity_error(client, clock, session_factory, logs, monkeypatch):
    altcha = _solved(client)
    _stored(session_factory, created_at=clock.now - timedelta(days=2), challenge=altcha["challenge"])
    monkeypatch.setattr(service, "challenge_used", lambda session, challenge: False)
    clock.advance(seconds=3)
    response = client.post("/api/public/requests", json=_body(altcha))
    assert response.status_code == 422
    assert [error["field"] for error in response.json()["errors"]] == ["altcha"]
    assert _count(session_factory) == 1
    _assert_logged(logs, "challenge_reused")


# --- Step 5: fill time ------------------------------------------------------------------------


def test_too_fast_silent_201(client, clock, session_factory, settings, logs):
    altcha = _solved(client)
    clock.advance(seconds=settings.request_min_fill_seconds - 1)
    response = client.post("/api/public/requests", json=_body(altcha))
    assert response.status_code == 201
    assert response.json() == {}
    assert _count(session_factory) == 0
    _assert_logged(logs, "too_fast")


# --- Step 6: purge (D5, I7) -------------------------------------------------------------------


def _decided(session_factory, status: str, decided_at: datetime) -> int:
    return _stored(
        session_factory, status=status, created_at=decided_at - timedelta(days=1),
        decided_at=decided_at, decided_by="admin@example.com",
    )


def _ids(session_factory) -> set[int]:
    with session_factory() as session:
        return set(session.scalars(select(GameRequest.id)))


def test_retention_purge(session_factory, clock):
    start = clock.now
    old_pending = _stored(session_factory, created_at=start - timedelta(days=400))
    old_approved = _decided(session_factory, "approved", start)
    old_rejected = _decided(session_factory, "rejected", start)
    clock.advance(days=10)
    fresh_rejected = _decided(session_factory, "rejected", clock.now)
    other_host = _stored(
        session_factory, created_at=start, status="approved", decided_at=start, host_id="other"
    )
    clock.advance(days=20)  # old rows decided exactly 30 days ago: not yet past retention
    with session_factory() as session:
        assert service.purge_decided_requests(session, clock.now, 30) == 0
        session.commit()
    clock.advance(seconds=1)
    with session_factory() as session:
        assert service.purge_decided_requests(session, clock.now, 30) == 3
        session.commit()
    # Pending rows stay however old; the fresh decision is kept; retention is global, not per host.
    assert _ids(session_factory) == {old_pending, fresh_rejected}
    assert {old_approved, old_rejected, other_host}.isdisjoint(_ids(session_factory))


def test_submit_runs_the_purge(client, clock, session_factory):
    old = _decided(session_factory, "approved", clock.now - timedelta(days=31))
    fresh = _decided(session_factory, "rejected", clock.now - timedelta(days=29))
    pending = _stored(session_factory, created_at=clock.now - timedelta(days=90))
    assert _submit(client, clock).status_code == 201
    remaining = _ids(session_factory)
    assert old not in remaining
    assert {fresh, pending} <= remaining
    assert len(remaining) == 3


def test_purge_uses_retention_setting(make_client, clock, session_factory):
    client = make_client(request_retention_days=5)
    _decided(session_factory, "approved", clock.now - timedelta(days=6))
    assert _submit(client, clock).status_code == 201
    # Compare statuses, not ids: SQLite may hand the purged row's id to the new one.
    with session_factory() as session:
        assert list(session.scalars(select(GameRequest.status))) == ["pending"]


# --- Step 7: pending cap ----------------------------------------------------------------------


def test_pending_cap_503(make_client, clock, session_factory, logs):
    client = make_client(request_max_pending=2)
    for days in (2, 3):
        _stored(session_factory, created_at=clock.now - timedelta(days=days))
    _decided(session_factory, "approved", clock.now - timedelta(days=1))
    _stored(session_factory, created_at=clock.now - timedelta(days=2), host_id="other")
    before = _count(session_factory)
    # Unknown game too: the cap (step 7) answers before the game check (step 9).
    response = _submit(client, clock, game_key="nope")
    assert response.status_code == 503
    assert response.json() == {"detail": "not_accepting"}
    assert _count(session_factory) == before
    _assert_logged(logs, "pending_cap")


def test_pending_below_cap_is_accepted(make_client, clock, session_factory):
    client = make_client(request_max_pending=2)
    _stored(session_factory, created_at=clock.now - timedelta(days=2))
    _decided(session_factory, "rejected", clock.now - timedelta(days=1))
    assert _submit(client, clock).status_code == 201


# --- Step 8: hourly cap -----------------------------------------------------------------------


def test_hourly_cap_503(make_client, clock, session_factory, logs):
    client = make_client(request_max_per_hour=2)
    altcha = _solved(client)
    clock.advance(seconds=3)
    _stored(session_factory, created_at=clock.now - timedelta(minutes=59), status="rejected",
            decided_at=clock.now)
    _stored(session_factory, created_at=clock.now - timedelta(minutes=1))
    before = _count(session_factory)
    response = client.post("/api/public/requests", json=_body(altcha, game_key="nope"))
    assert response.status_code == 503
    assert response.json() == {"detail": "not_accepting"}
    assert _count(session_factory) == before
    _assert_logged(logs, "hourly_cap")


def test_hourly_cap_window_is_one_hour(make_client, clock, session_factory):
    client = make_client(request_max_per_hour=2)
    altcha = _solved(client)
    clock.advance(seconds=3)
    _stored(session_factory, created_at=clock.now - timedelta(hours=1))
    _stored(session_factory, created_at=clock.now - timedelta(minutes=30))
    _stored(session_factory, created_at=clock.now, host_id="other")
    response = client.post("/api/public/requests", json=_body(altcha))
    assert response.status_code == 201


# --- Step 9: game and play date ---------------------------------------------------------------


@pytest.mark.parametrize("game_key", ["nope", "secret", "elsewhere"])
def test_unknown_or_unrequestable_game_422(client, clock, session_factory, game_key):
    response = _submit(client, clock, game_key=game_key)
    assert response.status_code == 422
    assert response.json() == {
        "errors": [{"field": "game_key", "message": "This game cannot be requested"}]
    }
    assert _count(session_factory) == 0


@pytest.mark.parametrize(
    ("play_date", "status"),
    [
        ("2026-10-13", 422),  # yesterday
        ("2026-10-14", 201),  # today
        ("2027-10-14", 201),  # today + 365 days
        ("2027-10-15", 422),  # today + 366 days
    ],
)
def test_play_date_range(client, clock, session_factory, play_date, status):
    response = _submit(client, clock, play_date=play_date)
    assert response.status_code == status
    if status == 422:
        assert [error["field"] for error in response.json()["errors"]] == ["play_date"]
        assert _count(session_factory) == 0


def test_play_date_today_is_in_the_games_time_zone(client, clock, session_factory):
    clock.now = datetime(2026, 10, 14, 22, 30, tzinfo=UTC)  # already 15 October in Sofia
    sofia = _submit(client, clock, play_date="2026-10-14")
    assert sofia.status_code == 422
    assert sofia.json()["errors"][0]["field"] == "play_date"
    utc = _submit(client, clock, game_key="plovdiv", play_date="2026-10-14")
    assert utc.status_code == 201


# --- Step 10: duplicate -----------------------------------------------------------------------


def test_duplicate_email_409(client, clock, session_factory, logs):
    assert _submit(client, clock).status_code == 201
    response = _submit(
        client,
        clock,
        contact_email="Maria.Ivanova@Example.com",
        teams=[{"name": "Other", "key": "other", "participants": 2}],
    )
    assert response.status_code == 409
    assert response.json() == {
        "errors": [
            {"field": "contact_email", "message": "You already have a pending request for this day"}
        ]
    }
    assert _count(session_factory) == 1
    _assert_logged(logs, "duplicate")


def test_phone_only_duplicate_409(client, clock, session_factory, logs):
    first = _submit(client, clock, contact_email=None, contact_phone="+359 (88) 123-4567")
    assert first.status_code == 201
    response = _submit(client, clock, contact_email="", contact_phone=" +359881234567 ")
    assert response.status_code == 409
    assert response.json()["errors"] == [
        {"field": "contact_phone", "message": "You already have a pending request for this day"}
    ]
    assert _count(session_factory) == 1
    _assert_logged(logs, "duplicate")
    # Without the leading + it is another number.
    assert _submit(client, clock, contact_email=None, contact_phone="359881234567").status_code == 201


def test_not_a_duplicate_for_another_day_game_or_decided(client, clock, session_factory):
    assert _submit(client, clock).status_code == 201
    assert _submit(client, clock, play_date="2026-10-21").status_code == 201
    assert _submit(client, clock, game_key="plovdiv").status_code == 201
    with session_factory() as session:
        for row in session.scalars(select(GameRequest)):
            row.status = "rejected"
            row.decided_at = clock.now
        session.commit()
    assert _submit(client, clock).status_code == 201
    assert _count(session_factory) == 4


# --- Step 11: team clash ----------------------------------------------------------------------


def test_team_clash_422_per_team(client, clock, session_factory):
    response = _submit(
        client,
        clock,
        teams=[
            {"name": "Brand New", "key": "explorers", "participants": 2},
            {"name": "the explorers", "key": "fresh", "participants": 2},
            {"name": "Night Owls", "key": "owls", "participants": 2},  # another host's team
        ],
    )
    assert response.status_code == 422
    assert [error["field"] for error in response.json()["errors"]] == [
        "teams.0.key",
        "teams.1.name",
    ]
    assert _count(session_factory) == 0


def test_team_clashes_one_error_per_team(session_factory):
    with session_factory() as session:
        errors = service.team_clashes(
            session, "default", [{"name": "THE EXPLORERS", "key": "explorers"}]
        )
    assert [error.field for error in errors] == ["teams.0.key"]


def test_duplicate_is_checked_before_clash(client, clock, session_factory):
    assert _submit(client, clock).status_code == 201
    response = _submit(client, clock, teams=[{"name": "X", "key": "explorers", "participants": 1}])
    assert response.status_code == 409


# --- CORS (D10) -------------------------------------------------------------------------------


def test_cors_for_configured_origin(make_client, clock):
    client = make_client(public_site_origin=ORIGIN)
    games = client.get("/api/public/games", headers={"Origin": ORIGIN})
    assert games.headers["access-control-allow-origin"] == ORIGIN
    assert "access-control-allow-credentials" not in games.headers
    preflight = client.options(
        "/api/public/requests",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == ORIGIN
    assert "POST" in preflight.headers["access-control-allow-methods"]
    assert "content-type" in preflight.headers["access-control-allow-headers"].lower()
    refused = client.post("/api/public/requests", json={}, headers={"Origin": ORIGIN})
    assert refused.status_code == 422
    assert refused.headers["access-control-allow-origin"] == ORIGIN


def test_no_cors_for_another_origin(make_client):
    client = make_client(public_site_origin=ORIGIN)
    games = client.get("/api/public/games", headers={"Origin": "https://evil.example"})
    assert games.status_code == 200
    assert "access-control-allow-origin" not in games.headers
    preflight = client.options(
        "/api/public/requests",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in preflight.headers


def test_no_cors_when_origin_unset(client):
    games = client.get("/api/public/games", headers={"Origin": ORIGIN})
    assert games.status_code == 200
    assert "access-control-allow-origin" not in games.headers
    preflight = client.options(
        "/api/public/requests",
        headers={"Origin": ORIGIN, "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in preflight.headers
