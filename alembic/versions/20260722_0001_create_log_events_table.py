"""Create log events table.

Revision ID: 20260722_0001
Revises: None
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260722_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "log_events",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("service", sa.String(length=100), nullable=False),
        sa.Column("environment", sa.String(length=50), nullable=False),
        sa.Column("level", sa.String(length=8), nullable=False),
        sa.Column("message", sa.String(length=4000), nullable=False),
        sa.Column("exception_type", sa.String(length=250), nullable=True),
        sa.Column("exception_message", sa.String(length=2000), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("trace_id", sa.String(length=128), nullable=True),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("host", sa.String(length=255), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index(
        "ix_log_events_timestamp", "log_events", ["timestamp"], unique=False
    )
    op.create_index(
        "ix_log_events_received_at", "log_events", ["received_at"], unique=False
    )
    op.create_index("ix_log_events_service", "log_events", ["service"], unique=False)
    op.create_index(
        "ix_log_events_environment", "log_events", ["environment"], unique=False
    )
    op.create_index("ix_log_events_level", "log_events", ["level"], unique=False)
    op.create_index(
        "ix_log_events_service_timestamp",
        "log_events",
        ["service", "timestamp"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_log_events_service_timestamp", table_name="log_events")
    op.drop_index("ix_log_events_level", table_name="log_events")
    op.drop_index("ix_log_events_environment", table_name="log_events")
    op.drop_index("ix_log_events_service", table_name="log_events")
    op.drop_index("ix_log_events_received_at", table_name="log_events")
    op.drop_index("ix_log_events_timestamp", table_name="log_events")
    op.drop_table("log_events")
