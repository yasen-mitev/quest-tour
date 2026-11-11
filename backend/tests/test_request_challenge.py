import hashlib
from datetime import UTC, datetime, timedelta

import pytest

from questtour.requests.challenge import CHALLENGE_TTL_SECONDS, ChallengeError, issue, verify

SECRET = "test-secret-test-secret-test-secret-0123"
NOW = datetime(2026, 10, 14, 8, 0, tzinfo=UTC)

# Fixed vector, reused by the website JS solver check (plan T7).
VECTOR = {
    "algorithm": "SHA-256",
    "challenge": "d6f78fb71b2d2f58d3d4eec1777ed4d7b5189e745bfa5a8b9748b98f6b52a4d0",
    "maxnumber": 50000,
    "salt": "00112233445566778899aabbccddeeff?expires=1792000600",
    "signature": "4c543b5d6a39f7a2895d02898bba5628f942828b359cf7a6e1ecc14841a445cc",
}
VECTOR_NUMBER = 1234
VECTOR_ISSUED = datetime.fromtimestamp(1792000000, UTC)


def solve(challenge: dict) -> int:
    for number in range(challenge["maxnumber"] + 1):
        digest = hashlib.sha256(f"{challenge['salt']}{number}".encode()).hexdigest()
        if digest == challenge["challenge"]:
            return number
    raise AssertionError("unsolvable")


def solved(max_number: int = 200, now: datetime = NOW) -> dict:
    challenge = issue(SECRET, max_number, now)
    return {**challenge, "number": solve(challenge)}


def code_of(payload: dict, now: datetime = NOW, **kwargs) -> str:
    with pytest.raises(ChallengeError) as info:
        verify(payload, SECRET, now, **kwargs)
    return info.value.code


def test_issue_shape():
    challenge = issue(SECRET, 200, NOW)
    assert set(challenge) == {"algorithm", "challenge", "maxnumber", "salt", "signature"}
    assert challenge["algorithm"] == "SHA-256"
    assert challenge["maxnumber"] == 200
    expires = int(NOW.timestamp()) + CHALLENGE_TTL_SECONDS
    assert challenge["salt"].endswith(f"?expires={expires}")
    assert len(challenge["salt"].split("?")[0]) == 32
    assert CHALLENGE_TTL_SECONDS == 600


def test_issue_is_random():
    assert issue(SECRET, 200, NOW)["salt"] != issue(SECRET, 200, NOW)["salt"]


def test_brute_force_solution_verifies_and_returns_issue_time():
    payload = solved(now=NOW)
    assert verify(payload, SECRET, NOW) == NOW
    assert verify(payload, SECRET, NOW).tzinfo is not None


def test_max_number_zero_is_solvable():
    assert verify(solved(0), SECRET, NOW) == NOW


def test_fixed_vector():
    assert hashlib.sha256(f"{VECTOR['salt']}{VECTOR_NUMBER}".encode()).hexdigest() == (
        VECTOR["challenge"]
    )
    assert solve({**VECTOR, "maxnumber": 2000}) == VECTOR_NUMBER
    payload = {**VECTOR, "number": VECTOR_NUMBER}
    assert verify(payload, SECRET, VECTOR_ISSUED + timedelta(seconds=5)) == VECTOR_ISSUED


def test_valid_until_just_before_expiry_and_expired_at_expiry():
    payload = solved()
    assert verify(payload, SECRET, NOW + timedelta(seconds=CHALLENGE_TTL_SECONDS - 1)) == NOW
    assert code_of(payload, NOW + timedelta(seconds=CHALLENGE_TTL_SECONDS)) == "challenge_expired"


def test_expired_genuine_challenge():
    assert code_of(solved(), NOW + timedelta(hours=1)) == "challenge_expired"


@pytest.mark.parametrize("field", ["signature", "challenge"])
def test_tampered_signature_or_challenge(field):
    payload = solved()
    payload[field] = ("0" if payload[field][0] != "0" else "1") + payload[field][1:]
    assert code_of(payload) == "challenge_signature"


def test_signature_from_another_secret():
    other = issue("another-secret-another-secret-0123456", 200, NOW)
    other["number"] = solve(other)
    assert code_of(other) == "challenge_signature"


def test_tampered_salt_fails_solution():
    payload = solved()
    payload["salt"] = "f" * 32 + payload["salt"][32:]
    assert code_of(payload) == "challenge_solution"


def test_tampered_expires_cannot_extend_validity():
    payload = solved()
    expires = int(NOW.timestamp()) + CHALLENGE_TTL_SECONDS
    payload["salt"] = payload["salt"].replace(f"expires={expires}", f"expires={expires + 86400}")
    assert code_of(payload) == "challenge_solution"
    # Also when the challenge itself is already expired.
    assert code_of(payload, NOW + timedelta(hours=1)) == "challenge_solution"


def test_wrong_number():
    payload = solved()
    payload["number"] = (payload["number"] + 1) % 201
    assert code_of(payload) == "challenge_solution"


def test_number_above_maxnumber():
    payload = solved(50)
    payload["number"] = payload["number"] + 51 * 1000
    assert code_of(payload) == "challenge_solution"


def test_number_above_payload_maxnumber_even_if_hash_is_right():
    payload = solved(100)
    while payload["number"] == 0:
        payload = solved(100)
    payload["maxnumber"] = payload["number"] - 1
    assert code_of(payload) == "challenge_solution"


def test_max_number_keyword_overrides_payload_maxnumber():
    payload = solved(100)
    while payload["number"] == 0:
        payload = solved(100)
    inflated = {**payload, "maxnumber": 10**9}
    assert verify(inflated, SECRET, NOW, max_number=100) == NOW
    assert code_of(inflated, max_number=payload["number"] - 1) == "challenge_solution"
    deflated = {**payload, "maxnumber": 0}
    assert verify(deflated, SECRET, NOW, max_number=100) == NOW


@pytest.mark.parametrize("bad", [-1, "5", 1.0, None, True, [1]])
def test_malformed_number(bad):
    payload = solved()
    payload["number"] = bad
    assert code_of(payload) == "challenge_solution"


@pytest.mark.parametrize("missing", ["number", "salt", "maxnumber"])
def test_missing_solution_fields(missing):
    payload = solved()
    del payload[missing]
    assert code_of(payload) == "challenge_solution"


@pytest.mark.parametrize("missing", ["algorithm", "challenge", "signature"])
def test_missing_signature_fields(missing):
    payload = solved()
    del payload[missing]
    assert code_of(payload) == "challenge_signature"


@pytest.mark.parametrize("salt", ["", "abc", "x" * 32 + "?expires=1", 5, None])
def test_malformed_salt(salt):
    payload = solved()
    payload["salt"] = salt
    assert code_of(payload) == "challenge_solution"


def test_wrong_algorithm_and_non_mapping_payload():
    payload = solved()
    assert code_of({**payload, "algorithm": "SHA-1"}) == "challenge_signature"
    assert code_of(["x"]) == "challenge_signature"  # type: ignore[arg-type]


def test_non_ascii_signature_does_not_crash():
    payload = solved()
    payload["signature"] = "é" * 64
    assert code_of(payload) == "challenge_signature"
