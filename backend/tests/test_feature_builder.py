import pytest
from datetime import datetime, timezone, timedelta
import numpy as np

from backend.app.services.ml.feature_builder import FeatureBuilder, ProvenanceFeature
from backend.scripts.generate_spatial_grid import generate_canonical_grid

@pytest.fixture
def canonical_grid():
    # Return a small mock grid for testing logic quickly
    return [
        {"grid_cell_id": "cell_15.5_72.0", "latitude": 15.5, "longitude": 72.0, "resolution": 0.1},
        {"grid_cell_id": "cell_15.5_72.1", "latitude": 15.5, "longitude": 72.1, "resolution": 0.1},
    ]

@pytest.fixture
def feature_builder(canonical_grid):
    return FeatureBuilder(canonical_grid=canonical_grid, gfw_availability_lag_days=4)

def test_canonical_grid_reproducibility():
    """Test marine masking and generation of the full canonical grid."""
    grid = generate_canonical_grid()
    assert len(grid) > 0
    # 18.5, 73.8 is land (Pune area, inland), should not be in marine grid
    for cell in grid:
        assert not (round(cell['latitude'], 1) == 18.5 and round(cell['longitude'], 1) == 73.8)

def test_gfw_aggregation_and_lag_policy_historical(feature_builder):
    """Test GFW enforces lag policy during historical backtesting, ignoring retrieved_at."""
    prediction_time = datetime(2023, 10, 10, tzinfo=timezone.utc)
    
    gfw_records = [
        # Available record (lag = 5 days). Retrieved in 2026! Should still be accepted in historical mode.
        {"observation_date": "2023-10-05T00:00:00Z", "lat": 15.51, "lon": 72.02, "fishing_hours": 2.0, "retrieved_at": "2026-10-09T00:00:00Z"},
        # Another record in same cell (should sum)
        {"observation_date": "2023-10-05T00:00:00Z", "lat": 15.49, "lon": 72.04, "fishing_hours": 3.5, "retrieved_at": "2026-10-09T00:00:00Z"},
        # Leaked record (lag = 2 days, less than 4 days threshold). Should be dropped!
        {"observation_date": "2023-10-08T00:00:00Z", "lat": 15.51, "lon": 72.02, "fishing_hours": 5.0, "retrieved_at": "2026-10-09T00:00:00Z"},
    ]
    
    features = feature_builder.map_gfw_to_canonical(gfw_records, prediction_time, is_historical_backtest=True)
    
    # We should have features for ALL 2 canonical cells because the data for 2023-10-05 was available!
    # Cell 15.5_72.0 should be 5.5
    # Cell 15.5_72.1 has no effort in gfw_records, so it should be exactly 0.0 (True Zero)
    assert len(features) == 2
    
    feat_72_0 = next(f for f in features if f.grid_cell_id == "cell_15.5_72.0")
    feat_72_1 = next(f for f in features if f.grid_cell_id == "cell_15.5_72.1")
    
    assert feat_72_0.value == 5.5  # 2.0 + 3.5
    assert feat_72_0.retrieved_at == datetime(2026, 10, 9, tzinfo=timezone.utc)
    assert feat_72_0.source_publication_time is None
    
    assert feat_72_1.value == 0.0  # TRUE ZERO

def test_gfw_aggregation_prospective(feature_builder):
    """Test GFW enforces exact retrieved_at <= T during prospective/real-time mode."""
    prediction_time = datetime(2023, 10, 10, tzinfo=timezone.utc)
    
    gfw_records = [
        # Fetched exactly at T (Valid)
        {"observation_date": "2023-10-05T00:00:00Z", "lat": 15.51, "lon": 72.02, "fishing_hours": 2.0, "retrieved_at": "2023-10-10T00:00:00Z"},
        # Fetched after T (Invalid)
        {"observation_date": "2023-10-05T00:00:00Z", "lat": 15.49, "lon": 72.04, "fishing_hours": 3.5, "retrieved_at": "2023-10-11T00:00:00Z"},
    ]
    
    features = feature_builder.map_gfw_to_canonical(gfw_records, prediction_time, is_historical_backtest=False)
    
    # Only the first record is accepted. Cell 15.5_72.0 gets 2.0. Cell 15.5_72.1 gets 0.0.
    assert len(features) == 2
    feat_72_0 = next(f for f in features if f.grid_cell_id == "cell_15.5_72.0")
    assert feat_72_0.value == 2.0

def test_cmems_interpolation_and_leakage_rule(feature_builder):
    """Test CMEMS interpolation and strict publication time cutoff."""
    prediction_time = datetime(2023, 10, 10, 12, 0, 0, tzinfo=timezone.utc)
    
    cmems_obs = [
        # Valid forecast (published at T-1)
        {
            "observation_date": "2023-10-10T00:00:00Z", "latitude": 15.55, "longitude": 72.05,
            "sst": 28.5, "wave_direction": 180.0, "source_publication_time": "2023-10-09T12:00:00Z"
        },
        # Leaked forecast (published at T+1)
        {
            "observation_date": "2023-10-10T00:00:00Z", "latitude": 15.55, "longitude": 72.15,
            "sst": 29.0, "wave_direction": 190.0, "source_publication_time": "2023-10-10T13:00:00Z"
        },
        # Missing data representation (map to a different cell so it gets picked up)
        {
            "observation_date": "2023-10-10T00:00:00Z", "latitude": 15.55, "longitude": 72.11,
            "sst": None, "wave_direction": None, "source_publication_time": "2023-10-09T12:00:00Z"
        }
    ]
    
    features = feature_builder.map_cmems_to_canonical(cmems_obs, prediction_time)
    
    sst_features = [f for f in features if f.feature_name == 'sst']
    wave_dir_features = [f for f in features if f.feature_name == 'wave_direction']
    assert len(sst_features) > 0
    
    # Verify wave direction is exactly the nearest neighbor value (180.0), not numerically averaged
    valid_wave_dirs = [f.value for f in wave_dir_features if not np.isnan(f.value)]
    assert 180.0 in valid_wave_dirs
    assert 190.0 not in valid_wave_dirs
    
    # 28.5 should map to cell_15.5_72.0, None maps as NaN.
    # The leaked 29.0 should NOT be present.
    values = [f.value for f in sst_features]
    assert 29.0 not in values
    assert 28.5 in values
    assert any(np.isnan(v) for v in values if isinstance(v, float))

def test_pfz_mapping_and_distance(feature_builder):
    """Test INCOIS PFZ maps to canonical cells and distances are calculated."""
    prediction_time = datetime(2023, 10, 10, 12, 0, 0, tzinfo=timezone.utc)
    
    pfz_points = [
        # Valid PFZ
        {
            "lat": 15.6, "lon": 72.0, "advisory_date": "2023-10-09T00:00:00Z", "validity_date": "2023-10-11T00:00:00Z"
        },
        # Future/Leaked PFZ (advisory issued after T)
        {
            "lat": 15.5, "lon": 72.1, "advisory_date": "2023-10-10T13:00:00Z", "validity_date": "2023-10-12T00:00:00Z"
        }
    ]
    
    features = feature_builder.map_pfz_to_canonical(pfz_points, prediction_time)
    
    # Expect 2 canonical cells * 2 features (dist + active) = 4 features
    assert len(features) == 4
    
    cell_72_0 = [f for f in features if f.grid_cell_id == "cell_15.5_72.0" and f.feature_name == "distance_to_nearest_pfz_km"][0]
    cell_72_1 = [f for f in features if f.grid_cell_id == "cell_15.5_72.1" and f.feature_name == "distance_to_nearest_pfz_km"][0]
    
    # The PFZ at 15.6, 72.0 is closest to cell 15.5, 72.0. Distance is roughly 11.1km
    assert cell_72_0.value > 10.0 and cell_72_0.value < 12.0
    
    # cell 15.5, 72.1 is further away from 15.6, 72.0.
    assert cell_72_1.value > cell_72_0.value

def test_target_construction(feature_builder):
    """Test target is strictly NEXT calendar day."""
    prediction_time = datetime(2023, 10, 10, 15, 0, 0, tzinfo=timezone.utc)
    
    gfw_records = [
        # Same day effort (SHOULD NOT BE TARGET)
        {"observation_date": "2023-10-10T00:00:00Z", "lat": 15.51, "lon": 72.02, "fishing_hours": 2.0},
        # Next calendar day effort (TARGET)
        {"observation_date": "2023-10-11T00:00:00Z", "lat": 15.51, "lon": 72.02, "fishing_hours": 3.5},
        # Future effort
        {"observation_date": "2023-10-12T00:00:00Z", "lat": 15.51, "lon": 72.02, "fishing_hours": 1.0},
    ]
    
    targets = feature_builder.construct_target(gfw_records, prediction_time)
    assert len(targets) == 1
    assert targets[0].value == 3.5
    assert targets[0].observation_valid_time == datetime(2023, 10, 11, tzinfo=timezone.utc)
