"""Stateless ALTCHA-compatible proof-of-work challenge for the public request form (plan D4).

Protocol:

* ``salt = <16-byte hex>?expires=<unix>``
* ``challenge = sha256hex(salt + str(N))`` for a random ``N`` in ``[0, max_number]``
* ``signature = hmac_sha256hex(secret, challenge)``
* ``algorithm = "SHA-256"``

The signature covers only ``challenge``. The salt (and so ``expires``) and the number are bound to
the challenge through the hash, so ``verify`` checks, in this order:

1. ``challenge_signature``: the payload is malformed, the algorithm is not SHA-256, or the
   signature does not match ``HMAC(secret, challenge)``. A forged or altered challenge stops here.
2. ``challenge_solution``: the number is not an integer in ``[0, cap]``, the salt is malformed, or
   ``sha256hex(salt + str(number))`` differs from ``challenge``. A tampered salt, tampered
   ``expires`` or wrong number stops here.
3. ``challenge_expired``: ``now >= expires``. This runs after the hash check on purpose: only then
   is ``expires`` authenticated, so a client cannot extend validity by editing it.

``cap`` is the ``max_number`` keyword when given, else the payload's ``maxnumber``. ``maxnumber``
is not signed, so the router passes its own setting. Single use (``challenge_reused``) is enforced
by DB uniqueness in the router, not here.
"""

import hashlib
import hmac
import re
import secrets
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

ALGORITHM = "SHA-256"
CHALLENGE_TTL_SECONDS = 600

_SALT_RE = re.compile(r"^[0-9a-f]{32}\?expires=([0-9]{1,12})$")
_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")

SIGNATURE = "challenge_signature"
EXPIRED = "challenge_expired"
SOLUTION = "challenge_solution"


class ChallengeError(Exception):
    """A challenge failed verification; ``code`` is the reason code logged and returned."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sign(secret: str, challenge: str) -> str:
    return hmac.new(secret.encode("utf-8"), challenge.encode("utf-8"), hashlib.sha256).hexdigest()


def issue(secret: str, max_number: int, now: datetime) -> dict[str, Any]:
    """Create a signed challenge that expires ``CHALLENGE_TTL_SECONDS`` after ``now``."""
    expires = int(now.timestamp()) + CHALLENGE_TTL_SECONDS
    salt = f"{secrets.token_hex(16)}?expires={expires}"
    number = secrets.randbelow(max_number + 1)
    challenge = _sha256_hex(f"{salt}{number}")
    return {
        "algorithm": ALGORITHM,
        "challenge": challenge,
        "maxnumber": max_number,
        "salt": salt,
        "signature": _sign(secret, challenge),
    }


def verify(
    payload: Mapping[str, Any],
    secret: str,
    now: datetime,
    *,
    max_number: int | None = None,
) -> datetime:
    """Check a solved challenge and return when it was issued (aware UTC, ``expires - ttl``).

    ``payload`` carries ``algorithm``, ``challenge``, ``maxnumber``, ``salt``, ``signature`` and
    ``number``. Raises ``ChallengeError`` with one of the codes in the module docstring.
    """
    if not isinstance(payload, Mapping):
        raise ChallengeError(SIGNATURE)
    challenge = payload.get("challenge")
    signature = payload.get("signature")
    if (
        payload.get("algorithm") != ALGORITHM
        or not isinstance(challenge, str)
        or not isinstance(signature, str)
        or not _SHA256_HEX_RE.match(challenge)
    ):
        raise ChallengeError(SIGNATURE)
    if not hmac.compare_digest(_sign(secret, challenge).encode(), signature.encode()):
        raise ChallengeError(SIGNATURE)

    number = payload.get("number")
    cap = max_number if max_number is not None else payload.get("maxnumber")
    salt = payload.get("salt")
    if (
        not isinstance(number, int)
        or isinstance(number, bool)
        or not isinstance(cap, int)
        or isinstance(cap, bool)
        or not 0 <= number <= cap
        or not isinstance(salt, str)
    ):
        raise ChallengeError(SOLUTION)
    match = _SALT_RE.match(salt)
    if match is None or not hmac.compare_digest(_sha256_hex(f"{salt}{number}"), challenge):
        raise ChallengeError(SOLUTION)

    expires = datetime.fromtimestamp(int(match.group(1)), UTC)
    if now >= expires:
        raise ChallengeError(EXPIRED)
    return expires - timedelta(seconds=CHALLENGE_TTL_SECONDS)
