"""upgrade expedition track and catch tables to v2

Revision ID: f8b2d1c3e4a5
Revises: e7a1c0ffee01
Create Date: 2026-11-24 02:55:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f8b2d1c3e4a5"
down_revision: Union[str, None] = "e7a1c0ffee01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("expedition_track_points", sa.Column("cog_deg", sa.Float(), nullable=True))
    op.add_column("expedition_track_points", sa.Column("compass_heading_deg", sa.Float(), nullable=True))
    op.add_column("expedition_track_points", sa.Column("xte_km", sa.Float(), nullable=True))

    op.add_column("catch_records", sa.Column("species_id", sa.String(64), nullable=True))
    op.add_column("catch_records", sa.Column("quantity", sa.Integer(), nullable=True))
    op.add_column("catch_records", sa.Column("fishing_duration_min", sa.Integer(), nullable=True))
    op.add_column("catch_records", sa.Column("estimated_value_inr", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("catch_records", "estimated_value_inr")
    op.drop_column("catch_records", "fishing_duration_min")
    op.drop_column("catch_records", "quantity")
    op.drop_column("catch_records", "species_id")

    op.drop_column("expedition_track_points", "xte_km")
    op.drop_column("expedition_track_points", "compass_heading_deg")
    op.drop_column("expedition_track_points", "cog_deg")
