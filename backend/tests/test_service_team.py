import pytest
from sqlalchemy import select

from questtour.models import AnswerAttempt, GameRun, Photo, RunDevice, RunTask, TeamAlbum
from questtour.storage import StorageUnavailable
from tests.factories import JPEG, add_service_assignment, play_through


def play(client, token, path, **body):
    return client.post(f"/api/play/{token}/{path}", json=body).json()


def photo(client, token, position=0):
    return client.post(
        f"/api/play/{token}/photo",
        data={"position": str(position)},
        files={"file": ("p.jpg", JPEG, "image/jpeg")},
    ).json()


@pytest.fixture
def service(session_factory, seed, clock) -> str:
    with session_factory() as s:
        return add_service_assignment(s, seed, clock.now)


def test_state_flags_service_links_only(client, seed, service):
    assert client.get(f"/api/play/{seed.token}").json()["service"] is False
    r = client.get(f"/api/play/{service}")  # window closed 29 days ago
    assert r.status_code == 200
    assert r.json()["service"] is True and r.json()["status"] == "not_started"


def test_service_link_starts_outside_window(client, service):
    assert play(client, service, "start")["outcome"] == "ok"


def test_service_run_never_times_out(client, service, clock):
    play(client, service, "start")
    clock.advance(days=10)
    state = client.get(f"/api/play/{service}").json()
    assert state["status"] == "playing" and state["phase"] == "task"
    assert state["clock"]["remaining_seconds"] is None
    assert state["clock"]["warning"] is False
    assert state["clock"]["elapsed_seconds"] == 10 * 24 * 3600


def test_service_reveal_unlocked_immediately(client, service):
    task = play(client, service, "start")["state"]["task"]
    assert task["reveal_unlocked"] is True and task["reveal_unlocks_in_seconds"] is None
    r = play(client, service, "reveal", position=0)
    assert r["outcome"] == "ok" and r["state"]["task"]["completion"] == "revealed"


def test_service_advance_works_without_a_photo(client, service):
    """R-25: the photo is optional for the test team; regular teams still need one (R-1, R-10)."""
    play(client, service, "start")
    play(client, service, "answer", position=0, answer="Alexander Nevsky")
    assert client.get(f"/api/play/{service}").json()["phase"] == "photo"  # photo still offered
    r = play(client, service, "advance", position=0)
    assert r["outcome"] == "ok" and r["state"]["position"] == 1


def test_service_run_stays_off_every_leaderboard(client, seed, service, clock):
    service_final = play_through(client, service, clock)
    assert service_final["status"] == "finished"
    assert service_final["results"]["rank"] is None
    regular_final = play_through(client, seed.token, clock)
    assert [r["team_name"] for r in regular_final["results"]["leaderboard"]] == ["The Explorers"]
    again = client.get(f"/api/play/{service}").json()
    assert [r["team_name"] for r in again["results"]["leaderboard"]] == ["The Explorers"]
    assert again["results"]["rank"] is None


def test_reset_wipes_everything_and_link_restarts(client, service, session_factory, blob_store):
    play(client, service, "start")
    play(client, service, "answer", position=0, answer="wrong")
    play(client, service, "answer", position=0, answer="Alexander Nevsky")
    before = photo(client, service)["state"]["version"]
    with session_factory() as s:
        blob = s.scalars(select(Photo.blob_name)).one()
    assert blob_store.exists("photos", blob)

    r = client.post(f"/api/play/{service}/reset")
    assert r.status_code == 200
    body = r.json()
    assert body["outcome"] == "ok"
    assert body["state"]["status"] == "not_started" and body["state"]["service"] is True
    assert body["state"]["version"] > before  # phones must not drop it (useGame.accept)
    assert not blob_store.exists("photos", blob)
    with session_factory() as s:
        for model in (GameRun, RunTask, AnswerAttempt, Photo, RunDevice):
            assert s.scalars(select(model)).all() == [], model.__name__

    restarted = play(client, service, "start")
    assert restarted["outcome"] == "ok"
    assert restarted["state"]["version"] > body["state"]["version"]
    assert restarted["state"]["position"] == 0 and restarted["state"]["task"]["wrong_attempts"] == 0


def test_reset_wipes_the_stored_album(client, service, clock, blob_store, session_factory):
    """A reset also drops the memories album of the finished run: the record would otherwise
    survive into the new run, and a live one would keep serving the previous run's PDF."""
    play_through(client, service, clock)
    pdf = client.get(f"/api/play/{service}/album.pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF-")
    with session_factory() as s:
        blob = s.scalars(select(TeamAlbum.blob_name)).one()
    assert blob_store.exists("albums", blob)

    assert client.post(f"/api/play/{service}/reset").status_code == 200
    with session_factory() as s:
        assert s.scalars(select(TeamAlbum)).all() == []
    assert not blob_store.exists("albums", blob)


def test_finished_service_game_can_be_replayed(client, service, clock):
    assert play_through(client, service, clock)["status"] == "finished"
    assert client.post(f"/api/play/{service}/reset").status_code == 200
    assert play(client, service, "start")["outcome"] == "ok"
    assert play_through(client, service, clock)["status"] == "finished"


def test_reset_without_run_is_harmless(client, service):
    r = client.post(f"/api/play/{service}/reset")
    assert r.status_code == 200 and r.json()["state"]["status"] == "not_started"


def test_reset_refused_for_regular_links(client, seed):
    play(client, seed.token, "start")
    assert client.post(f"/api/play/{seed.token}/reset").status_code == 404
    assert client.get(f"/api/play/{seed.token}").json()["status"] == "playing"


def test_reset_unknown_token_is_link_not_valid(client):
    r = client.post("/api/play/no-such-token-0123456789abcdef/reset")
    assert r.status_code == 403 and r.json()["error"]["reason"] == "unknown"


def test_reset_survives_blob_delete_failure(client, service, blob_store, monkeypatch, session_factory):
    play(client, service, "start")
    play(client, service, "answer", position=0, answer="Alexander Nevsky")
    photo(client, service)

    def boom(container, name):
        raise StorageUnavailable("down")

    monkeypatch.setattr(blob_store, "delete", boom)
    r = client.post(f"/api/play/{service}/reset")
    assert r.status_code == 200 and r.json()["state"]["status"] == "not_started"
    with session_factory() as s:
        assert s.scalars(select(GameRun)).all() == []
