"""Game play requests (issue #61): validation of the public form and the database checks.

``api/public.py`` runs these in the order fixed by the plan's "Public API" contract; the admin
requests API reuses ``purge_decided_requests`` (D5) and ``team_clashes``.
"""

import re
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, EmailStr, Field, ValidationError, field_validator
from sqlalchemy import delete, exists, func, select
from sqlalchemy.orm import Session

from questtour.admin.errors import AdminValidationError, FieldError, _pydantic_errors
from questtour.admin.schemas import SLUG
from questtour.models import Game, GameRequest, Team

PENDING = "pending"
DECIDED = ("approved", "rejected")
MAX_PLAY_DATE_DAYS = 365
DUPLICATE_MESSAGE = "You already have a pending request for this day"

_PHONE_DROP = re.compile(r"[^0-9]")


def _blank_to_none(value: Any) -> Any:
    """D7: optional strings are stripped and an empty one counts as not given."""
    if isinstance(value, str):
        return value.strip() or None
    return value


class TeamIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200)
    key: str = Field(max_length=100, pattern=SLUG)
    participants: int | None = Field(None, ge=1, le=500)


class RequestIn(BaseModel):
    """The public form body. Strings are stripped before the length checks (D7)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    game_key: str
    play_date: date = Field(strict=True)  # ISO text only, no unix timestamps
    teams: list[TeamIn] = Field(min_length=1)
    contact_name: str = Field(min_length=1, max_length=200)
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(None, max_length=32, pattern=r"^\+?[0-9 ()/-]{6,32}$")
    message: str | None = Field(None, max_length=2000)
    terms_accepted: Literal[True]
    terms_version: str = Field(min_length=1, max_length=64)
    website: str | None = Field(None, max_length=200)  # the honeypot
    altcha: dict[str, Any]

    _optional = field_validator(
        "contact_email", "contact_phone", "message", "website", mode="before"
    )(_blank_to_none)


def _request_errors(data: RequestIn, max_teams: int) -> list[FieldError]:
    """The rules that span fields or depend on settings, checked once the schema has passed."""
    errors = []
    if len(data.teams) > max_teams:
        errors.append(FieldError(field="teams", message=f"At most {max_teams} teams"))
    names: set[str] = set()
    keys: set[str] = set()
    for i, team in enumerate(data.teams):
        if team.name.casefold() in names:
            errors.append(FieldError(field=f"teams.{i}.name", message="Team names must differ"))
        if team.key in keys:
            errors.append(FieldError(field=f"teams.{i}.key", message="Team keys must differ"))
        names.add(team.name.casefold())
        keys.add(team.key)
    if data.contact_email is None and data.contact_phone is None:
        errors.append(
            FieldError(field="contact_email", message="Give an email address or a phone number")
        )
    return errors


def parse_request(raw: bytes, max_teams: int) -> RequestIn:
    """Validate the raw JSON body; raises ``AdminValidationError`` (422 ``{"errors": [...]}``)."""
    try:
        data = RequestIn.model_validate_json(raw)
    except ValidationError as exc:
        raise AdminValidationError(_pydantic_errors(exc)) from exc
    errors = _request_errors(data, max_teams)
    if errors:
        raise AdminValidationError(errors)
    return data


def normalize_phone(phone: str) -> str:
    """D7: a leading ``+`` is kept, then digits only."""
    return ("+" if phone.startswith("+") else "") + _PHONE_DROP.sub("", phone)


def challenge_used(session: Session, challenge: str) -> bool:
    """D3: a challenge stored with any request is consumed."""
    return bool(session.scalar(select(exists().where(GameRequest.challenge == challenge))))


def purge_decided_requests(session: Session, now: datetime, days: int) -> int:
    """D5: delete approved and rejected requests decided more than ``days`` before ``now``.

    Pending requests stay until decided. The caller commits. Returns the number of rows deleted.
    """
    result = session.execute(
        delete(GameRequest).where(
            GameRequest.status.in_(DECIDED),
            GameRequest.decided_at < now - timedelta(days=days),
        )
    )
    return result.rowcount


def capacity_refusal(
    session: Session, host_id: str, now: datetime, *, max_pending: int, max_per_hour: int
) -> str | None:
    """The reason code when the host is not accepting requests now, else ``None``."""
    pending = session.scalar(
        select(func.count(GameRequest.id)).where(
            GameRequest.host_id == host_id, GameRequest.status == PENDING
        )
    )
    if pending >= max_pending:
        return "pending_cap"
    last_hour = session.scalar(
        select(func.count(GameRequest.id)).where(
            GameRequest.host_id == host_id, GameRequest.created_at > now - timedelta(hours=1)
        )
    )
    if last_hour >= max_per_hour:
        return "hourly_cap"
    return None


def requestable_game(session: Session, host_id: str, key: str) -> Game | None:
    return session.scalars(
        select(Game).where(Game.host_id == host_id, Game.key == key, Game.requestable)
    ).one_or_none()


def play_date_allowed(game: Game, play_date: date, now: datetime) -> bool:
    """D9: from today to today + 365 days, in the game's time zone."""
    today = now.astimezone(ZoneInfo(game.time_zone)).date()
    return today <= play_date <= today + timedelta(days=MAX_PLAY_DATE_DAYS)


def duplicate_field(session: Session, host_id: str, game_id: int, data: RequestIn) -> str | None:
    """D7: the contact field of a pending request for the same game and day, else ``None``.

    The key is the lower-cased email; without an email, the normalized phone.
    """
    same_day = select(GameRequest).where(
        GameRequest.host_id == host_id,
        GameRequest.game_id == game_id,
        GameRequest.play_date == data.play_date,
        GameRequest.status == PENDING,
    )
    if data.contact_email is not None:
        email = data.contact_email.lower()
        found = session.scalar(
            select(exists(same_day.where(func.lower(GameRequest.contact_email) == email)))
        )
        return "contact_email" if found else None
    phone = normalize_phone(data.contact_phone)
    for row in session.scalars(same_day.where(GameRequest.contact_phone.is_not(None))):
        if normalize_phone(row.contact_phone) == phone:
            return "contact_phone"
    return None


def team_clashes(
    session: Session, host_id: str, teams: Sequence[Mapping[str, Any]]
) -> list[FieldError]:
    """One error per team whose key, or case-insensitive name, already exists for the host.

    ``teams`` are mappings with ``name`` and ``key``; a key clash is reported over a name clash.
    """
    # Names are compared in Python: SQLite's lower() folds ASCII only.
    existing = session.execute(select(Team.key, Team.name).where(Team.host_id == host_id)).all()
    taken_keys = {key for key, _ in existing}
    taken_names = {name.casefold() for _, name in existing}
    errors = []
    for i, team in enumerate(teams):
        if team["key"] in taken_keys:
            errors.append(
                FieldError(field=f"teams.{i}.key", message="A team with this key already exists")
            )
        elif team["name"].casefold() in taken_names:
            errors.append(
                FieldError(field=f"teams.{i}.name", message="A team with this name already exists")
            )
    return errors


def new_request(
    host_id: str, game_id: int, data: RequestIn, challenge: str, now: datetime
) -> GameRequest:
    """A pending request; every time comes from ``now`` (the injected clock)."""
    return GameRequest(
        host_id=host_id,
        game_id=game_id,
        play_date=data.play_date,
        teams=[
            {
                "name": team.name,
                "key": team.key,
                "participants": team.participants,
                "valid_from": None,
                "valid_until": None,
                "team_id": None,
            }
            for team in data.teams
        ],
        contact_name=data.contact_name,
        contact_email=data.contact_email,
        contact_phone=data.contact_phone,
        message=data.message,
        status=PENDING,
        terms_accepted_at=now,
        terms_version=data.terms_version,
        challenge=challenge,
        created_at=now,
    )
