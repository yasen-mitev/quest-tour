"""The memories album (issue #33): a finished run's photos and landmark stories, for the team."""

from datetime import timedelta

from questtour.models import Photo
from tests.factories import ANSWERS, JPEG, seed_game


def play(client, token, path, **body):
    return client.post(f"/api/play/{token}/{path}", json=body).json()


def upload(client, token, position, data=JPEG):
    return client.post(
        f"/api/play/{token}/photo",
        data={"position": str(position)},
        files={"file": ("x.bin", data, "application/octet-stream")},
    ).json()


def finish(client, token, clock, *, photos_per_task=1):
    client.post(f"/api/play/{token}/start")
    for position, answer in enumerate(ANSWERS):
        clock.advance(minutes=10)
        play(client, token, "answer", position=position, answer=answer)
        for _ in range(photos_per_task):
            clock.advance(minutes=1)
            upload(client, token, position)
        play(client, token, "advance", position=position)


def test_album_is_not_ready_before_the_run_ends(client, seed):
    t = seed.token
    assert client.get(f"/api/play/{t}/album").status_code == 409  # not started
    client.post(f"/api/play/{t}/start")
    play(client, t, "answer", position=0, answer=ANSWERS[0])
    upload(client, t, 0)
    assert client.get(f"/api/play/{t}/album").status_code == 409  # playing
    assert client.get(f"/api/play/{t}/photos/1").status_code == 404  # the photo just uploaded: hidden


def test_album_collects_every_chapter_and_photo_of_a_finished_run(client, seed, clock):
    t = seed.token
    finish(client, t, clock, photos_per_task=2)
    album = client.get(f"/api/play/{t}/album").json()
    assert album["game"] == "Sofia Old Town Quest" and album["team"] == "The Explorers"
    assert album["end_reason"] == "finished" and album["task_count"] == 3
    # 3 × 10 min to each answer; the 1-min photo pauses are inside the 5-minute grace (issue #49)
    assert album["total_seconds"] == 30 * 60 and album["rank"] == 1 and album["shared_rank"] is False
    assert album["host_message"] == "Thank you for exploring Sofia with us!"
    assert [c["number"] for c in album["chapters"]] == [1, 2, 3]
    first = album["chapters"][0]
    assert first["landmark"] == "Alexander Nevsky Cathedral"
    assert first["story"].startswith("Built 1882")
    assert first["reached_at"].startswith("2026-10-14T08:10")
    assert [p["taken_at"][11:16] for p in first["photos"]] == ["08:11", "08:12"]
    assert first["photos"][0]["url"] == f"/api/play/{t}/photos/{first['photos'][0]['id']}"


def test_album_photos_are_served_only_for_the_teams_own_live_photos(
    client, seed, clock, session_factory
):
    t = seed.token
    finish(client, t, clock)
    album = client.get(f"/api/play/{t}/album").json()
    photo = album["chapters"][0]["photos"][0]
    response = client.get(photo["url"])
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg" and response.content == JPEG
    assert response.headers["cache-control"] == "private, max-age=3600"

    # the other team's link knows nothing of this photo, even once its own run has ended
    other = seed.other_token
    finish(client, other, clock)
    assert client.get(f"/api/play/{other}/photos/{photo['id']}").status_code == 404

    # a photo the host deleted leaves the album and stops being served
    with session_factory() as s:
        s.get(Photo, photo["id"]).deleted_at = clock.now
        s.commit()
    assert client.get(photo["url"]).status_code == 404
    album = client.get(f"/api/play/{t}/album").json()
    assert album["chapters"][0]["photos"] == []


def test_album_of_a_timed_out_run_has_the_completed_chapters_only(
    client, session_factory, clock
):
    with session_factory() as s:
        seed = seed_game(s, clock.now, max_duration_minutes=30)
    t = seed.token
    client.post(f"/api/play/{t}/start")
    play(client, t, "answer", position=0, answer=ANSWERS[0])
    upload(client, t, 0)
    play(client, t, "advance", position=0)
    clock.advance(minutes=31)
    assert client.get(f"/api/play/{t}").json()["status"] == "timed_out"
    album = client.get(f"/api/play/{t}/album").json()
    assert album["end_reason"] == "max_duration" and album["total_seconds"] is None
    assert album["rank"] is None
    assert [c["landmark"] for c in album["chapters"]] == ["Alexander Nevsky Cathedral"]
    assert len(album["chapters"][0]["photos"]) == 1
    assert album["ended_at"] == (clock.now - timedelta(minutes=1)).isoformat().replace("+00:00", "Z")


def test_album_with_unknown_token_is_403(client, seed):
    response = client.get("/api/play/no-such-token/album")
    assert response.status_code == 403 and response.json()["error"]["code"] == "link_not_valid"
