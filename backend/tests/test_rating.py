"""Riddle ratings and the word for the host (issue #38)."""

from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from tests.factories import ANSWERS, JPEG

PHONE_A = {"X-Device-Id": "device-aaaa-0001"}
PHONE_B = {"X-Device-Id": "device-bbbb-0002"}


def play(client, token, path, headers=None, **body):
    return client.post(f"/api/play/{token}/{path}", json=body, headers=headers).json()


def upload(client, token, position):
    return client.post(
        f"/api/play/{token}/photo",
        data={"position": str(position)},
        files={"file": ("x.bin", JPEG, "application/octet-stream")},
    ).json()


def finish(client, token, clock):
    client.post(f"/api/play/{token}/start")
    for position, answer in enumerate(ANSWERS):
        clock.advance(minutes=10)
        play(client, token, "answer", position=position, answer=answer)
        upload(client, token, position)
        play(client, token, "advance", position=position)


def login_admin(client: TestClient) -> None:
    requested = client.post("/api/admin/auth/magic/request", json={"email": "admin@example.com"})
    params = parse_qs(urlparse(requested.json()["url"]).query)
    verified = client.get(
        "/api/admin/auth/magic/verify",
        params={"token": params["token"][0], "email": params["email"][0]},
        follow_redirects=False,
    )
    assert verified.status_code == 307


def test_rating_needs_a_completed_riddle_and_is_per_phone_and_changeable(client, seed, clock):
    t = seed.token
    client.post(f"/api/play/{t}/start")
    assert play(client, t, "rate", position=0, stars=4)["outcome"] == "stale"      # not solved yet
    r = play(client, t, "answer", position=0, answer=ANSWERS[0])
    assert r["state"]["task"]["rating"] is None
    r = play(client, t, "rate", position=0, stars=4)
    assert r["outcome"] == "ok" and r["state"]["task"]["rating"] == 4
    assert r["state"]["version"] == client.get(f"/api/play/{t}").json()["version"]   # no version bump
    r = play(client, t, "rate", position=0, stars=2)                               # changed their mind
    assert r["outcome"] == "ok" and r["state"]["task"]["rating"] == 2
    other = play(client, t, "rate", headers=PHONE_B, position=0, stars=5)         # a teammate's own stars
    assert other["outcome"] == "ok" and other["state"]["task"]["rating"] == 5
    assert client.get(f"/api/play/{t}").json()["task"]["rating"] == 2              # this phone still sees 2
    assert play(client, t, "rate", position=1, stars=3)["outcome"] == "stale"      # a riddle not reached
    assert client.post(f"/api/play/{t}/rate", json={"position": 0, "stars": 6}).status_code == 422
    assert client.post(f"/api/play/{t}/rate", json={"position": 0, "stars": 0}).status_code == 422


def test_results_carry_the_teams_average_over_every_phone(client, seed, clock):
    t = seed.token
    client.post(f"/api/play/{t}/start")
    for position, answer in enumerate(ANSWERS):
        clock.advance(minutes=10)
        play(client, t, "answer", position=position, answer=answer)
        play(client, t, "rate", position=position, stars=5)
        play(client, t, "rate", headers=PHONE_B, position=position, stars=3)
        upload(client, t, position)
        r = play(client, t, "advance", position=position)
    results = r["state"]["results"]
    assert results["average_rating"] == 4.0 and results["ratings_count"] == 6
    assert results["feedback_submitted"] is False
    # a rating for an earlier riddle still counts after the game
    play(client, t, "rate", position=0, stars=1)
    assert client.get(f"/api/play/{t}").json()["results"]["average_rating"] == round(20 / 6, 2)


def test_results_without_ratings_have_no_average(client, seed, clock):
    finish(client, seed.token, clock)
    results = client.get(f"/api/play/{seed.token}").json()["results"]
    assert results["average_rating"] is None and results["ratings_count"] == 0


def test_feedback_only_after_the_game_one_per_phone(client, seed, clock):
    t = seed.token
    client.post(f"/api/play/{t}/start")
    assert play(client, t, "feedback", text="Great!")["outcome"] == "stale"       # still playing
    finish(client, t, clock)
    r = play(client, t, "feedback", text="  Loved the bridge riddle.  ")
    assert r["outcome"] == "ok" and r["state"]["results"]["feedback_submitted"] is True
    assert play(client, t, "feedback", text="Again")["outcome"] == "ok"           # ignored: the first stands
    other = client.get(f"/api/play/{t}", headers=PHONE_B).json()
    assert other["results"]["feedback_submitted"] is False                        # a teammate may still write
    assert play(client, t, "feedback", headers=PHONE_B, text="Too long walks.")["outcome"] == "ok"
    assert client.post(f"/api/play/{t}/feedback", json={"text": ""}).status_code == 422
    assert client.post(f"/api/play/{t}/feedback", json={"text": "x" * 1001}).status_code == 422


def test_host_sees_averages_per_riddle_and_the_comments(client, seed, clock):
    t, other = seed.token, seed.other_token
    for token, stars in ((t, 5), (other, 3)):
        client.post(f"/api/play/{token}/start")
        for position, answer in enumerate(ANSWERS):
            clock.advance(minutes=10)
            play(client, token, "answer", position=position, answer=answer)
            play(client, token, "rate", position=position, stars=stars if position == 0 else 4)
            upload(client, token, position)
            play(client, token, "advance", position=position)
    play(client, t, "feedback", text="Loved the bridge riddle.")
    clock.advance(minutes=1)
    play(client, other, "feedback", text="Too long walks.")

    assert client.get("/api/admin/feedback").status_code == 401
    login_admin(client)
    data = client.get("/api/admin/feedback").json()
    assert [(r["landmark_name"], r["average"], r["count"]) for r in data["riddles"]] == [
        ("Alexander Nevsky Cathedral", 4.0, 2),
        ("Ancient Serdika Complex", 4.0, 2),
        ("Rotunda of St George", 4.0, 2),
    ]
    assert [(c["team_name"], c["text"]) for c in data["comments"]] == [
        ("Night Owls", "Too long walks."),
        ("The Explorers", "Loved the bridge riddle."),
    ]
