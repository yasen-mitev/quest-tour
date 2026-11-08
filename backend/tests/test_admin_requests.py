"""Admin API for game play requests (issue #61): list, detail, edit, approve and reject.

Approval is all-or-nothing and happens at most once (I3); another host's requests are hidden (I5);
the list runs the retention purge (I7). Times come from the injected clock.
"""

from datetime import UTC, date, datetime, timedelta
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from questtour.models import Assignment, Game, GameRequest, Team
from questtour.requests import service
from questtour.tokens import hash_token

BASE = "/api/admin/requests"
EXIT_MESSAGE = "Thanks for playing with us!"
PLAY_DATE = date(2026, 10, 14)  # the FakeClock's day; Europe/Sofia is UTC+3 then
DAY_START = "2026-10-13T21:00:00Z"
DAY_END = "2026-10-14T20:59:59Z"
GONE_GAME_ID = 9999  # SQLite does not enforce the FK, so a deleted game leaves a dangling id


@pytest.fixture
def settings(settings):
    return settings.model_copy(update={"default_exit_message": EXIT_MESSAGE})


@pytest.fixture
def admin(client):
    requested = client.post("/api/admin/auth/magic/request", json={"email": "admin@example.com"})
    params = parse_qs(urlparse(requested.json()["url"]).query)
    verified = client.get(
        "/api/admin/auth/magic/verify",
        params={"token": params["token"][0], "email": params["email"][0]},
        follow_redirects=False,
    )
    assert verified.status_code == 307
    return client


def _team(name: str, key: str, participants: int | None = None, **window) -> dict:
    return {
        "name": name,
        "key": key,
        "participants": participants,
        "valid_from": window.get("valid_from"),
        "valid_until": window.get("valid_until"),
        "team_id": None,
    }


def _store(
    session_factory,
    *,
    game_id: int | None,
    created_at: datetime,
    status: str = "pending",
    host_id: str = "default",
    teams: list[dict] | None = None,
    **fields,
) -> int:
    row = GameRequest(
        host_id=host_id,
        game_id=game_id,
        play_date=PLAY_DATE,
        teams=teams if teams is not None else [_team("Red Foxes", "red-foxes", 4)],
        contact_name="Maria Ivanova",
        contact_email="maria@example.com",
        terms_accepted_at=created_at,
        terms_version="11 October 2026",
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


def _counts(session_factory) -> tuple[int, int]:
    with session_factory() as session:
        return (
            session.scalar(select(func.count(Team.id))),
            session.scalar(select(func.count(Assignment.id))),
        )


def _reload(session_factory, request_id: int) -> GameRequest:
    with session_factory() as session:
        return session.get(GameRequest, request_id)


def _seen(client, request_id: int) -> str:
    return client.get(f"{BASE}/{request_id}").json()["updated_at"]


def _other_host_game(session_factory) -> int:
    with session_factory() as session:
        game = Game(
            host_id="other",
            key="elsewhere",
            name="Another Host Game",
            intro="Intro.",
            time_zone="UTC",
            max_duration_minutes=60,
            reveal_after_attempts=5,
            reveal_after_minutes=20,
            reveal_penalty_minutes=30,
        )
        session.add(game)
        session.commit()
        return game.id


def test_requires_admin(client):
    assert client.get(BASE).status_code == 401


def test_list_filter(admin, seed, session_factory, clock):
    now = clock.now
    older = _store(session_factory, game_id=seed.game_id, created_at=now - timedelta(hours=3))
    gone = _store(
        session_factory,
        game_id=GONE_GAME_ID,
        created_at=now - timedelta(hours=1),
        teams=[_team("A", "a"), _team("B", "b")],
        play_date=date(2026, 10, 20),
    )
    approved = _store(
        session_factory,
        game_id=seed.game_id,
        created_at=now - timedelta(hours=2),
        status="approved",
        decided_at=now,
    )
    rejected = _store(
        session_factory,
        game_id=None,
        created_at=now - timedelta(minutes=30),
        status="rejected",
        decided_at=now,
    )

    pending = admin.get(BASE)
    assert pending.status_code == 200
    assert [r["id"] for r in pending.json()] == [gone, older]
    assert pending.json()[0] == {
        "id": gone,
        "created_at": "2026-10-14T07:00:00Z",
        "contact_name": "Maria Ivanova",
        "game_id": GONE_GAME_ID,
        "game_name": None,
        "play_date": "2026-10-20",
        "team_count": 2,
        "status": "pending",
    }
    assert pending.json()[1]["game_name"] == "Sofia Old Town Quest"
    assert admin.get(BASE, params={"status": "pending"}).json() == pending.json()

    assert [r["id"] for r in admin.get(BASE, params={"status": "approved"}).json()] == [approved]
    assert [r["id"] for r in admin.get(BASE, params={"status": "rejected"}).json()] == [rejected]
    everything = admin.get(BASE, params={"status": "all"}).json()
    assert [r["id"] for r in everything] == [rejected, gone, approved, older]

    invalid = admin.get(BASE, params={"status": "bogus"})
    assert invalid.status_code == 422
    assert invalid.json()["errors"][0]["field"] == "query.status"


def test_detail(admin, seed, session_factory, clock):
    request_id = _store(
        session_factory,
        game_id=seed.game_id,
        created_at=clock.now,
        teams=[
            _team("Red Foxes", "red-foxes", 4),
            _team(
                "Blue Jays",
                "blue-jays",
                valid_from="2026-10-14T07:00:00+00:00",
                valid_until="2026-10-14T12:00:00+00:00",
            ),
        ],
        contact_phone="+359 88 123 4567",
        message="Birthday party",
    )

    response = admin.get(f"{BASE}/{request_id}")
    assert response.status_code == 200
    body = response.json()
    assert body.pop("updated_at")
    assert body == {
        "id": request_id,
        "created_at": "2026-10-14T08:00:00Z",
        "status": "pending",
        "game_id": seed.game_id,
        "game_name": "Sofia Old Town Quest",
        "game_time_zone": "Europe/Sofia",
        "play_date": "2026-10-14",
        "contact_name": "Maria Ivanova",
        "contact_email": "maria@example.com",
        "contact_phone": "+359 88 123 4567",
        "message": "Birthday party",
        "exit_message": EXIT_MESSAGE,
        "terms_accepted_at": "2026-10-14T08:00:00Z",
        "terms_version": "11 October 2026",
        "decided_at": None,
        "decided_by": None,
        "teams": [
            {
                "name": "Red Foxes",
                "key": "red-foxes",
                "participants": 4,
                "valid_from": DAY_START,
                "valid_until": DAY_END,
                "team_id": None,
            },
            {
                "name": "Blue Jays",
                "key": "blue-jays",
                "participants": None,
                "valid_from": "2026-10-14T07:00:00Z",
                "valid_until": "2026-10-14T12:00:00Z",
                "team_id": None,
            },
        ],
    }


def test_detail_without_game_leaves_default_windows_unresolved(admin, session_factory, clock):
    request_id = _store(session_factory, game_id=GONE_GAME_ID, created_at=clock.now)
    body = admin.get(f"{BASE}/{request_id}").json()
    assert (body["game_name"], body["game_time_zone"]) == (None, None)
    assert (body["teams"][0]["valid_from"], body["teams"][0]["valid_until"]) == (None, None)


def test_put_edits_pending_request(admin, seed, session_factory, clock):
    request_id = _store(session_factory, game_id=GONE_GAME_ID, created_at=clock.now)

    response = admin.put(
        f"{BASE}/{request_id}",
        json={
            "game_id": seed.game_id,
            "exit_message": "See you at the finish!",
            "teams": [
                {"name": " Red Foxes ", "key": "red-foxes", "participants": 5,
                 "valid_from": "2026-10-14T10:00", "valid_until": "2026-10-14T18:00"},
                {"name": "Blue Jays", "key": "blue-jays", "participants": None,
                 "valid_from": None, "valid_until": None},
            ],
            "seen_at": _seen(admin, request_id),
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["game_name"] == "Sofia Old Town Quest"
    assert body["exit_message"] == "See you at the finish!"
    assert body["teams"] == [
        {"name": "Red Foxes", "key": "red-foxes", "participants": 5,
         "valid_from": "2026-10-14T07:00:00Z", "valid_until": "2026-10-14T15:00:00Z",
         "team_id": None},
        {"name": "Blue Jays", "key": "blue-jays", "participants": None,
         "valid_from": DAY_START, "valid_until": DAY_END, "team_id": None},
    ]
    assert admin.get(f"{BASE}/{request_id}").json()["teams"] == body["teams"]

    stored = _reload(session_factory, request_id)
    assert stored.game_id == seed.game_id
    assert stored.teams[1]["valid_from"] is None  # still the play-date default
    assert stored.status == "pending"


def test_put_validation(admin, seed, session_factory, clock):
    request_id = _store(session_factory, game_id=seed.game_id, created_at=clock.now)
    url = f"{BASE}/{request_id}"

    def put(teams, **overrides):
        return admin.put(url, json={"game_id": seed.game_id, "exit_message": None,
                                    "teams": teams, **overrides})

    def fields(response) -> list[str]:
        assert response.status_code == 422
        return [e["field"] for e in response.json()["errors"]]

    assert fields(put([{"name": "A", "key": "Bad Key"}])) == ["teams.0.key"]
    assert fields(put([{"name": " ", "key": "a"}])) == ["teams.0.name"]
    assert fields(put([{"name": "A", "key": "a", "participants": 0}])) == ["teams.0.participants"]
    assert fields(put([{"name": "A", "key": "a" * 101}])) == ["teams.0.key"]
    assert fields(put([{"name": "Same", "key": "a"}, {"name": "SAME", "key": "a"}])) == [
        "teams.1.key",
        "teams.1.name",
    ]
    assert fields(put([{"name": "A", "key": "a", "valid_from": "tomorrow"}])) == [
        "teams.0.valid_from"
    ]
    assert fields(
        put([{"name": "A", "key": "a",
              "valid_from": "2026-10-14T18:00", "valid_until": "2026-10-14T10:00"}])
    ) == ["teams.0.valid_until"]
    assert fields(put([{"name": "A", "key": "a"}], game_id=_other_host_game(session_factory))) == [
        "game_id"
    ]
    assert fields(put([])) == ["body.teams"]

    stale = put([{"name": "A", "key": "a"}], seen_at="2000-01-01T00:00:00Z")
    assert stale.status_code == 409
    assert stale.json()["entity"] == "GameRequest"

    assert _reload(session_factory, request_id).teams[0]["key"] == "red-foxes"


def test_put_on_decided_request_409(admin, seed, session_factory, clock):
    request_id = _store(
        session_factory, game_id=seed.game_id, created_at=clock.now, status="approved",
        decided_at=clock.now, decided_by="other@example.com",
    )
    response = admin.put(
        f"{BASE}/{request_id}",
        json={"game_id": seed.game_id, "exit_message": None,
              "teams": [{"name": "A", "key": "a"}]},
    )
    assert response.status_code == 409
    assert response.json() == {
        "entity": "GameRequest",
        "current": admin.get(f"{BASE}/{request_id}").json(),
    }
    assert response.json()["current"]["status"] == "approved"
    assert _reload(session_factory, request_id).teams[0]["key"] == "red-foxes"


def test_approve_creates_teams(admin, seed, session_factory, clock):
    window = {"valid_from": "2026-10-14T06:00:00+00:00", "valid_until": "2026-10-14T18:00:00+00:00"}
    request_id = _store(
        session_factory,
        game_id=seed.game_id,
        created_at=clock.now - timedelta(days=2),
        teams=[_team("Red Foxes", "red-foxes", 4), _team("Blue Jays", "blue-jays", **window)],
    )
    clock.advance(minutes=5)

    response = admin.post(f"{BASE}/{request_id}/approve", json={"seen_at": _seen(admin, request_id)})
    assert response.status_code == 200
    reveals = response.json()
    assert len(reveals) == 2

    stored = _reload(session_factory, request_id)
    assert stored.status == "approved"
    assert stored.decided_at == clock.now
    assert stored.decided_by == "admin@example.com"

    with session_factory() as session:
        for spec, reveal in zip(stored.teams, reveals, strict=True):
            assignment = session.get(Assignment, reveal["assignment_id"])
            team = session.get(Team, spec["team_id"])
            assert assignment.team_id == team.id
            assert assignment.game_id == seed.game_id
            assert assignment.token_hash == hash_token(reveal["token"])
            assert assignment.issued_at == clock.now
            assert assignment.exit_message == EXIT_MESSAGE
            assert reveal["url"] == f"http://test/play/{reveal['token']}"
            assert (team.key, team.name, team.participants) == (
                spec["key"], spec["name"], spec["participants"],
            )
        foxes = session.get(Assignment, reveals[0]["assignment_id"])
        assert foxes.valid_from == datetime(2026, 10, 13, 21, 0, tzinfo=UTC)
        assert foxes.valid_until == datetime(2026, 10, 14, 20, 59, 59, tzinfo=UTC)
        jays = session.get(Assignment, reveals[1]["assignment_id"])
        assert jays.valid_from == datetime(2026, 10, 14, 6, 0, tzinfo=UTC)
        assert jays.valid_until == datetime(2026, 10, 14, 18, 0, tzinfo=UTC)

    for reveal in reveals:
        assert admin.get(f"/api/play/{reveal['token']}").status_code == 200

    detail = admin.get(f"{BASE}/{request_id}").json()
    assert detail["status"] == "approved"
    assert [t["team_id"] for t in detail["teams"]] == [t["team_id"] for t in stored.teams]
    assert all(t["team_id"] for t in detail["teams"])


def test_approve_uses_the_request_exit_message(admin, seed, session_factory, clock):
    request_id = _store(
        session_factory, game_id=seed.game_id, created_at=clock.now, exit_message="Custom bye"
    )
    reveal = admin.post(f"{BASE}/{request_id}/approve", json={}).json()[0]
    with session_factory() as session:
        assert session.get(Assignment, reveal["assignment_id"]).exit_message == "Custom bye"


@pytest.mark.parametrize("game_id", [None, GONE_GAME_ID])
def test_approve_with_missing_game_422(admin, session_factory, clock, game_id):
    request_id = _store(session_factory, game_id=game_id, created_at=clock.now)
    before = _counts(session_factory)

    response = admin.post(f"{BASE}/{request_id}/approve", json={})
    assert response.status_code == 422
    assert [e["field"] for e in response.json()["errors"]] == ["game_id"]
    assert _counts(session_factory) == before
    assert _reload(session_factory, request_id).status == "pending"


def test_approve_other_host_game_422(admin, session_factory, clock):
    request_id = _store(
        session_factory, game_id=_other_host_game(session_factory), created_at=clock.now
    )
    response = admin.post(f"{BASE}/{request_id}/approve", json={})
    assert response.status_code == 422
    assert [e["field"] for e in response.json()["errors"]] == ["game_id"]


def test_approve_clash_creates_nothing(admin, seed, session_factory, clock):
    request_id = _store(
        session_factory,
        game_id=seed.game_id,
        created_at=clock.now,
        teams=[
            _team("Fresh Team", "fresh"),
            _team("Somebody", "explorers"),  # the seeded team's key
            _team("NIGHT OWLS", "new-owls"),  # the seeded team's name, other case
        ],
    )
    before = _counts(session_factory)

    response = admin.post(f"{BASE}/{request_id}/approve", json={})
    assert response.status_code == 422
    assert [e["field"] for e in response.json()["errors"]] == ["teams.1.key", "teams.2.name"]
    assert _counts(session_factory) == before
    assert _reload(session_factory, request_id).status == "pending"


def test_double_approve_409(admin, seed, session_factory, clock):
    request_id = _store(session_factory, game_id=seed.game_id, created_at=clock.now)
    assert admin.post(f"{BASE}/{request_id}/approve", json={}).status_code == 200
    after_first = _counts(session_factory)

    second = admin.post(f"{BASE}/{request_id}/approve", json={})
    assert second.status_code == 409
    body = second.json()
    assert body == {"entity": "GameRequest", "current": admin.get(f"{BASE}/{request_id}").json()}
    assert body["current"]["status"] == "approved"
    assert body["current"]["teams"][0]["team_id"]
    assert _counts(session_factory) == after_first


def test_concurrent_decision_409(admin, seed, session_factory, clock, monkeypatch):
    """The conditional status flip refuses when another admin decided after this one's checks."""
    request_id = _store(session_factory, game_id=seed.game_id, created_at=clock.now)
    original = service.team_clashes

    def clashes_then_rejected_elsewhere(session, host_id, teams):
        errors = original(session, host_id, teams)
        with session_factory() as other:
            other.get(GameRequest, request_id).status = "rejected"
            other.commit()
        return errors

    monkeypatch.setattr(service, "team_clashes", clashes_then_rejected_elsewhere)
    before = _counts(session_factory)

    response = admin.post(f"{BASE}/{request_id}/approve", json={})
    assert response.status_code == 409
    assert response.json()["entity"] == "GameRequest"
    assert response.json()["current"]["status"] == "rejected"
    assert _counts(session_factory) == before


def test_approve_race_maps_team_fields(admin, seed, session_factory, clock, monkeypatch):
    """A team created between the clash check and the flush rolls everything back."""
    request_id = _store(
        session_factory,
        game_id=seed.game_id,
        created_at=clock.now,
        teams=[_team("Fresh Team", "fresh"), _team("Red Foxes", "red-foxes")],
    )
    original = service.team_clashes
    calls = []

    def check_then_race(session, host_id, teams):
        errors = original(session, host_id, teams)
        if not calls:
            with session_factory() as other:
                other.add(Team(host_id="default", key="red-foxes", name="Racing Foxes"))
                other.commit()
        calls.append(errors)
        return errors

    monkeypatch.setattr(service, "team_clashes", check_then_race)
    before_teams, before_assignments = _counts(session_factory)

    response = admin.post(f"{BASE}/{request_id}/approve", json={})
    assert response.status_code == 422
    assert [e["field"] for e in response.json()["errors"]] == ["teams.1.key"]
    assert len(calls) == 2  # the check ran again after the rollback
    assert _counts(session_factory) == (before_teams + 1, before_assignments)  # the racer only
    stored = _reload(session_factory, request_id)
    assert stored.status == "pending"
    assert stored.decided_at is None
    assert [t["team_id"] for t in stored.teams] == [None, None]


def test_reject(admin, seed, session_factory, clock):
    request_id = _store(session_factory, game_id=seed.game_id, created_at=clock.now)
    before = _counts(session_factory)
    clock.advance(minutes=1)

    response = admin.post(f"{BASE}/{request_id}/reject", json={"seen_at": _seen(admin, request_id)})
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert response.json()["decided_at"] == "2026-10-14T08:01:00Z"
    assert response.json()["decided_by"] == "admin@example.com"
    assert _counts(session_factory) == before
    stored = _reload(session_factory, request_id)
    assert (stored.status, stored.decided_at) == ("rejected", clock.now)


def test_decided_request_is_read_only(admin, seed, session_factory, clock):
    request_id = _store(session_factory, game_id=seed.game_id, created_at=clock.now)
    assert admin.post(f"{BASE}/{request_id}/reject", json={}).status_code == 200
    before = _counts(session_factory)
    url = f"{BASE}/{request_id}"

    edit = admin.put(url, json={"game_id": seed.game_id, "exit_message": None,
                                "teams": [{"name": "A", "key": "a"}]})
    for response in (
        edit,
        admin.post(f"{url}/approve", json={}),
        admin.post(f"{url}/reject", json={}),
    ):
        assert response.status_code == 409
        assert response.json()["current"]["status"] == "rejected"
    assert admin.get(url).status_code == 200
    assert _counts(session_factory) == before
    assert _reload(session_factory, request_id).status == "rejected"


def test_other_host_hidden(admin, session_factory, clock):
    game_id = _other_host_game(session_factory)
    request_id = _store(session_factory, game_id=game_id, created_at=clock.now, host_id="other")
    url = f"{BASE}/{request_id}"

    assert admin.get(BASE, params={"status": "all"}).json() == []
    assert admin.get(url).status_code == 404
    assert admin.put(url, json={"game_id": game_id, "exit_message": None,
                                "teams": [{"name": "A", "key": "a"}]}).status_code == 404
    assert admin.post(f"{url}/approve", json={}).status_code == 404
    assert admin.post(f"{url}/reject", json={}).status_code == 404
    assert _reload(session_factory, request_id).status == "pending"


def test_retention_purge(admin, seed, session_factory, clock):
    now = clock.now
    old_approved = _store(session_factory, game_id=seed.game_id, created_at=now,
                          status="approved", decided_at=now)
    old_rejected = _store(session_factory, game_id=seed.game_id, created_at=now,
                          status="rejected", decided_at=now)
    pending = _store(session_factory, game_id=seed.game_id, created_at=now)
    clock.advance(days=20)
    fresh = _store(session_factory, game_id=seed.game_id, created_at=clock.now,
                   status="rejected", decided_at=clock.now)

    clock.advance(days=10)  # exactly the retention: nothing is old enough yet
    listed = {r["id"] for r in admin.get(BASE, params={"status": "all"}).json()}
    assert listed == {old_approved, old_rejected, pending, fresh}

    clock.advance(seconds=1)
    listed = {r["id"] for r in admin.get(BASE, params={"status": "all"}).json()}
    assert listed == {pending, fresh}
    with session_factory() as session:
        assert session.scalar(select(func.count(GameRequest.id))) == 2
