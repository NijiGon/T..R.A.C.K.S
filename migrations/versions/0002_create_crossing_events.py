"""Create the crossing_events table: one row per counted crossing, keyed by the car's event UUID.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-18

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "crossing_events",
        sa.Column("event_id", sa.String(36), primary_key=True),
        sa.Column("car_id", sa.String(64), nullable=False),
        sa.Column("door", sa.String(64), nullable=False),
        sa.Column("occurred_at", sa.Float(), nullable=False),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("seat_delta", sa.Integer(), nullable=False),
        sa.Column("received_at", sa.Float(), nullable=False),
    )
    op.create_index("ix_crossing_events_car_id", "crossing_events", ["car_id"])


def downgrade() -> None:
    op.drop_index("ix_crossing_events_car_id", table_name="crossing_events")
    op.drop_table("crossing_events")
