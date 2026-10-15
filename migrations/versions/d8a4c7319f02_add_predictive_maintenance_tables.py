"""add predictive maintenance tables

Revision ID: d8a4c7319f02
Revises: c41f6d2e85b7
"""

from alembic import op
import sqlalchemy as sa


revision = "d8a4c7319f02"
down_revision = "c41f6d2e85b7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "machines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=140), nullable=False),
        sa.Column("machine_type", sa.String(length=100), nullable=False),
        sa.Column("area", sa.String(length=100), nullable=False),
        sa.Column("max_usage_hours", sa.Float(), nullable=False),
        sa.Column("max_vibration", sa.Float(), nullable=False),
        sa.Column("max_temperature", sa.Float(), nullable=False),
        sa.Column("rated_current", sa.Float(), nullable=False),
        sa.Column("nominal_rpm", sa.Float(), nullable=False),
        sa.Column("max_pressure", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_machines_code", "machines", ["code"], unique=True)
    op.create_table(
        "machine_readings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("machine_id", sa.Integer(), sa.ForeignKey("machines.id", ondelete="CASCADE"), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("usage_hours", sa.Float(), nullable=False),
        sa.Column("vibration", sa.Float(), nullable=False),
        sa.Column("temperature", sa.Float(), nullable=False),
        sa.Column("current", sa.Float(), nullable=False),
        sa.Column("rpm", sa.Float(), nullable=False),
        sa.Column("pressure", sa.Float(), nullable=False),
        sa.Column("failure_probability", sa.Float(), nullable=False),
        sa.Column("health_status", sa.String(length=20), nullable=False),
        sa.Column("explanation", sa.String(length=500), nullable=False),
    )
    op.create_index("ix_machine_readings_machine_id", "machine_readings", ["machine_id"])
    op.create_index("ix_machine_readings_recorded_at", "machine_readings", ["recorded_at"])
    op.create_index("ix_machine_readings_health_status", "machine_readings", ["health_status"])


def downgrade():
    op.drop_table("machine_readings")
    op.drop_table("machines")
