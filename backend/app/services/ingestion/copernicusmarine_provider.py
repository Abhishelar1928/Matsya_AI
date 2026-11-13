import os
import logging
from typing import List, Dict, Optional
import pandas as pd
import numpy as np
import datetime

# Conditional import to handle missing package gracefully
try:
    import copernicusmarine
    import xarray as xr
    CMEMS_AVAILABLE = True
except ImportError:
    CMEMS_AVAILABLE = False

from backend.app.services.ingestion.environmental_provider import BaseEnvironmentalProvider
from backend.app.ml.config import (
    CMEMS_USERNAME,
    CMEMS_PASSWORD,
    CMEMS_PRODUCT_PHYSICS,
    CMEMS_PRODUCT_WAVES,
    CMEMS_PRODUCT_BGC
)

logger = logging.getLogger(__name__)

class CopernicusMarineProvider(BaseEnvironmentalProvider):
    """
    Environmental data provider using Copernicus Marine Service (CMEMS).
    
    Products Used:
    - cmems_mod_glo_phy_anfc_0.083deg_P1D-m (Global Ocean Physics Analysis and Forecast, Daily)
      Variables: uo (current E), vo (current N), thetao (potential temp / SST), so (salinity)
    - cmems_mod_glo_wav_anfc_0.083deg_PT3H-i (Global Ocean Waves Analysis and Forecast, 3-Hourly)
      Variables: VHM0 (wave height), VTM10 (wave period), VMDR (wave direction)
      
    Resolution: 1/12 degree (~8km) globally.
    """
    
    def __init__(self):
        self.username = CMEMS_USERNAME
        self.password = CMEMS_PASSWORD
        self.auth_blocked = not (self.username and self.password)
        
        if not CMEMS_AVAILABLE:
            logger.error("copernicusmarine package is not installed.")
            self.auth_blocked = True
            
        if self.auth_blocked:
            logger.warning("Copernicus Marine Service credentials are missing or package unavailable. Provider is BLOCKED.")

    def _fetch_cmems_point(self, lat: float, lon: float, date_str: str) -> Dict:
        """
        Fetches a single coordinate-date point from CMEMS OPeNDAP lazy loaded xarrays.
        In a production batch scenario, this would be heavily vectorized.
        For validation, we query individually to prove capability.
        """
        if self.auth_blocked:
            return {"data_status": "BLOCKED_AUTH"}

        result = {
            "observation_date": date_str,
            "latitude": lat,
            "longitude": lon,
            "source": "Copernicus Marine Service (CMEMS)",
            "source_publication_time": datetime.datetime.now(datetime.timezone.utc).isoformat(), # Ideally we parse this from the dataset metadata, but for now we set it to current retrieval time as the boundary.
            "retrieved_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "data_status": "SUCCESS"
        }

        try:
            # Login required for open_dataset
            copernicusmarine.login(username=self.username, password=self.password, force_overwrite=True)
            
            # Target datetime
            target_dt = pd.to_datetime(date_str).tz_localize(None)

            # 1. Physics Data (Daily)
            ds_phy = copernicusmarine.open_dataset(
                dataset_id=CMEMS_PRODUCT_PHYSICS,
                username=self.username,
                password=self.password
            )
            # Select nearest point
            point_phy = ds_phy.sel(latitude=lat, longitude=lon, time=target_dt, method="nearest")
            
            # Physics variables (at depth=0.494m for surface)
            if 'depth' in point_phy.dims:
                point_phy = point_phy.isel(depth=0)
                
            uo = float(point_phy['uo'].values) if 'uo' in point_phy.data_vars else np.nan
            vo = float(point_phy['vo'].values) if 'vo' in point_phy.data_vars else np.nan
            thetao = float(point_phy['thetao'].values) if 'thetao' in point_phy.data_vars else np.nan
            so = float(point_phy['so'].values) if 'so' in point_phy.data_vars else np.nan
            
            # Calculate current velocity magnitude
            if not np.isnan(uo) and not np.isnan(vo):
                result["ocean_current_velocity"] = float(np.sqrt(uo**2 + vo**2))
            else:
                result["ocean_current_velocity"] = None
                
            result["sst"] = thetao if not np.isnan(thetao) else None
            result["salinity"] = so if not np.isnan(so) else None

            # 2. Waves Data (3-Hourly -> aggregate to daily mean for historical match)
            ds_wav = copernicusmarine.open_dataset(
                dataset_id=CMEMS_PRODUCT_WAVES,
                username=self.username,
                password=self.password
            )
            # Select daily window
            start_dt = target_dt
            end_dt = target_dt + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
            # First select spatial coordinates using nearest, then slice time and mean
            point_wav = ds_wav.sel(latitude=lat, longitude=lon, method="nearest").sel(time=slice(start_dt, end_dt)).mean(dim='time')
            
            vhm0 = float(point_wav['VHM0'].values) if 'VHM0' in point_wav.data_vars else np.nan
            vtm10 = float(point_wav['VTM10'].values) if 'VTM10' in point_wav.data_vars else np.nan
            vmdr = float(point_wav['VMDR'].values) if 'VMDR' in point_wav.data_vars else np.nan
            
            result["wave_height"] = vhm0 if not np.isnan(vhm0) else None
            result["wave_period"] = vtm10 if not np.isnan(vtm10) else None
            result["wave_direction"] = vmdr if not np.isnan(vmdr) else None
            result["swell_wave_height"] = None # Optional/Fallback if separate swell band exists
            result["wind_speed"] = None # Need separate wind product or atmospheric forcing if missing in wave product
            
            # 3. Biogeochemistry Data (Daily, 0.25 deg)
            try:
                ds_bgc = copernicusmarine.open_dataset(
                    dataset_id=CMEMS_PRODUCT_BGC,
                    username=self.username,
                    password=self.password
                )
                point_bgc = ds_bgc.sel(latitude=lat, longitude=lon, time=target_dt, method="nearest")
                if 'depth' in point_bgc.dims:
                    point_bgc = point_bgc.isel(depth=0)
                chl = float(point_bgc['chl'].values) if 'chl' in point_bgc.data_vars else np.nan
                result["chlorophyll"] = chl if not np.isnan(chl) else None
            except Exception as e_bgc:
                logger.warning(f"CMEMS BGC API Error for point {lat},{lon}: {str(e_bgc)}")
                result["chlorophyll"] = None

            # Check for NaN land masking
            if all(v is None for v in [result.get("wave_height"), result.get("ocean_current_velocity"), result.get("sst"), result.get("chlorophyll")]):
                result["data_status"] = "MISSING_LAND_MASK"

        except Exception as e:
            logger.error(f"CMEMS API Error: {str(e)}")
            result["data_status"] = f"API_ERROR: {str(e)}"
            
        return result

    def fetch_historical(self, grid_cells: List[Dict], start_date: str, end_date: str) -> List[Dict]:
        """
        Historical mode mapping environment at T to same-day records.
        """
        results = []
        # Expand dates
        dates = pd.date_range(start=start_date, end=end_date, freq='D').strftime('%Y-%m-%d')
        for date_str in dates:
            for cell in grid_cells:
                lat, lon = cell['latitude'], cell['longitude']
                res = self._fetch_cmems_point(lat, lon, date_str)
                res["grid_cell_id"] = cell.get("grid_cell_id", f"{lat}_{lon}")
                results.append(res)
        return results

    def fetch_current(self, grid_cells: List[Dict]) -> List[Dict]:
        """
        Forecast mode mapping Environment forecast for T+1.
        Called at time T, retrieves T+1 environment.
        """
        results = []
        # T+1 logic
        t_plus_1 = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
        for cell in grid_cells:
            lat, lon = cell['latitude'], cell['longitude']
            res = self._fetch_cmems_point(lat, lon, t_plus_1)
            res["grid_cell_id"] = cell.get("grid_cell_id", f"{lat}_{lon}")
            res["observation_date"] = t_plus_1
            res["forecast_for"] = "T+1"
            results.append(res)
        return results
