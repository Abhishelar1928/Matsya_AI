from datetime import date, datetime
from sqlalchemy import String, Float, DateTime, Date, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from geoalchemy2 import Geometry

from backend.app.core.database import Base

class PFZZone(Base):
    __tablename__ = "pfz_zones"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    geom: Mapped[str] = mapped_column(Geometry(geometry_type='GEOMETRY', srid=4326), nullable=False)
    depth: Mapped[float | None] = mapped_column(Float, nullable=True)
    
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    dataset_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    spatial_resolution: Mapped[str | None] = mapped_column(String(100), nullable=True)
    temporal_resolution: Mapped[str | None] = mapped_column(String(100), nullable=True)
    data_quality_status: Mapped[str] = mapped_column(String(50), nullable=False, default="VALID")
    is_stale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
