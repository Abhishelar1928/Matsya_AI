from datetime import datetime
from typing import Optional
from sqlalchemy import String, Float, DateTime, Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column
from geoalchemy2 import Geometry

from backend.app.core.database import Base

class INCOISPFZAdvisory(Base):
    __tablename__ = "incois_pfz_advisories"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="INCOIS")
    source_type: Mapped[str] = mapped_column(String(50), nullable=False, default="OFFICIAL_PFZ_ADVISORY")
    sector: Mapped[str] = mapped_column(String(50), nullable=False, default="Maharashtra")
    
    landing_centre: Mapped[str] = mapped_column(String(100), nullable=False)
    direction: Mapped[str] = mapped_column(String(20), nullable=False)
    bearing_degrees: Mapped[int] = mapped_column(Integer, nullable=False)
    distance_km: Mapped[str] = mapped_column(String(50), nullable=False)
    depth_min_m: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    depth_max_m: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    geom: Mapped[str] = mapped_column(Geometry(geometry_type='POINT', srid=4326), nullable=False)
    
    advisory_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    validity_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_url: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # Hash of coordinates, date, etc to avoid duplicate ingestion
    hash_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
