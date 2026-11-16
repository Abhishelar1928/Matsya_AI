"""add offline expedition tables

Revision ID: e7a1c0ffee01
Revises: 8596d05bae1b
Create Date: 2026-11-16 00:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import geoalchemy2

revision: str = "e7a1c0ffee01"
down_revision: Union[str, None] = "8596d05bae1b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _point(nullable: bool) -> sa.Column:
    return sa.Column(
        "geom",
        geoalchemy2.types.Geometry(geometry_type="POINT", srid=4326, from_text="ST_GeomFromEWKT", name="geometry"),
        nullable=nullable,
    )


def upgrade() -> None:
    op.create_table(
        "expeditions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("device_id", sa.String(64), nullable=False),
        sa.Column("landing_centre_id", sa.String(64), nullable=False),
        sa.Column("destination_latitude", sa.Float(), nullable=False),
        sa.Column("destination_longitude", sa.Float(), nullable=False),
        sa.Column(
            "destination_geom",
            geoalchemy2.types.Geometry(geometry_type="POINT", srid=4326, from_text="ST_GeomFromEWKT", name="geometry"),
            nullable=False,
        ),
        sa.Column("package_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("package_valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("planned_departure", sa.DateTime(timezone=True), nullable=True),
        sa.Column("planned_return", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_expeditions_device_id", "expeditions", ["device_id"])

    op.create_table(
        "expedition_track_points",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("client_uuid", sa.String(36), nullable=False, unique=True),
        sa.Column("expedition_id", sa.String(36), sa.ForeignKey("expeditions.id"), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        _point(nullable=False),
        sa.Column("speed_mps", sa.Float(), nullable=True),
        sa.Column("heading_deg", sa.Float(), nullable=True),
        sa.Column("accuracy_m", sa.Float(), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_expedition_track_points_expedition_id", "expedition_track_points", ["expedition_id"])

    op.create_table(
        "catch_records",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("client_uuid", sa.String(36), nullable=False, unique=True),
        sa.Column("expedition_id", sa.String(36), sa.ForeignKey("expeditions.id"), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        _point(nullable=True),
        sa.Column("species", sa.String(100), nullable=False),
        sa.Column("weight_kg", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_catch_records_expedition_id", "catch_records", ["expedition_id"])

    op.create_table(
        "field_observations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("client_uuid", sa.String(36), nullable=False, unique=True),
        sa.Column("expedition_id", sa.String(36), sa.ForeignKey("expeditions.id"), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        _point(nullable=True),
        sa.Column("observation_type", sa.String(50), nullable=False),
        sa.Column("value", sa.String(255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_field_observations_expedition_id", "field_observations", ["expedition_id"])


def downgrade() -> None:
    op.drop_table("field_observations")
    op.drop_table("catch_records")
    op.drop_table("expedition_track_points")
    op.drop_index("ix_expeditions_device_id", table_name="expeditions")
    op.drop_table("expeditions")
