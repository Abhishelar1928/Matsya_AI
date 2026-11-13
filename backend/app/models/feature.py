from datetime import datetime
from sqlalchemy import String, Float, DateTime, Boolean, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from geoalchemy2 import Geometry

from backend.app.core.database import Base

class SpatialGrid(Base):
    """
    Configurable spatial grid cells for the Maharashtra Fishing Region.
    """
    __tablename__ = "spatial_grids"

    id: Mapped[str] = mapped_column(String(100), primary_key=True) # e.g. "cell_19.0_72.8"
    resolution: Mapped[float] = mapped_column(Float, nullable=False) # e.g. 0.25
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    geom: Mapped[str] = mapped_column(Geometry(geometry_type='POLYGON', srid=4326), nullable=False)
    centroid: Mapped[str] = mapped_column(Geometry(geometry_type='POINT', srid=4326), nullable=False)
    distance_to_coast_km: Mapped[float | None] = mapped_column(Float, nullable=True)

class ModelFeature(Base):
    """
    Aggregated and engineered feature vectors ready for ML prediction.
    """
    __tablename__ = "model_features"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    grid_cell_id: Mapped[str] = mapped_column(String(100), ForeignKey("spatial_grids.id"), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    
    # Environmental Features
    wave_height: Mapped[float | None] = mapped_column(Float, nullable=True)
    wave_period: Mapped[float | None] = mapped_column(Float, nullable=True)
    wave_direction: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_speed: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_direction: Mapped[float | None] = mapped_column(Float, nullable=True)
    sst: Mapped[float | None] = mapped_column(Float, nullable=True)
    
    # Temporal Features
    hour: Mapped[int] = mapped_column(Integer, nullable=False)
    day_of_year: Mapped[int] = mapped_column(Integer, nullable=False)
    season: Mapped[str] = mapped_column(String(50), nullable=False)
    
    # Validation & Provenance
    is_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    provenance: Mapped[str] = mapped_column(String(255), nullable=False) # e.g. "OPEN_METEO_MODEL"
    imputation_flags: Mapped[str | None] = mapped_column(String(255), nullable=True) # e.g. "sst_forward_filled"
    
    # Relationships
    grid_cell: Mapped[SpatialGrid] = relationship("SpatialGrid")
