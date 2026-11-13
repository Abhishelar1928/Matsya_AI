from datetime import datetime, timezone
from sqlalchemy import String, Float, DateTime, Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column
from geoalchemy2 import Geometry

from backend.app.core.database import Base

class Prediction(Base):
    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    prediction_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    geom: Mapped[str] = mapped_column(Geometry(geometry_type='POINT', srid=4326), nullable=False)
    
    # ML Prediction outputs
    prediction_probability: Mapped[float] = mapped_column(Float, nullable=False)
    prediction_class: Mapped[int] = mapped_column(Integer, nullable=False)
    prediction_label: Mapped[str] = mapped_column(String(200), nullable=False)
    
    # Model Metadata
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    model_trained_at: Mapped[str] = mapped_column(String(100), nullable=False)
    
    # Environmental Data Tracking
    env_observation_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    env_source: Mapped[str] = mapped_column(String(100), nullable=False)
    data_freshness_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    
    # Safety Data
    safety_status: Mapped[str] = mapped_column(String(100), nullable=False)
    safety_override: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    pfz_advisory: Mapped[str | None] = mapped_column(String, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
