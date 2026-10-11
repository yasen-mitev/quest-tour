from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError
from ruamel.yaml import YAML

from questtour.sync.schema import (
    AssignmentBaseCfg,
    AssignmentCfg,
    GameBaseCfg,
    GameCfg,
    LandmarkBaseCfg,
    LandmarkCfg,
    TeamBaseCfg,
    TeamCfg,
)


def test_sample_config_supports_bulgarian():
    """The shipped sample config (the default game) carries Bulgarian in every i18n map.

    English lives in the base fields, so a Bulgarian-speaking team depends on `bg` being
    present for every landmark field.
    """
    config_dir = Path(__file__).resolve().parents[1] / "config"
    doc = YAML(typ="safe").load((config_dir / "landmarks.yaml").read_text(encoding="utf-8"))
    landmarks = [LandmarkCfg.model_validate(raw) for raw in doc["landmarks"]]

    i18n_maps = ("name_i18n", "task_i18n", "hint1_i18n", "hint2_i18n", "tourist_info_i18n")
    languages: set[str] = set()
    for lm in landmarks:
        for key in i18n_maps:
            table = getattr(lm, key) or {}
            assert "bg" in table, f"{lm.id} is missing Bulgarian in {key}"
            assert table["bg"].strip(), f"{lm.id} has blank Bulgarian in {key}"
            languages.update(table)
    assert languages >= {"bg", "de", "sr"}


def test_landmark_base_cfg_validates_minimal_data():
    cfg = LandmarkBaseCfg(
        id="old-bridge",
        name="Old Bridge",
        task="Find the year",
        accepted_answers=["1879"],
        tourist_info="A nice bridge",
    )
    assert cfg.id == "old-bridge"
    assert cfg.hint1 is None
    assert cfg.hint2 is None
    assert cfg.coordinates is None


def test_landmark_base_cfg_rejects_blank_answer():
    with pytest.raises(ValidationError, match="empty after normalisation"):
        LandmarkBaseCfg(
            id="a",
            name="A",
            task="T",
            accepted_answers=["   "],
            tourist_info="I",
        )


def test_landmark_base_cfg_rejects_hint2_without_hint1():
    with pytest.raises(ValidationError, match="hint2 is set but hint1 is empty"):
        LandmarkBaseCfg(
            id="a",
            name="A",
            task="T",
            accepted_answers=["x"],
            hint2="only-two",
            tourist_info="I",
        )


def test_landmark_base_cfg_validates_coordinates():
    cfg = LandmarkBaseCfg(
        id="a",
        name="A",
        task="T",
        accepted_answers=["x"],
        tourist_info="I",
        coordinates={"lat": 42.7, "lon": 23.3},
    )
    assert cfg.coordinates is not None
    assert cfg.coordinates.lat == pytest.approx(42.7)

    with pytest.raises(ValidationError, match="coordinates.lat"):
        LandmarkBaseCfg(
            id="a",
            name="A",
            task="T",
            accepted_answers=["x"],
            tourist_info="I",
            coordinates={"lat": 99, "lon": 200},
        )


def test_landmark_cfg_extends_base_without_extra_behavior():
    assert issubclass(LandmarkCfg, LandmarkBaseCfg)
    cfg = LandmarkCfg(
        id="a",
        name="A",
        task="T",
        accepted_answers=["x"],
        tourist_info="I",
    )
    assert isinstance(cfg, LandmarkBaseCfg)


def test_game_base_cfg_validates_minimal_data():
    cfg = GameBaseCfg(
        id="g",
        name="Game",
        intro="Welcome",
        time_zone="Europe/Sofia",
        max_duration_minutes=120,
    )
    assert cfg.id == "g"
    assert cfg.reveal.attempts == 5


def test_game_base_cfg_rejects_unknown_time_zone():
    with pytest.raises(ValidationError, match="unknown time zone"):
        GameBaseCfg(
            id="g",
            name="G",
            intro="I",
            time_zone="Mars/Base",
            max_duration_minutes=60,
        )


def test_game_cfg_adds_tasks_and_no_repeats_validator():
    assert issubclass(GameCfg, GameBaseCfg)
    cfg = GameCfg(
        id="g",
        name="G",
        intro="I",
        time_zone="Europe/Sofia",
        max_duration_minutes=60,
        tasks=["a", "b"],
    )
    assert cfg.tasks == ["a", "b"]

    with pytest.raises(ValidationError, match="appears twice"):
        GameCfg(
            id="g",
            name="G",
            intro="I",
            time_zone="Europe/Sofia",
            max_duration_minutes=60,
            tasks=["a", "a"],
        )


def test_team_base_cfg_validates_minimal_data():
    cfg = TeamBaseCfg(id="t", name="Team T")
    assert cfg.participants is None

    with pytest.raises(ValidationError, match="participants"):
        TeamBaseCfg(id="t", name="T", participants=0)


def test_team_cfg_extends_base():
    assert issubclass(TeamCfg, TeamBaseCfg)
    cfg = TeamCfg(id="t", name="T")
    assert isinstance(cfg, TeamBaseCfg)


def test_assignment_base_cfg_requires_quoted_timestamps():
    with pytest.raises(ValidationError, match="write the timestamp in quotes"):
        AssignmentBaseCfg(
            team="t",
            game="g",
            valid_from=datetime(2026, 10, 1, tzinfo=UTC),
            valid_until="2026-10-02T00:00:00",
        )
    with pytest.raises(ValidationError, match="write the timestamp in quotes"):
        AssignmentBaseCfg(
            team="t",
            game="g",
            valid_from=date(2026, 10, 1),
            valid_until="2026-10-02T00:00:00",
        )


def test_assignment_base_cfg_accepts_string_timestamps():
    cfg = AssignmentBaseCfg(
        team="t",
        game="g",
        valid_from="2026-10-01T00:00:00",
        valid_until="2026-10-02T00:00:00+02:00",
    )
    assert cfg.exit_message == ""


def test_assignment_cfg_extends_base_and_adds_token():
    assert issubclass(AssignmentCfg, AssignmentBaseCfg)
    cfg = AssignmentCfg(
        team="t",
        game="g",
        valid_from="2026-10-01T00:00:00",
        valid_until="2026-10-02T00:00:00+02:00",
        token="x" * 22,
    )
    assert cfg.token == "x" * 22

    with pytest.raises(ValidationError, match="token"):
        AssignmentCfg(
            team="t",
            game="g",
            valid_from="2026-10-01T00:00:00",
            valid_until="2026-10-02T00:00:00+02:00",
            token="short",
        )


def test_landmark_base_cfg_i18n_round_trip():
    cfg = LandmarkBaseCfg(
        id="pond",
        name="Lily Pond",
        name_i18n={"de": "Seerosenteich"},
        task="Find it",
        task_i18n={"de": "Finde es"},
        accepted_answers=["1879"],
        hint1="hint",
        hint1_i18n={"de": "Hinweis"},
        hint2="hint2",
        hint2_i18n={"de": "Hinweis 2"},
        tourist_info="Info",
        tourist_info_i18n={"de": "Information"},
    )
    assert cfg.name_i18n == {"de": "Seerosenteich"}
    assert cfg.task_i18n == {"de": "Finde es"}
    assert cfg.hint1_i18n == {"de": "Hinweis"}
    assert cfg.hint2_i18n == {"de": "Hinweis 2"}
    assert cfg.tourist_info_i18n == {"de": "Information"}


def test_landmark_base_cfg_rejects_en_i18n_key():
    with pytest.raises(ValidationError, match="'en' is not allowed"):
        LandmarkBaseCfg(
            id="a",
            name="A",
            name_i18n={"en": "A"},
            task="T",
            accepted_answers=["x"],
            tourist_info="I",
        )


def test_landmark_base_cfg_rejects_blank_i18n_value():
    with pytest.raises(ValidationError, match="is blank"):
        LandmarkBaseCfg(
            id="a",
            name="A",
            name_i18n={"de": "   "},
            task="T",
            accepted_answers=["x"],
            tourist_info="I",
        )


def test_landmark_base_cfg_rejects_bad_language_code():
    with pytest.raises(ValidationError, match="invalid language code"):
        LandmarkBaseCfg(
            id="a",
            name="A",
            name_i18n={"German": "A"},
            task="T",
            accepted_answers=["x"],
            tourist_info="I",
        )


def test_landmark_base_cfg_rejects_hint1_i18n_without_hint1():
    with pytest.raises(ValidationError, match="hint1_i18n requires hint1"):
        LandmarkBaseCfg(
            id="a",
            name="A",
            task="T",
            accepted_answers=["x"],
            tourist_info="I",
            hint1_i18n={"de": "Hinweis"},
        )


def test_landmark_base_cfg_rejects_hint2_i18n_without_hint2():
    with pytest.raises(ValidationError, match="hint2_i18n requires hint2"):
        LandmarkBaseCfg(
            id="a",
            name="A",
            task="T",
            accepted_answers=["x"],
            tourist_info="I",
            hint1="h1",
            hint2_i18n={"de": "Hinweis 2"},
        )
