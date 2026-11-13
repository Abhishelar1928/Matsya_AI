from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from datetime import date

class BaseEnvironmentalProvider(ABC):
    """
    Common interface for all environmental data providers.
    Ensures the ML pipeline does not depend directly on any specific source.
    """

    @abstractmethod
    def fetch_historical(self, grid_cells: List[Dict], start_date: str, end_date: str) -> List[Dict]:
        """
        Fetch historical environmental data for the given grid cells and date range.
        
        Must return a list of dictionaries containing:
        - grid_cell_id
        - observation_date
        - latitude
        - longitude
        - wave_height
        - wave_period
        - wave_direction
        - swell_wave_height
        - wind_speed
        - wind_direction
        - ocean_current_velocity
        - ocean_current_direction
        - sst
        - source
        - source_timestamp
        - data_status
        """
        pass

    @abstractmethod
    def fetch_current(self, grid_cells: List[Dict]) -> List[Dict]:
        """
        Fetch current/forecast environmental data for inference.
        """
        pass
