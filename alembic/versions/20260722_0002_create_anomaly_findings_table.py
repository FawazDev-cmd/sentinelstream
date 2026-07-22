"""Create anomaly findings table.

Revision ID: 20260722_0002
Revises: 20260722_0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260722_0002"
down_revision: str | None = "20260722_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "anomaly_findings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("anomaly_type", sa.String(length=50), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("rule_id", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["event_id"], ["log_events.event_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "event_id", "rule_id", name="uq_anomaly_findings_event_rule"
        ),
    )
    op.create_index(
        "ix_anomaly_findings_event_id", "anomaly_findings", ["event_id"], unique=False
    )
    op.create_index(
        "ix_anomaly_findings_severity", "anomaly_findings", ["severity"], unique=False
    )
    op.create_index(
        "ix_anomaly_findings_anomaly_type",
        "anomaly_findings",
        ["anomaly_type"],
        unique=False,
    )
    op.create_index(
        "ix_anomaly_findings_created_at",
        "anomaly_findings",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_anomaly_findings_created_at", table_name="anomaly_findings")
    op.drop_index("ix_anomaly_findings_anomaly_type", table_name="anomaly_findings")
    op.drop_index("ix_anomaly_findings_severity", table_name="anomaly_findings")
    op.drop_index("ix_anomaly_findings_event_id", table_name="anomaly_findings")
    op.drop_table("anomaly_findings")
