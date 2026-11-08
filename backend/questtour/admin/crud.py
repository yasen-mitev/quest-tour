from datetime import UTC, datetime

from fastapi import Request
from sqlalchemy.exc import IntegrityError

from questtour.admin.errors import AdminValidationError, ConflictError, FieldError
from questtour.admin.schemas import TokenReveal
from questtour.models import Assignment
from questtour.tokens import generate_token, hash_token


def get_admin_host_id(request: Request) -> str:
    return request.app.state.settings.host_id


def issue_token(assignment: Assignment, public_base_url: str, now: datetime) -> TokenReveal:
    """Give a flushed assignment a new token; only its hash is stored, the reveal shows it once."""
    token = generate_token()
    assignment.token_hash = hash_token(token)
    assignment.issued_at = now
    return TokenReveal(
        assignment_id=assignment.id,
        token=token,
        url=f"{public_base_url.rstrip('/')}/play/{token}",
    )


def _ts_iso(dt: datetime) -> str:
    """Compare at second precision so JSON round-tripping does not create false conflicts."""
    return dt.astimezone(UTC).replace(microsecond=0).isoformat()


def require_fresh(obj, seen_at: datetime | None) -> None:
    """Reject write if the entity has been updated since the client read it."""
    if seen_at is None:
        return
    if _ts_iso(obj.updated_at) != _ts_iso(seen_at):
        raise ConflictError(
            entity=obj.__class__.__name__,
            current={"id": obj.id, "updated_at": obj.updated_at},
        )


def _sqlite_columns(msg: str) -> list[str]:
    if "unique constraint failed:" not in msg.lower():
        return []
    cols_part = msg.lower().split("unique constraint failed:", 1)[1]
    return [c.strip() for c in cols_part.replace(" ", "").split(",") if c.strip()]


def _is_unique_conflict(orig_msg: str, field_map: dict[str, str]) -> FieldError | None:
    """Map SQLite/Postgres unique-violation messages to field errors.

    SQLite: UNIQUE constraint failed: table.col1, table.col2
    Postgres: duplicate key value violates unique constraint "uq_name" DETAIL: Key (col1, col2)=(...) already exists.
    """
    lower = orig_msg.lower()
    # SQLite: map by column names.
    for table_col in _sqlite_columns(orig_msg):
        col_name = table_col.rsplit(".", 1)[-1]
        if col_name in field_map:
            return FieldError(field=field_map[col_name], message=f"{col_name} already exists")
    # Postgres: map by constraint name. The v5 substring fallback is removed because
    # "uq_teams_host_name" contains "key" and would map a duplicate name to the key field.
    constraint_to_field = {
        "uq_landmarks_host_key": "key",
        "uq_games_host_key": "key",
        "uq_teams_host_key": "key",
        "uq_teams_host_name": "name",
        "uq_assignments_team_game": "game",
        "uq_game_requests_challenge": "altcha",
    }
    for constraint, field in constraint_to_field.items():
        if constraint in lower:
            return FieldError(field=field, message=f"{field} already exists")
    return None


def handle_integrity(error: IntegrityError, field_map: dict[str, str]) -> AdminValidationError:
    """Map a SQLAlchemy IntegrityError to a structured field error where possible."""
    msg = str(error.orig) if error.orig else str(error)
    field_err = _is_unique_conflict(msg, field_map)
    if field_err:
        return AdminValidationError([field_err])
    return AdminValidationError([FieldError(field="", message="database constraint failed")])
