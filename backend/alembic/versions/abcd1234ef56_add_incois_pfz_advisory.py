"""add incois pfz advisory

Revision ID: abcd1234ef56
Revises: c75009cfc94b
Create Date: 2026-09-07 01:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geometry

# revision identifiers, used by Alembic.
revision = 'abcd1234ef56'
down_revision = 'c75009cfc94b'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        'incois_pfz_advisories',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('source', sa.String(length=50), nullable=False),
        sa.Column('source_type', sa.String(length=50), nullable=False),
        sa.Column('sector', sa.String(length=50), nullable=False),
        sa.Column('landing_centre', sa.String(length=100), nullable=False),
        sa.Column('direction', sa.String(length=20), nullable=False),
        sa.Column('bearing_degrees', sa.Integer(), nullable=False),
        sa.Column('distance_km', sa.String(length=50), nullable=False),
        sa.Column('depth_min_m', sa.Integer(), nullable=True),
        sa.Column('depth_max_m', sa.Integer(), nullable=True),
        sa.Column('latitude', sa.Float(), nullable=False),
        sa.Column('longitude', sa.Float(), nullable=False),
        sa.Column('geom', Geometry(geometry_type='POINT', srid=4326, from_text='ST_GeomFromEWKT', name='geometry'), nullable=False),
        sa.Column('advisory_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('validity_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('retrieved_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('source_url', sa.String(length=255), nullable=False),
        sa.Column('hash_id', sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_incois_pfz_advisories_hash_id'), 'incois_pfz_advisories', ['hash_id'], unique=True)

def downgrade() -> None:
    op.drop_index(op.f('ix_incois_pfz_advisories_hash_id'), table_name='incois_pfz_advisories')
    op.drop_table('incois_pfz_advisories')
