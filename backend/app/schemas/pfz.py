from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field

class PFZLocation(BaseModel):
    landing_centre: str
    direction: str
    bearing_degrees: int
    distance_km: str
    depth_min_m: Optional[int] = None
    depth_max_m: Optional[int] = None
    latitude: float
    longitude: float

    class Config:
        from_attributes = True

class PFZLatestResponse(BaseModel):
    source: str = "INCOIS"
    source_type: str = "OFFICIAL_PFZ_ADVISORY"
    sector: str = "Maharashtra"
    status: str
    advisory_date: Optional[datetime] = None
    validity_date: Optional[datetime] = None
    retrieved_at: datetime
    count: int = 0
    locations: List[PFZLocation] = Field(default_factory=list)
    error: Optional[str] = None
