import re
from datetime import date, datetime
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from questtour.normalize import normalize_answer

SLUG = r"^[a-z0-9][a-z0-9-]*$"

LANGUAGE_CODE_RE = re.compile(r"^[a-z]{2,3}(?:-[a-z0-9]{2,8})*$")

I18nMap = dict[str, str] | None


class _Cfg(BaseModel):
    # coerce_numbers_to_str: YAML reads `accepted_answers: [1879]` or `name: 1984` as numbers.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, coerce_numbers_to_str=True)


class CoordinatesCfg(_Cfg):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class LandmarkBaseCfg(_Cfg):
    id: str = Field(pattern=SLUG)
    name: str = Field(min_length=1)
    name_i18n: I18nMap = None
    task: str = Field(min_length=1)
    task_i18n: I18nMap = None
    task_picture: str | None = None
    accepted_answers: list[str] = Field(min_length=1)
    hint1: str | None = None
    hint1_i18n: I18nMap = None
    hint2: str | None = None
    hint2_i18n: I18nMap = None
    tourist_info: str = Field(min_length=1)
    tourist_info_i18n: I18nMap = None
    tourist_info_picture: str | None = None
    coordinates: CoordinatesCfg | None = None

    @field_validator("accepted_answers")
    @classmethod
    def _answers_not_blank(cls, value: list[str]) -> list[str]:
        if any(normalize_answer(a) == "" for a in value):
            raise ValueError("an accepted answer is empty after normalisation")
        return value

    @field_validator("name_i18n", "task_i18n", "hint1_i18n", "hint2_i18n", "tourist_info_i18n")
    @classmethod
    def _i18n_valid(cls, value: I18nMap) -> I18nMap:
        if value is None:
            return None
        for code, text in value.items():
            if code == "en":
                raise ValueError("use the base fields for English; 'en' is not allowed in *_i18n")
            if not LANGUAGE_CODE_RE.fullmatch(code):
                raise ValueError(f"invalid language code {code!r}")
            if not text or not text.strip():
                raise ValueError(f"translation for {code!r} is blank")
        return value

    @field_validator("hint1_i18n")
    @classmethod
    def _hint1_i18n_needs_hint1(cls, value: I18nMap, info: ValidationInfo) -> I18nMap:
        if value and not info.data.get("hint1"):
            raise ValueError("hint1_i18n requires hint1")
        return value

    @field_validator("hint2_i18n")
    @classmethod
    def _hint2_i18n_needs_hint2(cls, value: I18nMap, info: ValidationInfo) -> I18nMap:
        if value and not info.data.get("hint2"):
            raise ValueError("hint2_i18n requires hint2")
        return value

    @model_validator(mode="after")
    def _hint2_needs_hint1(self) -> "LandmarkBaseCfg":
        if self.hint2 and not self.hint1:
            raise ValueError("hint2 is set but hint1 is empty")
        return self


class LandmarkCfg(LandmarkBaseCfg):
    pass


class RevealCfg(_Cfg):
    attempts: int = Field(5, ge=1)
    minutes: int = Field(20, ge=0)
    penalty_minutes: int = Field(30, ge=0)


class GameBaseCfg(_Cfg):
    id: str = Field(pattern=SLUG)
    name: str = Field(min_length=1)
    intro: str = Field(min_length=1)
    time_zone: str
    max_duration_minutes: int = Field(gt=0)
    reveal: RevealCfg = Field(default_factory=RevealCfg)
    # None = not in the file: sync-config then leaves a flag set in the admin panel alone.
    requestable: bool | None = None

    @field_validator("time_zone")
    @classmethod
    def _valid_zone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"unknown time zone {value!r}") from exc
        return value


class GameCfg(GameBaseCfg):
    tasks: list[str] = Field(min_length=1)

    @field_validator("tasks")
    @classmethod
    def _no_repeats(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("a landmark appears twice in the task list")
        return value


class TeamBaseCfg(_Cfg):
    id: str = Field(pattern=SLUG)
    name: str = Field(min_length=1)
    participants: int | None = Field(default=None, ge=1)


class TeamCfg(TeamBaseCfg):
    pass


class AssignmentBaseCfg(_Cfg):
    team: str
    game: str
    valid_from: str
    valid_until: str
    exit_message: str = ""

    @field_validator("valid_from", "valid_until", mode="before")
    @classmethod
    def _quoted(cls, value):
        if isinstance(value, (datetime, date)):
            raise ValueError(  # noqa: TRY004 - pydantic reports ValueError as a validation error
                'write the timestamp in quotes, e.g. "2026-10-14T09:00:00+03:00"'
            )
        return value


class AssignmentCfg(AssignmentBaseCfg):
    token: str | None = Field(default=None, min_length=22)  # >= 128 bits base64url


class ServiceCfg(_Cfg):
    """R-25: the service (test) team. sync-config fills `tokens` with one link per game."""

    team: str = Field(pattern=SLUG)
    name: str = Field(min_length=1)
    tokens: dict[str, Annotated[str, Field(min_length=22)]] = Field(default_factory=dict)


def parse_window_time(value: str, time_zone: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=ZoneInfo(time_zone))
