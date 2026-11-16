"""
MatsyaAI Maharashtra — Offline Expedition Mode models.

Records are created on the device while offline and synced later, so every
device-originated row carries a client-generated UUID (``client_uuid``) that
makes sync idempotent: re-sending the same record never creates a duplicate.
"""

from datetime import datetime, timezone

from geoalchemy2 import Geometry
from sqlalchemy import DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Expedition(Base):
    __tablename__ = "expeditions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # package UUID
    device_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    landing_centre_id: Mapped[str] = mapped_column(String(64), nullable=False)
    destination_latitude: Mapped[float] = mapped_column(Float, nullable=False)
    destination_longitude: Mapped[float] = mapped_column(Float, nullable=False)
    destination_geom: Mapped[str] = mapped_column(Geometry("POINT", srid=4326), nullable=False)
    package_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    package_valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    planned_departure: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    planned_return: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ExpeditionTrackPoint(Base):
    __tablename__ = "expedition_track_points"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    client_uuid: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    expedition_id: Mapped[str] = mapped_column(String(36), ForeignKey("expeditions.id"), nullable=False, index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    geom: Mapped[str] = mapped_column(Geometry("POINT", srid=4326), nullable=False)
    speed_mps: Mapped[float | None] = mapped_column(Float, nullable=True)
    heading_deg: Mapped[float | None] = mapped_column(Float, nullable=True)
    accuracy_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class CatchRecord(Base):
    __tablename__ = "catch_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    client_uuid: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    expedition_id: Mapped[str] = mapped_column(String(36), ForeignKey("expeditions.id"), nullable=False, index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    geom: Mapped[str | None] = mapped_column(Geometry("POINT", srid=4326), nullable=True)
    species: Mapped[str] = mapped_column(String(100), nullable=False)
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class FieldObservation(Base):
    __tablename__ = "field_observations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    client_uuid: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    expedition_id: Mapped[str] = mapped_column(String(36), ForeignKey("expeditions.id"), nullable=False, index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    geom: Mapped[str | None] = mapped_column(Geometry("POINT", srid=4326), nullable=True)
    observation_type: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g. sea_state, bird_activity
    value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
