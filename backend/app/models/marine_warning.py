from datetime import datetime
from sqlalchemy import String, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from geoalchemy2 import Geometry

from backend.app.core.database import Base

class MarineWarning(Base):
    __tablename__ = "marine_warnings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    warning_type: Mapped[str] = mapped_column(String(255), nullable=False)
    severity: Mapped[str] = mapped_column(String(100), nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)
    geom: Mapped[str] = mapped_column(Geometry(geometry_type='GEOMETRY', srid=4326), nullable=False)
    
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    dataset_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    spatial_resolution: Mapped[str | None] = mapped_column(String(100), nullable=True)
    temporal_resolution: Mapped[str | None] = mapped_column(String(100), nullable=True)
    data_quality_status: Mapped[str] = mapped_column(String(50), nullable=False, default="VALID")
    is_stale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
