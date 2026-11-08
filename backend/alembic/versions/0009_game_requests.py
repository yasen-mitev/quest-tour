"""game_requests and games.requestable: the website's game play request form (issue #61)"""
import sqlalchemy as sa

from alembic import op

revision = "0009"
down_revision = "0008"


def upgrade() -> None:
    op.add_column(
        "games",
        sa.Column("requestable", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "game_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("host_id", sa.String(length=64), nullable=False),
        sa.Column("game_id", sa.Integer(), sa.ForeignKey("games.id", ondelete="SET NULL")),
        sa.Column("play_date", sa.Date(), nullable=False),
        sa.Column("teams", sa.JSON(), nullable=False),
        sa.Column("contact_name", sa.String(length=200), nullable=False),
        sa.Column("contact_email", sa.String(length=254)),
        sa.Column("contact_phone", sa.String(length=32)),
        sa.Column("message", sa.Text()),
        sa.Column("exit_message", sa.Text()),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("terms_accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("terms_version", sa.String(length=64), nullable=False),
        sa.Column("challenge", sa.String(length=64), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("decided_by", sa.String(length=254)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("challenge", name="uq_game_requests_challenge"),
    )
    op.create_index("ix_game_requests_host_status", "game_requests", ["host_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_game_requests_host_status", table_name="game_requests")
    op.drop_table("game_requests")
    with op.batch_alter_table("games") as batch:
        batch.drop_column("requestable")
