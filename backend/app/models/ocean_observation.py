from datetime import datetime
from sqlalchemy import String, Float, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from geoalchemy2 import Geometry

from backend.app.core.database import Base

class OceanObservation(Base):
    __tablename__ = "ocean_observations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="The observation/valid time of the data")
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    geom: Mapped[str] = mapped_column(Geometry(geometry_type='POINT', srid=4326), nullable=False)
    
    sst: Mapped[float | None] = mapped_column(Float, nullable=True)
    sst_anomaly: Mapped[float | None] = mapped_column(Float, nullable=True)
    chlorophyll: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_speed: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_direction: Mapped[float | None] = mapped_column(Float, nullable=True)
    wave_height: Mapped[float | None] = mapped_column(Float, nullable=True)
    wave_period: Mapped[float | None] = mapped_column(Float, nullable=True)
    swell_height: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_speed: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_direction: Mapped[float | None] = mapped_column(Float, nullable=True)
    
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    dataset_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_publication_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="The time the forecast/analysis was published/initialized. Used to prevent leakage.")
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="The exact time Matsya AI downloaded this record.")
    spatial_resolution: Mapped[str | None] = mapped_column(String(100), nullable=True)
    temporal_resolution: Mapped[str | None] = mapped_column(String(100), nullable=True)
    data_quality_status: Mapped[str] = mapped_column(String(50), nullable=False, default="VALID")
    is_stale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
