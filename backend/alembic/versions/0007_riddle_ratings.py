"""riddle_ratings and run_feedback: stars per riddle and a word for the host (issue #38)"""
import sqlalchemy as sa

from alembic import op

revision = "0007"
down_revision = "0006"


def upgrade() -> None:
    op.create_table(
        "riddle_ratings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "run_task_id",
            sa.Integer(),
            sa.ForeignKey("run_tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("stars", sa.Integer(), nullable=False),
        sa.Column("rated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_task_id", "device_id", name="uq_riddle_ratings_task_device"),
    )
    op.create_table(
        "run_feedback",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "run_id", sa.Integer(), sa.ForeignKey("game_runs.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "device_id", name="uq_run_feedback_run_device"),
    )


def downgrade() -> None:
    op.drop_table("run_feedback")
    op.drop_table("riddle_ratings")
