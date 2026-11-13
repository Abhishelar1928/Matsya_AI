from datetime import datetime, timezone
from sqlalchemy import String, Float, DateTime, Enum, Column
from sqlalchemy.orm import Mapped, mapped_column
from geoalchemy2 import Geometry
import enum

from backend.app.core.database import Base

class DistrictEnum(str, enum.Enum):
    PALGHAR = "Palghar"
    MUMBAI = "Mumbai"
    RAIGAD = "Raigad"
    RATNAGIRI = "Ratnagiri"
    SINDHUDURG = "Sindhudurg"

class LandingCentre(Base):
    __tablename__ = "landing_centres"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    district: Mapped[DistrictEnum] = mapped_column(Enum(DistrictEnum), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    geom: Mapped[str] = mapped_column(Geometry(geometry_type='POINT', srid=4326), nullable=False)
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
