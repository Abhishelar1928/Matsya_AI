from datetime import datetime
from sqlalchemy import String, Float, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base

class GFWFishingEffort(Base):
    """
    Stores apparent fishing effort aggregated from Global Fishing Watch (GFW).
    Data represents fishing activity in a grid cell over a calendar day.
    """
    __tablename__ = "gfw_fishing_effort"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    
    # Spatial binding
    grid_cell_id: Mapped[str] = mapped_column(String(100), nullable=True, index=True) 
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    
    # Temporal binding (observation_date is the date the fishing occurred)
    observation_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    
    # Provenance / Availability boundary
    # GFW 4Wings API DOES NOT currently expose a per-record 'published_at' timestamp.
    # Therefore, we cannot perfectly reconstruct historical availability using GFW metadata alone.
    # `retrieved_at` is purely the timestamp when Matsya AI downloaded this record.
    # It does NOT definitively prove the data was available exactly at time T historically.
    # To prevent temporal leakage during ML backtesting, a conservative availability-aware policy
    # (e.g., enforcing a strict minimum lag of 4 days) MUST be applied in the feature builder.
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    
    # Effort values
    fishing_hours: Mapped[float] = mapped_column(Float, nullable=False)
    
    # Metadata
    vessel_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    geartype: Mapped[str | None] = mapped_column(String(100), nullable=True)
    flag: Mapped[str | None] = mapped_column(String(10), nullable=True)
    
    # We can compute a unique hash (lat, lon, date, gear, flag) to ensure deduplication
    hash_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
