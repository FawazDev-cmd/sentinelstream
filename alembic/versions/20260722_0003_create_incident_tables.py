"""Create incident persistence tables.

Revision ID: 20260722_0003
Revises: 20260722_0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260722_0003"
down_revision: str | None = "20260722_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "incidents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service", sa.String(length=100), nullable=False),
        sa.Column("environment", sa.String(length=50), nullable=False),
        sa.Column("anomaly_type", sa.String(length=50), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finding_count", sa.Integer(), nullable=False),
        sa.Column("highest_severity", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("finding_count >= 2", name="ck_incidents_finding_count"),
        sa.CheckConstraint(
            "started_at <= last_seen_at", name="ck_incidents_occurrence_range"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "started_at",
        "last_seen_at",
        "highest_severity",
        "service",
        "environment",
        "anomaly_type",
    ):
        op.create_index(f"ix_incidents_{column}", "incidents", [column], unique=False)
    op.create_table(
        "incident_findings",
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("finding_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("position >= 0", name="ck_incident_findings_position"),
        sa.ForeignKeyConstraint(
            ["finding_id"], ["anomaly_findings.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("incident_id", "finding_id"),
        sa.UniqueConstraint("finding_id", name="uq_incident_findings_finding"),
        sa.UniqueConstraint(
            "incident_id", "position", name="uq_incident_findings_incident_position"
        ),
    )


def downgrade() -> None:
    op.drop_table("incident_findings")
    for column in (
        "anomaly_type",
        "environment",
        "service",
        "highest_severity",
        "last_seen_at",
        "started_at",
    ):
        op.drop_index(f"ix_incidents_{column}", table_name="incidents")
    op.drop_table("incidents")
