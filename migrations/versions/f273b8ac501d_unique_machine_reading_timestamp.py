"""unique machine reading timestamp

Revision ID: f273b8ac501d
Revises: d8a4c7319f02
"""

from alembic import op


revision = "f273b8ac501d"
down_revision = "d8a4c7319f02"
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint(
        "uq_machine_reading_time", "machine_readings", ["machine_id", "recorded_at"]
    )


def downgrade():
    op.drop_constraint("uq_machine_reading_time", "machine_readings", type_="unique")
