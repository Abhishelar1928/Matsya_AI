import math
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple
from sqlalchemy import select, insert, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.feature import SpatialGrid, ModelFeature
from backend.app.models.ocean_observation import OceanObservation
from backend.app.models.landing_centre import LandingCentre

logger = logging.getLogger(__name__)

def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great circle distance in kilometers between two points on the earth."""
    R = 6371.0 # Earth radius in kilometers
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def get_season(dt: datetime) -> str:
    month = dt.month
    if 6 <= month <= 9:
        return "Monsoon"
    elif 10 <= month <= 12 or month <= 2:
        return "Post-Monsoon/Winter"
    else:
        return "Pre-Monsoon/Summer"

class FeatureEngineeringPipeline:
    def __init__(self, session: AsyncSession, resolution: float = 0.25):
        self.session = session
        self.resolution = resolution
        # Configurable Maharashtra Fishing Region Bounds
        self.min_lat = 15.5
        self.max_lat = 20.2
        self.min_lon = 72.0
        self.max_lon = 74.0
        self.max_imputation_distance_km = 50.0

    async def _ensure_grid_exists(self) -> List[SpatialGrid]:
        """Generates the spatial grid if it doesn't exist for the given resolution."""
        result = await self.session.execute(select(SpatialGrid).where(SpatialGrid.resolution == self.resolution))
        existing_grids = result.scalars().all()
        
        if existing_grids:
            return existing_grids
            
        logger.info(f"Generating {self.resolution} degree grid...")
        
        # Load landing centres for distance-to-coast calculations
        lc_result = await self.session.execute(select(LandingCentre.latitude, LandingCentre.longitude))
        landing_centres = lc_result.all()
        
        grids_to_insert = []
        lat = self.min_lat
        while lat <= self.max_lat:
            lon = self.min_lon
            while lon <= self.max_lon:
                cell_id = f"cell_{lat:.2f}_{lon:.2f}_{self.resolution}"
                
                # Simple distance to nearest landing centre as a proxy for distance to coast
                dist_to_coast = None
                if landing_centres:
                    dist_to_coast = min(haversine(lat, lon, lc[0], lc[1]) for lc in landing_centres)
                
                geom_wkt = f"POLYGON(({lon} {lat}, {lon+self.resolution} {lat}, {lon+self.resolution} {lat+self.resolution}, {lon} {lat+self.resolution}, {lon} {lat}))"
                centroid_wkt = f"POINT({lon + self.resolution/2} {lat + self.resolution/2})"
                
                grids_to_insert.append({
                    "id": cell_id,
                    "resolution": self.resolution,
                    "latitude": lat,
                    "longitude": lon,
                    "geom": geom_wkt,
                    "centroid": centroid_wkt,
                    "distance_to_coast_km": dist_to_coast
                })
                lon += self.resolution
            lat += self.resolution
            
        if grids_to_insert:
            await self.session.execute(insert(SpatialGrid).values(grids_to_insert))
            await self.session.commit()
            logger.info(f"Generated {len(grids_to_insert)} grid cells.")
            
        # Refetch to return objects
        result = await self.session.execute(select(SpatialGrid).where(SpatialGrid.resolution == self.resolution))
        return result.scalars().all()

    def _impute_from_observations(self, lat: float, lon: float, observations: List[OceanObservation]) -> Tuple[OceanObservation, float]:
        """Nearest neighbor imputation."""
        if not observations:
            return None, float('inf')
            
        nearest_obs = None
        min_dist = float('inf')
        
        for obs in observations:
            dist = haversine(lat, lon, obs.latitude, obs.longitude)
            if dist < min_dist:
                min_dist = dist
                nearest_obs = obs
                
        return nearest_obs, min_dist

    async def run(self, target_timestamp: datetime = None) -> int:
        """
        Runs the feature engineering pipeline.
        Aggregates raw observations into normalized ModelFeatures.
        """
        target_timestamp = target_timestamp or datetime.now(timezone.utc)
        
        # 1. Ensure Spatial Grid exists
        grids = await self._ensure_grid_exists()
        
        # 2. Fetch raw observations within a time window (e.g., last 24 hours)
        # For simplicity in this milestone, we'll fetch recent observations
        obs_result = await self.session.execute(
            select(OceanObservation).order_by(OceanObservation.timestamp.desc()).limit(100)
        )
        observations = obs_result.scalars().all()
        
        if not observations:
            logger.warning("No raw observations available to engineer features.")
            return 0
            
        features_to_insert = []
        
        # 3. For each grid cell, generate the feature vector
        for grid in grids:
            # Spatial Interpolation (Nearest Neighbor)
            nearest_obs, dist = self._impute_from_observations(grid.latitude, grid.longitude, observations)
            
            # Missing Data Strategy: If nearest observation is too far, leave environmental vars as null
            env_vars = {
                "wave_height": None,
                "wave_period": None,
                "wave_direction": None,
                "wind_speed": None,     # Explicitly None per requirements
                "wind_direction": None, # Explicitly None per requirements
                "sst": None,            # Explicitly None per requirements
                "provenance": "MISSING",
                "imputation_flags": None,
                "is_valid": False
            }
            
            if nearest_obs and dist <= self.max_imputation_distance_km:
                env_vars.update({
                    "wave_height": nearest_obs.wave_height,
                    "wave_period": nearest_obs.wave_period,
                    # Fallback to current direction if wave direction isn't explicitly modeled in this record
                    "wave_direction": nearest_obs.current_direction, 
                    "provenance": nearest_obs.source_name, # e.g. "Open-Meteo"
                    "imputation_flags": f"NN_dist_{dist:.1f}km",
                    "is_valid": True
                })
            
            # Temporal Features
            dt = nearest_obs.timestamp if nearest_obs else target_timestamp
            
            features_to_insert.append({
                "grid_cell_id": grid.id,
                "timestamp": dt,
                "wave_height": env_vars["wave_height"],
                "wave_period": env_vars["wave_period"],
                "wave_direction": env_vars["wave_direction"],
                "wind_speed": env_vars["wind_speed"],
                "wind_direction": env_vars["wind_direction"],
                "sst": env_vars["sst"],
                "hour": dt.hour,
                "day_of_year": dt.timetuple().tm_yday,
                "season": get_season(dt),
                "is_valid": env_vars["is_valid"],
                "provenance": env_vars["provenance"],
                "imputation_flags": env_vars["imputation_flags"]
            })
            
        # 4. Persistence
        if features_to_insert:
            await self.session.execute(insert(ModelFeature).values(features_to_insert))
            await self.session.commit()
            
        logger.info(f"Engineered and saved {len(features_to_insert)} feature vectors.")
        return len(features_to_insert)
