from contextlib import contextmanager
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.middleware.sessions import SessionMiddleware

from questtour.admin import admin_router
from questtour.admin.errors import register_admin_exception_handlers
from questtour.auth import auth_router
from questtour.db import Base
from questtour.models import Assignment, GameRequest, Team
from questtour.settings import Settings
from questtour.storage import LocalBlobStore


@contextmanager
def count_queries(engine, substring):
    counts = {"n": 0}

    def handler(conn, cursor, statement, parameters, context, executemany):
        if substring in statement:
            counts["n"] += 1

    event.listen(engine, "before_cursor_execute", handler)
    try:
        yield counts
    finally:
        event.remove(engine, "before_cursor_execute", handler)


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        _env_file=None,
        database_url="sqlite://",
        public_base_url="http://test",
        storage_backend="local",
        local_storage_dir=tmp_path / "blobs",
        static_dir=None,
        admin_session_secret="test-secret-must-be-at-least-32-bytes-long",
        admin_auth_provider="dev",
        admin_dev_emails=["admin@example.com"],
    )


@pytest.fixture
def engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def session_factory(engine):
    return sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def blob_store(tmp_path) -> LocalBlobStore:
    return LocalBlobStore(tmp_path / "blobs")


@pytest.fixture
def admin_app(settings, session_factory, blob_store):
    app = FastAPI()
    app.state.settings = settings
    app.state.session_factory = session_factory
    app.state.blob_store = blob_store
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.admin_session_secret,
        session_cookie="questtour_admin_session",
        max_age=settings.admin_session_max_age_minutes * 60,
        same_site="lax",
        https_only=settings.admin_session_secure,
    )
    register_admin_exception_handlers(app)
    app.include_router(auth_router)
    app.include_router(admin_router)
    return app


@pytest.fixture
def admin_client(admin_app) -> TestClient:
    return TestClient(admin_app, raise_server_exceptions=False)


def _login(client: TestClient) -> None:
    request_resp = client.post("/api/admin/auth/magic/request", json={"email": "admin@example.com"})
    assert request_resp.status_code == 200
    parsed = urlparse(request_resp.json()["url"])
    params = parse_qs(parsed.query)
    verify_resp = client.get(
        "/api/admin/auth/magic/verify",
        params={"token": params["token"][0], "email": params["email"][0]},
        follow_redirects=False,
    )
    assert verify_resp.status_code == 307


def _create_landmark(client: TestClient, key: str, name: str) -> int:
    resp = client.post(
        "/api/admin/landmarks",
        json={
            "key": key,
            "name": name,
            "task": f"Find {name}.",
            "accepted_answers": [name.lower()],
            "tourist_info": f"Info about {name}.",
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def test_create_game_returns_structured_data(admin_client):
    _login(admin_client)
    payload = {
        "key": "city-tour",
        "name": "City Tour",
        "intro": "Welcome to the city tour.",
        "time_zone": "Europe/Sofia",
        "max_duration_minutes": 120,
    }
    resp = admin_client.post("/api/admin/games", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["key"] == "city-tour"
    assert data["name"] == "City Tour"
    assert data["intro"] == "Welcome to the city tour."
    assert data["time_zone"] == "Europe/Sofia"
    assert data["max_duration_minutes"] == 120
    assert data["reveal"] == {"attempts": 5, "minutes": 20, "penalty_minutes": 30}
    assert data["task_landmark_ids"] == []
    assert "updated_at" in data


def test_requestable_defaults_false_and_round_trips(admin_client):
    _login(admin_client)
    base = {
        "key": "req-game",
        "name": "Req Game",
        "intro": "Intro.",
        "time_zone": "Europe/Sofia",
        "max_duration_minutes": 60,
    }
    created = admin_client.post("/api/admin/games", json=base)
    assert created.status_code == 201
    assert created.json()["requestable"] is False
    game_id = created.json()["id"]

    resp = admin_client.put(f"/api/admin/games/{game_id}", json={**base, "requestable": True})
    assert resp.status_code == 200
    assert resp.json()["requestable"] is True
    assert admin_client.get(f"/api/admin/games/{game_id}").json()["requestable"] is True
    assert [g["requestable"] for g in admin_client.get("/api/admin/games").json()] == [True]

    # An update that omits the flag leaves it alone.
    resp = admin_client.put(f"/api/admin/games/{game_id}", json=base)
    assert resp.status_code == 200
    assert resp.json()["requestable"] is True

    resp = admin_client.put(f"/api/admin/games/{game_id}", json={**base, "requestable": False})
    assert resp.json()["requestable"] is False


def test_create_game_can_be_requestable(admin_client):
    _login(admin_client)
    resp = admin_client.post(
        "/api/admin/games",
        json={
            "key": "open-game",
            "name": "Open Game",
            "intro": "Intro.",
            "time_zone": "Europe/Sofia",
            "max_duration_minutes": 60,
            "requestable": True,
        },
    )
    assert resp.status_code == 201
    assert resp.json()["requestable"] is True


def test_create_game_with_custom_reveal_settings(admin_client):
    _login(admin_client)
    payload = {
        "key": "hard-tour",
        "name": "Hard Tour",
        "intro": "Hard.",
        "time_zone": "Europe/Sofia",
        "max_duration_minutes": 60,
        "reveal": {"attempts": 3, "minutes": 10, "penalty_minutes": 15},
    }
    resp = admin_client.post("/api/admin/games", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["reveal"] == {"attempts": 3, "minutes": 10, "penalty_minutes": 15}


def test_create_game_rejects_invalid_time_zone(admin_client):
    _login(admin_client)
    payload = {
        "key": "bad-zone",
        "name": "Bad Zone",
        "intro": "Intro.",
        "time_zone": "Mars/Colony",
        "max_duration_minutes": 60,
    }
    resp = admin_client.post("/api/admin/games", json=payload)
    assert resp.status_code == 422
    data = resp.json()
    assert "errors" in data
    assert any("time_zone" in e["field"] for e in data["errors"])


def test_create_game_rejects_non_positive_max_duration(admin_client):
    _login(admin_client)
    payload = {
        "key": "bad-duration",
        "name": "Bad Duration",
        "intro": "Intro.",
        "time_zone": "Europe/Sofia",
        "max_duration_minutes": 0,
    }
    resp = admin_client.post("/api/admin/games", json=payload)
    assert resp.status_code == 422
    data = resp.json()
    assert "errors" in data
    assert any("max_duration_minutes" in e["field"] for e in data["errors"])


def test_duplicate_key_returns_422_field_error(admin_client):
    _login(admin_client)
    payload = {
        "key": "duplicate-game",
        "name": "Duplicate",
        "intro": "Intro.",
        "time_zone": "Europe/Sofia",
        "max_duration_minutes": 60,
    }
    assert admin_client.post("/api/admin/games", json=payload).status_code == 201
    resp = admin_client.post("/api/admin/games", json=payload)
    assert resp.status_code == 422
    data = resp.json()
    assert "errors" in data
    assert any(e["field"] == "key" for e in data["errors"])


def test_list_games(admin_client):
    _login(admin_client)
    for key, name in [("alpha-game", "Alpha Game"), ("beta-game", "Beta Game")]:
        admin_client.post(
            "/api/admin/games",
            json={
                "key": key,
                "name": name,
                "intro": "Intro.",
                "time_zone": "Europe/Sofia",
                "max_duration_minutes": 60,
            },
        )
    resp = admin_client.get("/api/admin/games")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["name"] == "Alpha Game"
    assert data[1]["name"] == "Beta Game"


def test_get_game_by_id(admin_client):
    _login(admin_client)
    create_resp = admin_client.post(
        "/api/admin/games",
        json={
            "key": "get-game",
            "name": "Get Game",
            "intro": "Intro.",
            "time_zone": "Europe/Sofia",
            "max_duration_minutes": 60,
        },
    )
    game_id = create_resp.json()["id"]
    resp = admin_client.get(f"/api/admin/games/{game_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == game_id
    assert data["key"] == "get-game"


def test_get_unknown_game_returns_404(admin_client):
    _login(admin_client)
    resp = admin_client.get("/api/admin/games/9999")
    assert resp.status_code == 404


def test_update_game_returns_structured_data(admin_client):
    _login(admin_client)
    create_resp = admin_client.post(
        "/api/admin/games",
        json={
            "key": "update-game",
            "name": "Update Game",
            "intro": "Intro.",
            "time_zone": "Europe/Sofia",
            "max_duration_minutes": 60,
        },
    )
    game_id = create_resp.json()["id"]
    payload = {
        "key": "updated-game",
        "name": "Updated Game",
        "intro": "Updated intro.",
        "time_zone": "Europe/Berlin",
        "max_duration_minutes": 90,
        "reveal": {"attempts": 2, "minutes": 5, "penalty_minutes": 10},
    }
    resp = admin_client.put(f"/api/admin/games/{game_id}", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["key"] == "updated-game"
    assert data["name"] == "Updated Game"
    assert data["intro"] == "Updated intro."
    assert data["time_zone"] == "Europe/Berlin"
    assert data["max_duration_minutes"] == 90
    assert data["reveal"] == {"attempts": 2, "minutes": 5, "penalty_minutes": 10}


def test_update_game_with_stale_seen_at_returns_409(admin_client):
    _login(admin_client)
    create_resp = admin_client.post(
        "/api/admin/games",
        json={
            "key": "stale-game",
            "name": "Stale Game",
            "intro": "Intro.",
            "time_zone": "Europe/Sofia",
            "max_duration_minutes": 60,
        },
    )
    game_id = create_resp.json()["id"]
    stale = datetime(2020, 1, 1, tzinfo=UTC).isoformat()
    payload = {
        "key": "stale-game",
        "name": "Updated",
        "intro": "Updated.",
        "time_zone": "Europe/Sofia",
        "max_duration_minutes": 60,
        "seen_at": stale,
    }
    resp = admin_client.put(f"/api/admin/games/{game_id}", json=payload)
    assert resp.status_code == 409
    data = resp.json()
    assert data["entity"] == "Game"
    assert "current" in data


def test_update_game_tasks_reorders_and_returns_ok(admin_client):
    _login(admin_client)
    lm1 = _create_landmark(admin_client, "lm1", "First Landmark")
    lm2 = _create_landmark(admin_client, "lm2", "Second Landmark")
    create_resp = admin_client.post(
        "/api/admin/games",
        json={
            "key": "task-game",
            "name": "Task Game",
            "intro": "Intro.",
            "time_zone": "Europe/Sofia",
            "max_duration_minutes": 60,
        },
    )
    game_id = create_resp.json()["id"]

    resp = admin_client.put(f"/api/admin/games/{game_id}/tasks", json={"landmark_ids": [lm2, lm1]})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    get_resp = admin_client.get(f"/api/admin/games/{game_id}/tasks")
    assert get_resp.status_code == 200
    assert get_resp.json()["landmark_ids"] == [lm2, lm1]

    game_resp = admin_client.get(f"/api/admin/games/{game_id}")
    assert game_resp.json()["task_landmark_ids"] == [lm2, lm1]


def test_update_game_tasks_rejects_duplicate_landmarks(admin_client):
    _login(admin_client)
    lm1 = _create_landmark(admin_client, "dup1", "Dup One")
    create_resp = admin_client.post(
        "/api/admin/games",
        json={
            "key": "dup-game",
            "name": "Dup Game",
            "intro": "Intro.",
            "time_zone": "Europe/Sofia",
            "max_duration_minutes": 60,
        },
    )
    game_id = create_resp.json()["id"]
    resp = admin_client.put(
        f"/api/admin/games/{game_id}/tasks", json={"landmark_ids": [lm1, lm1]}
    )
    assert resp.status_code == 422
    data = resp.json()
    assert "errors" in data
    assert any("landmark_ids" in e["field"] for e in data["errors"])


def test_update_game_tasks_rejects_unknown_landmark_ids(admin_client):
    _login(admin_client)
    create_resp = admin_client.post(
        "/api/admin/games",
        json={
            "key": "unknown-lm",
            "name": "Unknown LM",
            "intro": "Intro.",
            "time_zone": "Europe/Sofia",
            "max_duration_minutes": 60,
        },
    )
    game_id = create_resp.json()["id"]
    resp = admin_client.put(
        f"/api/admin/games/{game_id}/tasks", json={"landmark_ids": [99999]}
    )
    assert resp.status_code == 422
    data = resp.json()
    assert "errors" in data
    assert any("landmark_ids" in e["field"] for e in data["errors"])


def test_update_game_tasks_bumps_updated_at(admin_client):
    _login(admin_client)
    lm1 = _create_landmark(admin_client, "bump1", "Bump One")
    create_resp = admin_client.post(
        "/api/admin/games",
        json={
            "key": "bump-game",
            "name": "Bump Game",
            "intro": "Intro.",
            "time_zone": "Europe/Sofia",
            "max_duration_minutes": 60,
        },
    )
    game_id = create_resp.json()["id"]
    before = create_resp.json()["updated_at"]

    resp = admin_client.put(f"/api/admin/games/{game_id}/tasks", json={"landmark_ids": [lm1]})
    assert resp.status_code == 200

    game_resp = admin_client.get(f"/api/admin/games/{game_id}")
    after = game_resp.json()["updated_at"]
    assert after != before


def test_update_game_tasks_with_stale_seen_at_returns_409(admin_client):
    _login(admin_client)
    lm1 = _create_landmark(admin_client, "stale-lm1", "Stale LM")
    create_resp = admin_client.post(
        "/api/admin/games",
        json={
            "key": "stale-tasks",
            "name": "Stale Tasks",
            "intro": "Intro.",
            "time_zone": "Europe/Sofia",
            "max_duration_minutes": 60,
        },
    )
    game_id = create_resp.json()["id"]
    stale = datetime(2020, 1, 1, tzinfo=UTC).isoformat()
    resp = admin_client.put(
        f"/api/admin/games/{game_id}/tasks",
        json={"landmark_ids": [lm1], "seen_at": stale},
    )
    assert resp.status_code == 409
    data = resp.json()
    assert data["entity"] == "Game"
    assert "current" in data


def test_delete_game_blocked_by_assignment(admin_client, session_factory):
    _login(admin_client)
    create_resp = admin_client.post(
        "/api/admin/games",
        json={
            "key": "assigned-game",
            "name": "Assigned Game",
            "intro": "Intro.",
            "time_zone": "Europe/Sofia",
            "max_duration_minutes": 60,
        },
    )
    game_id = create_resp.json()["id"]
    with session_factory() as session:
        team = Team(host_id="default", key="team", name="Team")
        assignment = Assignment(
            host_id="default",
            team=team,
            game_id=game_id,
            valid_from=datetime.now(UTC),
            valid_until=datetime.now(UTC),
            exit_message="",
        )
        session.add_all([team, assignment])
        session.commit()

    resp = admin_client.delete(f"/api/admin/games/{game_id}")
    assert resp.status_code == 409
    assert "assignment" in resp.json()["detail"].lower()


def test_delete_game_blocked_by_pending_request(admin_client, session_factory):
    _login(admin_client)
    create_resp = admin_client.post(
        "/api/admin/games",
        json={
            "key": "requested-game",
            "name": "Requested Game",
            "intro": "Intro.",
            "time_zone": "Europe/Sofia",
            "max_duration_minutes": 60,
        },
    )
    game_id = create_resp.json()["id"]
    now = datetime.now(UTC)
    with session_factory() as session:
        request = GameRequest(
            host_id="default",
            game_id=game_id,
            play_date=now.date(),
            teams=[],
            contact_name="Maria",
            terms_accepted_at=now,
            terms_version="v1",
            challenge="delete-guard",
            status="pending",
            created_at=now,
        )
        session.add(request)
        session.commit()
        request_id = request.id

    resp = admin_client.delete(f"/api/admin/games/{game_id}")
    assert resp.status_code == 409
    assert resp.json()["detail"] == "cannot delete a game that has pending requests"

    # A decided request does not block the deletion.
    with session_factory() as session:
        session.get(GameRequest, request_id).status = "rejected"
        session.commit()
    resp = admin_client.delete(f"/api/admin/games/{game_id}")
    assert resp.status_code == 200
    assert resp.json() == {"deleted": True}


def test_delete_game_succeeds_when_unused(admin_client):
    _login(admin_client)
    create_resp = admin_client.post(
        "/api/admin/games",
        json={
            "key": "delete-game",
            "name": "Delete Game",
            "intro": "Intro.",
            "time_zone": "Europe/Sofia",
            "max_duration_minutes": 60,
        },
    )
    game_id = create_resp.json()["id"]
    resp = admin_client.delete(f"/api/admin/games/{game_id}")
    assert resp.status_code == 200
    assert resp.json() == {"deleted": True}


def test_list_games_avoids_landmark_n_plus_one(admin_client, engine):
    _login(admin_client)
    landmark_ids = []
    for i in range(5):
        landmark_ids.append(
            _create_landmark(admin_client, f"n1-lm-{i}", f"Landmark {i}")
        )
    create_resp = admin_client.post(
        "/api/admin/games",
        json={
            "key": "n1-list",
            "name": "N+1 List",
            "intro": "Intro.",
            "time_zone": "Europe/Sofia",
            "max_duration_minutes": 60,
        },
    )
    game_id = create_resp.json()["id"]
    admin_client.put(
        f"/api/admin/games/{game_id}/tasks",
        json={"landmark_ids": landmark_ids},
    )

    with count_queries(engine, "FROM landmarks") as counts:
        resp = admin_client.get("/api/admin/games")
    assert resp.status_code == 200
    assert counts["n"] <= 1


def test_get_game_avoids_landmark_n_plus_one(admin_client, engine):
    _login(admin_client)
    landmark_ids = []
    for i in range(5):
        landmark_ids.append(
            _create_landmark(admin_client, f"n1-get-{i}", f"Landmark {i}")
        )
    create_resp = admin_client.post(
        "/api/admin/games",
        json={
            "key": "n1-get",
            "name": "N+1 Get",
            "intro": "Intro.",
            "time_zone": "Europe/Sofia",
            "max_duration_minutes": 60,
        },
    )
    game_id = create_resp.json()["id"]
    admin_client.put(
        f"/api/admin/games/{game_id}/tasks",
        json={"landmark_ids": landmark_ids},
    )

    with count_queries(engine, "FROM landmarks") as counts:
        resp = admin_client.get(f"/api/admin/games/{game_id}")
    assert resp.status_code == 200
    assert counts["n"] <= 1
