"""
MatsyaAI Canonical Grid Generator

Generates a strictly reproducible 0.1 x 0.1 degree spatial grid for the Maharashtra region.

SPECIFICATION:
- Latitude Bounds: 15.50 to 20.00
- Longitude Bounds: 72.00 to 74.00
- Grid Resolution: 0.1 degree
- Coordinate Convention: Center of the cell (e.g. 15.5 represents cell from 15.45 to 15.55)
- Cell ID Convention: `cell_{lat:.1f}_{lon:.1f}` (e.g., `cell_15.5_72.0`)
- Marine Mask: `global_land_mask` library (version 1.0.0, numpy-based)
- Expected Generated Cell Count: 537 valid marine cells
"""
import numpy as np
from global_land_mask import globe
from typing import List, Dict

from backend.app.ml.config import (
    GRID_MIN_LAT,
    GRID_MAX_LAT,
    GRID_MIN_LON,
    GRID_MAX_LON,
)

CANONICAL_RESOLUTION = 0.1

def generate_canonical_grid() -> List[Dict]:
    """
    Generate the authoritative 0.1 degree marine grid.
    Returns a list of cell dictionaries containing ID, center lat, and center lon.
    """
    # Create coordinate arrays (add resolution/2 so the coordinates represent cell centers)
    # Using np.arange with an epsilon to avoid float cutoff issues
    lats = np.arange(GRID_MIN_LAT, GRID_MAX_LAT + CANONICAL_RESOLUTION/2, CANONICAL_RESOLUTION)
    lons = np.arange(GRID_MIN_LON, GRID_MAX_LON + CANONICAL_RESOLUTION/2, CANONICAL_RESOLUTION)
    
    # We will round coordinates to 3 decimal places for clean IDs
    lats = np.round(lats, 3)
    lons = np.round(lons, 3)

    cells = []
    
    for lat in lats:
        for lon in lons:
            # Check if land. globe.is_land returns True for land, False for ocean.
            is_land = globe.is_land(lat, lon)
            
            if not is_land:
                cell_id = f"cell_{lat:.1f}_{lon:.1f}"
                cells.append({
                    "grid_cell_id": cell_id,
                    "latitude": float(lat),
                    "longitude": float(lon),
                    "resolution": CANONICAL_RESOLUTION
                })
                
    return cells

if __name__ == "__main__":
    grid = generate_canonical_grid()
    print(f"Generated {len(grid)} valid marine canonical grid cells.")
    for i in range(5):
        print(grid[i])
