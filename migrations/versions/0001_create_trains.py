"""Create the trains table: one seat count per carriage.

Revision ID: 0001
Revises:
Create Date: 2026-10-17

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

trains = sa.table("trains", sa.column("gerbong", sa.Integer), sa.column("jumlah_seat", sa.Integer))


def upgrade() -> None:
    op.create_table(
        "trains",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("gerbong", sa.Integer(), nullable=False, unique=True),
        sa.Column("jumlah_seat", sa.Integer(), nullable=False),
    )
    # Starting rows so the board shows something on a fresh database. Adjust per station.
    op.bulk_insert(trains, [{"gerbong": g, "jumlah_seat": 25} for g in (1, 2, 3)])


def downgrade() -> None:
    op.drop_table("trains")
