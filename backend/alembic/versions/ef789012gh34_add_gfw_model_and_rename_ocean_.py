"""Add GFW model, rename OceanObservation source_publication_time

Revision ID: ef789012gh34
Revises: abcd1234ef56
Create Date: 2026-09-07 02:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ef789012gh34'
down_revision: Union[str, None] = 'abcd1234ef56'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Rename column in ocean_observations
    op.alter_column(
        'ocean_observations', 'source_timestamp',
        new_column_name='source_publication_time',
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
        comment="The time the forecast/analysis was published/initialized. Used to prevent leakage."
    )

    # 2. Create gfw_fishing_effort table
    op.create_table(
        'gfw_fishing_effort',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('grid_cell_id', sa.String(length=100), nullable=True),
        sa.Column('latitude', sa.Float(), nullable=False),
        sa.Column('longitude', sa.Float(), nullable=False),
        sa.Column('observation_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('retrieved_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('fishing_hours', sa.Float(), nullable=False),
        sa.Column('vessel_type', sa.String(length=100), nullable=True),
        sa.Column('geartype', sa.String(length=100), nullable=True),
        sa.Column('flag', sa.String(length=10), nullable=True),
        sa.Column('hash_id', sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('hash_id')
    )
    op.create_index(op.f('ix_gfw_fishing_effort_grid_cell_id'), 'gfw_fishing_effort', ['grid_cell_id'], unique=False)
    op.create_index(op.f('ix_gfw_fishing_effort_observation_date'), 'gfw_fishing_effort', ['observation_date'], unique=False)


def downgrade() -> None:
    # 1. Drop gfw_fishing_effort table
    op.drop_index(op.f('ix_gfw_fishing_effort_observation_date'), table_name='gfw_fishing_effort')
    op.drop_index(op.f('ix_gfw_fishing_effort_grid_cell_id'), table_name='gfw_fishing_effort')
    op.drop_table('gfw_fishing_effort')

    # 2. Rename column back
    op.alter_column(
        'ocean_observations', 'source_publication_time',
        new_column_name='source_timestamp',
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
        comment=None
    )
