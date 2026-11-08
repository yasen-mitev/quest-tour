import hashlib
from datetime import UTC
from pathlib import Path

import pytest
from sqlalchemy import select

from questtour.cli.sync_config import main
from questtour.db import Base
from questtour.models import Assignment, Game, GameRun, Landmark, RunTask, Team
from questtour.services.game import start_run
from questtour.settings import get_settings
from questtour.sync.apply import apply_config
from questtour.sync.loader import load_config
from questtour.sync.teams_file import issue_tokens, write_teams_file
from questtour.tokens import hash_token

SVG = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"/>'
LANDMARKS = """
landmarks:
  - {id: a, name: Alpha, task: Riddle A, accepted_answers: [Alpha], tourist_info: Info A,
     task_picture: images/a.svg}
  - {id: b, name: Beta, task: Riddle B, accepted_answers: [Beta], tourist_info: Info B}
"""
GAMES = """
games:
  - {id: g, name: Game G, intro: Hi, time_zone: Europe/Sofia, max_duration_minutes: 240, tasks: [a, b]}
"""
TEAMS = """# keep this repo private
teams:
  - {id: t, name: Team T}
assignments:
  - team: t
    game: g
    valid_from: "2026-10-01T00:00:00"
    valid_until: "2026-10-31T23:59:59+02:00"
    exit_message: Bye
"""


def write_config(
    root: Path, *, landmarks: str = LANDMARKS, games: str = GAMES, teams: str = TEAMS
) -> Path:
    (root / "images").mkdir(parents=True, exist_ok=True)
    (root / "images" / "a.svg").write_bytes(SVG)
    for name, text in (("landmarks.yaml", landmarks), ("games.yaml", games), ("teams.yaml", teams)):
        (root / name).write_text(text, encoding="utf-8")
    return root


def sync(root: Path, session_factory, blob_store, reissue=None) -> dict:
    cfg = load_config(root)
    assert cfg.errors == []
    issued = issue_tokens(cfg, reissue)
    if issued:
        write_teams_file(cfg)
    with session_factory() as s:
        apply_config(
            s, blob_store, cfg, host_id="default", images_container="images",
            photos_container="photos",
        )
        s.commit()
    return issued


def test_validation_reports_all_problems(tmp_path):
    write_config(
        tmp_path,
        landmarks="""
landmarks:
  - {id: a, name: A, task: T, accepted_answers: [x], hint2: only-two, tourist_info: I}
  - {id: a, name: B, task: T, accepted_answers: ["!!"], tourist_info: I, task_picture: images/missing.png}
""",
        games="""
games:
  - {id: g, name: G, intro: I, time_zone: Mars/Base, max_duration_minutes: 60, tasks: [a, nope]}
""",
        teams="""
teams: [{id: t, name: T}]
assignments:
  - {team: t, game: g, valid_from: 2026-10-01T00:00:00, valid_until: "2026-10-02T00:00:00"}
""",
    )
    errors = load_config(tmp_path).errors
    text = "\n".join(errors)
    assert "hint2 is set but hint1 is empty" in text
    assert "empty after normalisation" in text
    assert "unknown time zone" in text
    assert "write the timestamp in quotes" in text


def test_coordinates_are_optional_and_validated(tmp_path):
    write_config(
        tmp_path,
        landmarks="""
landmarks:
  - {id: a, name: A, task: T, accepted_answers: [x], tourist_info: I,
     coordinates: {lat: 42.7, lon: 23.3}}
  - {id: b, name: B, task: T, accepted_answers: [y], tourist_info: I}
  - {id: c, name: C, task: T, accepted_answers: [z], tourist_info: I,
     coordinates: {lat: 99, lon: 200}}
""",
    )
    errors = [e for e in load_config(tmp_path).errors]
    flat = "\n".join(errors)
    assert "coordinates.lat" in flat
    assert "coordinates.lon" in flat


def test_coordinates_are_persisted(tmp_path, session_factory, blob_store):
    root = write_config(
        tmp_path,
        landmarks="""
landmarks:
  - {id: a, name: A, task: T, accepted_answers: [x], tourist_info: I,
     coordinates: {lat: 42.7, lon: 23.3}}
  - {id: b, name: B, task: T, accepted_answers: [y], tourist_info: I}
""",
    )
    sync(root, session_factory, blob_store)
    with session_factory() as s:
        a = s.scalars(select(Landmark).where(Landmark.key == "a")).one()
        b = s.scalars(select(Landmark).where(Landmark.key == "b")).one()
        assert a.coordinates_lat == 42.7
        assert a.coordinates_lon == 23.3
        assert b.coordinates_lat is None
        assert b.coordinates_lon is None


def test_cross_check_finds_duplicates_missing_images_and_bad_windows(tmp_path):
    write_config(
        tmp_path,
        landmarks="""
landmarks:
  - {id: a, name: A, task: T, accepted_answers: [x], tourist_info: I}
  - {id: a, name: B, task: T, accepted_answers: [y], tourist_info: I, task_picture: images/missing.png}
""",
        games="""
games:
  - {id: g, name: G, intro: I, time_zone: Europe/Sofia, max_duration_minutes: 60, tasks: [a, nope]}
""",
        teams="""
teams: [{id: t, name: T}, {id: u, name: t}]
assignments:
  - {team: t, game: g, valid_from: "2026-10-02T00:00:00", valid_until: "2026-10-01T00:00:00"}
  - {team: t, game: g, valid_from: "2026-10-01T00:00:00", valid_until: "2026-10-02T00:00:00"}
""",
    )
    text = "\n".join(load_config(tmp_path).errors)
    assert "duplicate landmark id 'a'" in text
    assert "duplicate team name" in text
    assert "picture not found: images/missing.png" in text
    assert "unknown landmark 'nope'" in text
    assert "valid_from must be before valid_until" in text
    assert "duplicate assignment 't/g'" in text


def test_missing_files_are_reported(tmp_path):
    errors = load_config(tmp_path).errors
    for name in ("landmarks", "games", "teams"):
        expected = f"{name}.yaml: file not found (looked in {(tmp_path / f'{name}.yaml').resolve()})"
        assert expected in errors


def test_tokens_written_back_and_comments_kept(tmp_path, session_factory, blob_store):
    write_config(tmp_path)                       # default teams.yaml starts with "# keep this repo private"
    cfg = load_config(tmp_path)
    issued = issue_tokens(cfg)
    write_teams_file(cfg)
    text = (tmp_path / "teams.yaml").read_text(encoding="utf-8")
    token = next(iter(issued.values()))
    assert f"token: {token}" in text and "# keep this repo private" in text
    assert "\n  - team: t\n    game: g\n" in text              # original indentation kept (small diff)
    assert not (tmp_path / "teams.yaml.tmp").exists()
    with session_factory() as s:
        apply_config(
            s, blob_store, cfg, host_id="default", images_container="images",
            photos_container="photos",
        )
        s.commit()
        a = s.scalars(select(Assignment)).one()
        assert a.token_hash == hash_token(token)
        assert a.valid_from.utcoffset() is not None or a.valid_from.tzinfo == UTC


def test_reissue_unknown_assignment_raises(tmp_path):
    write_config(tmp_path)
    cfg = load_config(tmp_path)
    with pytest.raises(ValueError, match="no assignment"):
        issue_tokens(cfg, ("t", "nope"))


def test_reissue_invalidates_old_token(tmp_path, session_factory, blob_store):
    root = write_config(tmp_path)
    old = next(iter(sync(root, session_factory, blob_store).values()))
    new = sync(root, session_factory, blob_store, reissue=("t", "g"))[("t", "g")]
    assert new != old and f"token: {new}" in (root / "teams.yaml").read_text(encoding="utf-8")
    with session_factory() as s:
        assert s.scalars(select(Assignment)).one().token_hash == hash_token(new)


def test_second_sync_is_idempotent_and_keeps_run_snapshot(
    tmp_path, session_factory, blob_store, clock
):
    root = write_config(tmp_path)
    sync(root, session_factory, blob_store)
    with session_factory() as s:
        start_run(s, s.scalars(select(Assignment)).one(), clock.now)
        s.commit()
    assert sync(root, session_factory, blob_store) == {}                    # no new tokens
    write_config(
        tmp_path,
        games=GAMES.replace("tasks: [a, b]", "tasks: [b]"),
        teams=(root / "teams.yaml").read_text(encoding="utf-8"),
    )
    sync(root, session_factory, blob_store)
    with session_factory() as s:
        assert [t.landmark.key for t in s.scalars(select(Game)).one().tasks] == ["b"]
        assert s.query(RunTask).count() == 2                                 # run kept its snapshot
        assert s.query(GameRun).count() == 1


def test_requestable_in_yaml_sets_the_flag_and_omission_preserves_it(
    tmp_path, session_factory, blob_store
):
    """D11: the YAML key is optional; leaving it out never overwrites a flag set in the panel."""
    root = write_config(tmp_path)
    sync(root, session_factory, blob_store)
    with session_factory() as s:
        assert s.scalars(select(Game)).one().requestable is False   # model default for new games

    with session_factory() as s:                                    # the admin panel turns it on
        s.scalars(select(Game)).one().requestable = True
        s.commit()
    sync(root, session_factory, blob_store)                         # YAML omits the key
    with session_factory() as s:
        assert s.scalars(select(Game)).one().requestable is True

    requestable_off = GAMES.replace("tasks: [a, b]", "tasks: [a, b], requestable: false")
    write_config(
        tmp_path,
        games=requestable_off,
        teams=(root / "teams.yaml").read_text(encoding="utf-8"),
    )
    sync(root, session_factory, blob_store)
    with session_factory() as s:
        assert s.scalars(select(Game)).one().requestable is False

    requestable_on = GAMES.replace("tasks: [a, b]", "tasks: [a, b], requestable: true")
    write_config(
        tmp_path,
        games=requestable_on,
        teams=(root / "teams.yaml").read_text(encoding="utf-8"),
    )
    sync(root, session_factory, blob_store)
    with session_factory() as s:
        assert s.scalars(select(Game)).one().requestable is True


def test_removed_assignment_is_deactivated(tmp_path, session_factory, blob_store):
    root = write_config(tmp_path)
    sync(root, session_factory, blob_store)
    write_config(tmp_path, teams="teams:\n  - {id: t, name: Team T}\nassignments: []\n")
    sync(root, session_factory, blob_store)
    with session_factory() as s:
        assert s.scalars(select(Assignment)).one().token_hash is None


def test_images_uploaded_once_under_content_hash(tmp_path, session_factory, blob_store):
    root = write_config(tmp_path)
    sync(root, session_factory, blob_store)
    sync(root, session_factory, blob_store)
    assert blob_store.get("images", hashlib.sha256(SVG).hexdigest() + ".svg") == (
        SVG,
        "image/svg+xml",
    )


def test_numeric_yaml_values_are_text(tmp_path):
    write_config(
        tmp_path,
        landmarks=LANDMARKS.replace("accepted_answers: [Beta]", "accepted_answers: [1879, Beta]"),
    )
    cfg = load_config(tmp_path)
    assert cfg.errors == [] and cfg.landmarks[1].accepted_answers == ["1879", "Beta"]


def test_cli_validate_only(tmp_path, monkeypatch, capsys):
    write_config(tmp_path)
    monkeypatch.chdir(tmp_path)  # main() calls load_dotenv(".env"): never load backend/.env here
    assert main(["--config-dir", str(tmp_path), "--validate-only"]) == 0
    assert "Configuration is valid." in capsys.readouterr().out


def test_cli_reports_errors_and_changes_nothing(tmp_path, monkeypatch, capsys):
    write_config(tmp_path, games="games: []\n")
    before = (tmp_path / "teams.yaml").read_text(encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert main(["--config-dir", str(tmp_path)]) == 1
    assert "problem(s) found; nothing was changed." in capsys.readouterr().err
    assert (tmp_path / "teams.yaml").read_text(encoding="utf-8") == before


def test_cli_full_run(tmp_path, monkeypatch, capsys):
    from sqlalchemy import create_engine

    root = write_config(tmp_path / "config")
    db = tmp_path / "db.sqlite"
    Base.metadata.create_all(create_engine(f"sqlite:///{db.as_posix()}"))
    monkeypatch.chdir(tmp_path)                      # no stray backend/.env is picked up
    for key, value in {
        "DATABASE_URL": f"sqlite:///{db.as_posix()}",
        "STORAGE_BACKEND": "local",
        "LOCAL_STORAGE_DIR": str(tmp_path / "blobs"),
        "PUBLIC_BASE_URL": "http://test",
    }.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    try:
        assert main(["--config-dir", str(root)]) == 0
        assert "http://test/play/" in capsys.readouterr().out
        assert main(["--config-dir", str(root)]) == 0
        assert "(new)" not in capsys.readouterr().out
    finally:
        get_settings.cache_clear()


SERVICE = """service:
  team: qa
  name: QA Service
"""
GAMES_GH = (
    GAMES
    + """  - {id: h, name: Game H, intro: Hi, time_zone: Europe/Sofia, max_duration_minutes: 60, tasks: [b]}
"""
)


def test_service_block_gets_one_link_per_game(tmp_path, session_factory, blob_store):
    root = write_config(tmp_path, games=GAMES_GH, teams=TEAMS + SERVICE)
    issued = sync(root, session_factory, blob_store)
    assert set(issued) == {("t", "g"), ("qa", "g"), ("qa", "h")}
    text = (root / "teams.yaml").read_text(encoding="utf-8")
    assert f"g: {issued[('qa', 'g')]}" in text and f"h: {issued[('qa', 'h')]}" in text
    assert "# keep this repo private" in text
    with session_factory() as s:
        team = s.scalars(select(Team).where(Team.key == "qa")).one()
        assert team.is_service is True and team.name == "QA Service"
        rows = s.scalars(select(Assignment).where(Assignment.team_id == team.id)).all()
        assert {r.token_hash for r in rows} == {
            hash_token(issued[("qa", "g")]),
            hash_token(issued[("qa", "h")]),
        }
        regular = s.scalars(select(Team).where(Team.key == "t")).one()
        assert regular.is_service is False
    assert sync(root, session_factory, blob_store) == {}  # idempotent: no new tokens


def test_new_game_gets_service_link_and_removed_game_deactivates_it(
    tmp_path, session_factory, blob_store
):
    root = write_config(tmp_path, teams=TEAMS + SERVICE)
    first = sync(root, session_factory, blob_store)
    assert set(first) == {("t", "g"), ("qa", "g")}
    (root / "games.yaml").write_text(GAMES_GH, encoding="utf-8")
    assert set(sync(root, session_factory, blob_store)) == {("qa", "h")}
    (root / "games.yaml").write_text(GAMES, encoding="utf-8")
    assert sync(root, session_factory, blob_store) == {}  # stale `h` token is not an error
    with session_factory() as s:
        h = s.scalars(select(Game).where(Game.key == "h")).one()
        row = s.scalars(select(Assignment).where(Assignment.game_id == h.id)).one()
        assert row.token_hash is None


def test_removing_service_block_deactivates_service_links(tmp_path, session_factory, blob_store):
    root = write_config(tmp_path, teams=TEAMS + SERVICE)
    sync(root, session_factory, blob_store)
    kept = (root / "teams.yaml").read_text(encoding="utf-8").split("service:")[0]
    (root / "teams.yaml").write_text(kept, encoding="utf-8")
    sync(root, session_factory, blob_store)
    with session_factory() as s:
        qa = s.scalars(select(Team).where(Team.key == "qa")).one()
        row = s.scalars(select(Assignment).where(Assignment.team_id == qa.id)).one()
        assert row.token_hash is None


def test_reissue_service_token(tmp_path, session_factory, blob_store):
    root = write_config(tmp_path, teams=TEAMS + SERVICE)
    old = sync(root, session_factory, blob_store)[("qa", "g")]
    new = sync(root, session_factory, blob_store, reissue=("qa", "g"))[("qa", "g")]
    assert new != old and f"g: {new}" in (root / "teams.yaml").read_text(encoding="utf-8")


def test_service_block_cross_checks(tmp_path):
    clash = """service:
  team: t
  name: team t
  tokens:
    g: TOKEN-0123456789abcdefghijklmn
"""
    teams = TEAMS.replace(
        "exit_message: Bye", "exit_message: Bye\n    token: TOKEN-0123456789abcdefghijklmn"
    )
    write_config(tmp_path, teams=teams + clash)
    errors = load_config(tmp_path).errors
    assert any("service team id 't'" in e for e in errors)
    assert any("service team name" in e for e in errors)
    assert any("duplicate token" in e for e in errors)


def test_service_block_validation_errors(tmp_path):
    write_config(tmp_path, teams=TEAMS + "service:\n  team: Not A Slug\n  name: ''\n")
    errors = load_config(tmp_path).errors
    assert any(e.startswith("teams.yaml: service team:") for e in errors)
    assert any(e.startswith("teams.yaml: service name:") for e in errors)


I18N_LANDMARKS = """
landmarks:
  - {id: c, name: Gamma, task: Riddle C, accepted_answers: [Gamma], hint1: Hint1 C, hint2: Hint2 C,
     tourist_info: Info C, name_i18n: {de: Gamma DE}, task_i18n: {de: Riddle C DE},
     hint1_i18n: {de: Hint1 C DE}, hint2_i18n: {de: Hint2 C DE},
     tourist_info_i18n: {de: Info C DE}}
"""


def test_landmark_i18n_maps_are_persisted_and_idempotent(tmp_path, session_factory, blob_store):
    root = write_config(
        tmp_path,
        landmarks=I18N_LANDMARKS,
        games="games: []\n",
        teams="teams: []\nassignments: []\n",
    )
    sync(root, session_factory, blob_store)
    with session_factory() as s:
        c = s.scalars(select(Landmark).where(Landmark.key == "c")).one()
        assert c.name_i18n == {"de": "Gamma DE"}
        assert c.task_text_i18n == {"de": "Riddle C DE"}
        assert c.hint1_i18n == {"de": "Hint1 C DE"}
        assert c.hint2_i18n == {"de": "Hint2 C DE"}
        assert c.info_text_i18n == {"de": "Info C DE"}
    sync(root, session_factory, blob_store)
    with session_factory() as s:
        c = s.scalars(select(Landmark).where(Landmark.key == "c")).one()
        assert c.name_i18n == {"de": "Gamma DE"}
        assert c.task_text_i18n == {"de": "Riddle C DE"}
        assert c.hint1_i18n == {"de": "Hint1 C DE"}
        assert c.hint2_i18n == {"de": "Hint2 C DE"}
        assert c.info_text_i18n == {"de": "Info C DE"}
