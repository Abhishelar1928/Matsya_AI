import math
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

@dataclass
class ProvenanceFeature:
    """
    Wraps a feature value with its strict provenance metadata to guarantee
    temporal and spatial traceability, preventing leakage.
    """
    feature_name: str
    value: Any
    grid_cell_id: str
    observation_valid_time: datetime
    source: str
    source_publication_time: Optional[datetime]
    retrieved_at: Optional[datetime]
    
    def to_dict(self):
        return {
            "feature_name": self.feature_name,
            "value": self.value,
            "grid_cell_id": self.grid_cell_id,
            "observation_valid_time": self.observation_valid_time.isoformat() if self.observation_valid_time else None,
            "source": self.source,
            "source_publication_time": self.source_publication_time.isoformat() if self.source_publication_time else None,
            "retrieved_at": self.retrieved_at.isoformat() if self.retrieved_at else None,
        }

class FeatureBuilder:
    """
    Constructs ML features for Matsya AI based on the fixed 0.1 degree Canonical Grid.
    Enforces strict temporal availability boundaries and provenance tracking.
    """
    
    def __init__(self, canonical_grid: List[Dict], gfw_availability_lag_days: int = 4):
        """
        :param canonical_grid: List of dicts with 'grid_cell_id', 'latitude', 'longitude'
        :param gfw_availability_lag_days: Conservative availability lag for GFW historical data.
        """
        self.grid = canonical_grid
        self.gfw_availability_lag_days = gfw_availability_lag_days
        
    def _haversine_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate the great circle distance in kilometers between two points on the earth."""
        R = 6371.0 # Radius of earth in km
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c

    def get_nearest_canonical_cell(self, lat: float, lon: float) -> Dict:
        """Find the nearest canonical grid cell for a given lat/lon."""
        min_dist = float('inf')
        nearest = None
        for cell in self.grid:
            dist = self._haversine_distance(lat, lon, cell['latitude'], cell['longitude'])
            if dist < min_dist:
                min_dist = dist
                nearest = cell
        return nearest

    def map_cmems_to_canonical(
        self, 
        cmems_observations: List[Dict], 
        prediction_time_t: datetime
    ) -> List[ProvenanceFeature]:
        """
        Regrids CMEMS native data (e.g. 0.083 deg or 0.25 deg) to the canonical 0.1 deg grid.
        Enforces Temporal Leakage Rule: source_publication_time <= prediction_time_t.
        """
        features = []
        
        # 1. Filter out leaked forecasts
        valid_observations = []
        for obs in cmems_observations:
            pub_time_str = obs.get('source_publication_time')
            if not pub_time_str:
                logger.warning(f"Missing source_publication_time for CMEMS data. Dropping.")
                continue
            
            pub_time = datetime.fromisoformat(pub_time_str)
            if pub_time.tzinfo is None:
                pub_time = pub_time.replace(tzinfo=timezone.utc)
                
            if pub_time <= prediction_time_t:
                valid_observations.append(obs)
            else:
                logger.debug("Dropped leaked CMEMS forecast published after T.")

        if not valid_observations:
            return features
            
        # 2. Spatial regridding (Nearest Neighbor Interpolation for Canonical Grid)
        # For simplicity and strictness, we map each CMEMS point to the nearest canonical cell.
        # In a highly vectorized pandas/xarray setup, this would use scipy.interpolate.griddata
        # For our provider dict format, we assign the CMEMS value to the closest canonical cell.
        
        # Group by valid time
        df = pd.DataFrame(valid_observations)
        if df.empty:
            return features
            
        df['valid_time'] = pd.to_datetime(df['observation_date'])
        
        for valid_time, group in df.groupby('valid_time'):
            # Regrid: for each canonical cell, find the closest CMEMS point
            for cell in self.grid:
                # Calculate distances
                group['dist'] = group.apply(lambda row: self._haversine_distance(
                    cell['latitude'], cell['longitude'], row['latitude'], row['longitude']), axis=1)
                
                closest = group.loc[group['dist'].idxmin()]
                
                # Check maximum interpolation distance (e.g., don't map if CMEMS point is too far)
                if closest['dist'] > 30.0:  # ~0.3 degrees max distance
                    continue
                    
                # Document CMEMS Interpolation:
                # We use nearest-neighbor selection for all variables to preserve original source provenance.
                # This is especially critical for 'wave_direction' (VMDR), which is a circular/angle variable
                # and CANNOT be mathematically averaged using scalar interpolation.
                variables = ['sst', 'chlorophyll', 'ocean_current_velocity', 'wave_height', 'wave_period', 'wave_direction']
                for var in variables:
                    val = closest.get(var)
                    if pd.isna(val) or val is None:
                        val = np.nan # Explicit missing indicator
                        
                    feat = ProvenanceFeature(
                        feature_name=var,
                        value=val,
                        grid_cell_id=cell['grid_cell_id'],
                        observation_valid_time=valid_time,
                        source=closest.get('source', 'CMEMS'),
                        source_publication_time=pd.to_datetime(closest['source_publication_time']),
                        retrieved_at=pd.to_datetime(closest.get('retrieved_at')) if pd.notna(closest.get('retrieved_at')) else None
                    )
                    features.append(feat)
                    
        return features

    def map_gfw_to_canonical(
        self, 
        gfw_records: List[Dict], 
        prediction_time_t: datetime,
        is_historical_backtest: bool = True
    ) -> List[ProvenanceFeature]:
        """
        Maps GFW apparent fishing effort into the 0.1 deg canonical grid (Summation).
        
        GFW AVAILABILITY POLICY:
        - Prospective/Real-time: Validates if `retrieved_at <= prediction_time_t`.
        - Historical Backtesting: A record retrieved in 2026 cannot prove availability in 2023.
          Instead, we apply the 'GFW Conservative Coverage Lag Policy' (configurable, default 4 days).
          This ensures we assume data was not available until 4 days after the observation date.
        """
        features = []
        
        valid_records = []
        for rec in gfw_records:
            if not is_historical_backtest:
                # 1. Real-time / Prospective check (Did we actually retrieve it by T?)
                retrieved_str = rec.get('retrieved_at')
                if not retrieved_str:
                    logger.warning("GFW record missing retrieved_at provenance. Dropping.")
                    continue
                    
                retrieved_time = datetime.fromisoformat(retrieved_str)
                if retrieved_time.tzinfo is None:
                    retrieved_time = retrieved_time.replace(tzinfo=timezone.utc)
                    
                if retrieved_time > prediction_time_t:
                    continue
            else:
                # 2. Historical Backtesting Policy
                # We ignore retrieved_at (since it might be 2026 for a 2023 record)
                # and strictly enforce the Conservative Availability Lag Policy.
                obs_date_str = rec.get('observation_date')
                obs_date = datetime.fromisoformat(obs_date_str).replace(tzinfo=timezone.utc)
                
                days_lag = (prediction_time_t - obs_date).days
                if days_lag < self.gfw_availability_lag_days:
                    # Violates conservative backtesting policy
                    continue
                
            valid_records.append(rec)
            
        if not valid_records:
            return features
            
        df = pd.DataFrame(valid_records)
        df['observation_date'] = pd.to_datetime(df['observation_date'])
        
        # Map to canonical cells and SUM
        for date, group in df.groupby('observation_date'):
            # Regrid: for each GFW point, find nearest canonical cell
            # To be precise, 0.1 deg GFW easily maps by rounding, but using distance is robust
            group['canonical_cell_id'] = group.apply(
                lambda row: self.get_nearest_canonical_cell(row['lat'], row['lon'])['grid_cell_id'], 
                axis=1
            )
            
            # Sum fishing hours per canonical cell
            summed = group.groupby('canonical_cell_id')['fishing_hours'].sum().reset_index()
            summed_dict = dict(zip(summed['canonical_cell_id'], summed['fishing_hours']))
            
            # For provenance, we pick the maximum retrieved_at in the aggregated group
            retrieved_max = pd.to_datetime(group['retrieved_at']).max()
            
            # Output features for ALL canonical cells. 
            # If data is available for this date, cells not in GFW are true 0 effort.
            # If data wasn't available (lag policy), this date loop wouldn't even execute.
            for cell in self.grid:
                cell_id = cell['grid_cell_id']
                val = float(summed_dict.get(cell_id, 0.0))
                
                feat = ProvenanceFeature(
                    feature_name='fishing_hours_lagged',
                    value=val,
                    grid_cell_id=cell_id,
                    observation_valid_time=date,
                    source='Global Fishing Watch (GFW)',
                    source_publication_time=None, # Explicitly missing from GFW API
                    retrieved_at=retrieved_max
                )
                features.append(feat)
                
        return features

    def map_pfz_to_canonical(
        self,
        pfz_points: List[Dict],
        prediction_time_t: datetime
    ) -> List[ProvenanceFeature]:
        """
        Maps INCOIS PFZ coordinates to the canonical grid and computes distance_to_pfz.
        Does NOT modify INCOIS structure, purely creates derived spatial features.
        """
        features = []
        
        # Filter PFZ points active at time T
        active_pfz = []
        for pfz in pfz_points:
            # Advisory validity
            valid_from = pfz.get('advisory_date')
            valid_to = pfz.get('validity_date')
            
            if not valid_from or not valid_to:
                continue
                
            if isinstance(valid_from, str):
                valid_from = datetime.fromisoformat(valid_from)
            if isinstance(valid_to, str):
                valid_to = datetime.fromisoformat(valid_to)
                
            # Naive to aware if needed
            if valid_from.tzinfo is None: valid_from = valid_from.replace(tzinfo=timezone.utc)
            if valid_to.tzinfo is None: valid_to = valid_to.replace(tzinfo=timezone.utc)
            
            # Was this advisory published/available by T, and is it valid?
            if valid_from <= prediction_time_t:
                active_pfz.append(pfz)
                
        # For every canonical cell, calculate distance to nearest active PFZ
        for cell in self.grid:
            if not active_pfz:
                dist = np.nan # Missing/Unavailable PFZ info
                pfz_active = False
                source = "INCOIS_PFZ (NO_ACTIVE)"
            else:
                min_dist = float('inf')
                source = "INCOIS_PFZ"
                for pfz in active_pfz:
                    d = self._haversine_distance(cell['latitude'], cell['longitude'], pfz['lat'], pfz['lon'])
                    if d < min_dist:
                        min_dist = d
                dist = min_dist
                # If nearest is within half a cell diagonal (~7km), consider cell 'inside' PFZ
                pfz_active = dist <= 7.0
                
            feat_dist = ProvenanceFeature(
                feature_name='distance_to_nearest_pfz_km',
                value=float(dist) if not np.isnan(dist) else np.nan,
                grid_cell_id=cell['grid_cell_id'],
                observation_valid_time=prediction_time_t,
                source=source,
                source_publication_time=valid_from if active_pfz else None,
                retrieved_at=None
            )
            feat_active = ProvenanceFeature(
                feature_name='is_incois_pfz_active',
                value=bool(pfz_active),
                grid_cell_id=cell['grid_cell_id'],
                observation_valid_time=prediction_time_t,
                source=source,
                source_publication_time=valid_from if active_pfz else None,
                retrieved_at=None
            )
            features.extend([feat_dist, feat_active])
            
        return features

    def construct_target(
        self,
        gfw_records: List[Dict],
        prediction_time_t: datetime
    ) -> List[ProvenanceFeature]:
        """
        Constructs the TARGET variable for ML: NEXT CALENDAR DAY apparent fishing activity.
        Target window: T+1 (start of day) to T+1 (end of day).
        """
        targets = []
        
        # Target calendar day
        target_date = (prediction_time_t + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        target_date_str = target_date.strftime('%Y-%m-%d')
        
        target_records = [r for r in gfw_records if r.get('observation_date', '').startswith(target_date_str)]
        
        if not target_records:
            # True Zero or Missing?
            # We don't append anything, implying Missing Data unless explicitly zeroed later.
            return targets
            
        df = pd.DataFrame(target_records)
        
        for _, row in df.iterrows():
            canonical_id = self.get_nearest_canonical_cell(row['lat'], row['lon'])['grid_cell_id']
            # We just append individual target observations, sum later
            feat = ProvenanceFeature(
                feature_name='target_fishing_hours_T_plus_1',
                value=float(row['fishing_hours']),
                grid_cell_id=canonical_id,
                observation_valid_time=target_date,
                source='Global Fishing Watch (GFW)',
                source_publication_time=None,
                retrieved_at=pd.to_datetime(row.get('retrieved_at')) if pd.notna(row.get('retrieved_at')) else None
            )
            targets.append(feat)
            
        return targets
