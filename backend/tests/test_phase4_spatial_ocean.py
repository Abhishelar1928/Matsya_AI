"""
Comprehensive Unit & Integration Tests for MatsyaAI Phase 4 (`Phase4_SpatioOcean_v1`):
1. SpatialAdjacencyMapper (1-ring Moore 3x3, 2-ring ~54 km, Haversine distances, edge cells)
2. Zero-leakage spatial neighbor causality (T+1 perturbation must not change T)
3. Zero-leakage rolling Chl-a & SST front causality (T+1 perturbation must not change T)
4. Satellite cloud-cover NaN resilience & missingness indicator integrity
5. Phase 4 LeakageValidator enforcement (Stage-1 purity, expanding OOF, calibration isolation)
6. Multi-year chronological full-year Test split vs single-year 60/20/20 compatibility
7. Frozen Phase 4 artifact consistency + Phase4InferencePipeline + SafetyGate decoupling
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd
import pytest

from backend.app.ml.config import (
    PHASE4_FEATURES_PATH,
    PHASE4_METADATA_PATH,
    PHASE4_RESULTS_PATH,
    PHASE4_THRESHOLD_PATH,
)
from backend.app.ml.inference import Phase4InferencePipeline
from backend.app.ml.safety_gate import SafetyGate
from ml.evaluation.leakage_validator import (
    DataLeakageError,
    validate_calibration_isolation,
    validate_rolling_ocean_causality,
    validate_spatial_neighbor_causality,
    validate_stage1_feature_purity,
    validate_stage1_oof_causality,
)
from ml.features.features_spatial_ocean import (
    OCEAN_HABITAT_FEATURES,
    SPATIAL_NEIGHBOR_FEATURES,
    STAGE1_HABITAT_FEATURES,
    SpatialAdjacencyMapper,
    build_phase4_causal_dataset,
    compute_ocean_habitat_features,
    compute_spatial_neighborhood_features,
)
from ml.models.phase4_pipeline import (
    ProbabilityCalibrator,
    split_chronological_dataset,
)
from ml.models.serialize_phase4_artifacts import serialize_phase4


def _make_synthetic_grid_history(
    start_date: str = "2023-01-01",
    end_date: str = "2023-02-20",
    lat_steps: int = 5,
    lon_steps: int = 5,
) -> pd.DataFrame:
    """Create a regular 5x5 grid of canonical 0.25-deg cells across multi-day history."""
    dates = pd.date_range(start_date, end_date, freq="D")
    rows = []
    rng = np.random.default_rng(42)
    for r in range(lat_steps):
        g_lat = 16.0 + 0.25 * r
        for c in range(lon_steps):
            g_lon = 72.0 + 0.25 * c
            cid = f"cell_{g_lat:.2f}_{g_lon:.2f}_0.25"
            c_lat = g_lat + 0.125
            c_lon = g_lon + 0.125
            for d_idx, d in enumerate(dates):
                # Synthetic habitat gradient + ocean current + patchy clouds
                sst_val = 27.5 + 0.3 * r + 0.2 * np.sin(d_idx / 5.0)
                chl_val = 0.6 + 0.15 * c + (0.5 if d_idx % 9 == 0 else 0.0)
                if d_idx % 6 == 0 and (r + c) % 2 == 0:
                    chl_val = np.nan  # cloud gap
                fh = 3.5 if (r == 2 and c == 2 and d_idx % 2 == 0) else (1.5 if (r + c + d_idx) % 4 == 0 else 0.0)
                rows.append(
                    {
                        "grid_cell_id": cid,
                        "latitude": c_lat,
                        "longitude": c_lon,
                        "observation_date": d.strftime("%Y-%m-%d"),
                        "fishing_hours": fh,
                        "wave_height": 1.2 + 0.1 * rng.random(),
                        "wave_period": 8.0,
                        "wave_direction": 210.0,
                        "swell_wave_height": 0.9,
                        "ocean_current_velocity": 0.2 + 0.08 * r + 0.05 * c,
                        "wind_speed": 14.0 + 2.0 * rng.random(),
                        "distance_to_coast_km": 25.0 + 25.0 * (lon_steps - 1 - c),
                        "sst": sst_val,
                        "chl_a": chl_val,
                        "depth_m": 20.0 + 18.0 * (lon_steps - 1 - c),
                        "seabed_slope": 0.45 + 0.1 * c,
                    }
                )
    return pd.DataFrame(rows)


def test_spatial_adjacency_mapper_rings_and_distances():
    """Verify 1-ring Moore (8), 2-ring (16 on 5x5 center), self-exclusion, and boundary edges."""
    df = _make_synthetic_grid_history("2023-01-01", "2023-01-05")
    mapper = SpatialAdjacencyMapper(df)
    summary = mapper.to_summary()

    assert summary["total_cells"] == 25
    center_cid = "cell_16.50_72.50_0.25"
    corner_cid = "cell_16.00_72.00_0.25"

    r1_center = mapper.get_ring1(center_cid)
    r2_center = mapper.get_ring2(center_cid)
    assert len(r1_center) == 8
    assert len(r2_center) == 16
    assert center_cid not in r1_center
    assert center_cid not in r2_center
    assert set(r1_center).isdisjoint(set(r2_center))

    # Corner cell on 5x5 has 3 immediate 1-ring neighbors and 5 2-ring neighbors
    assert len(mapper.get_ring1(corner_cid)) == 3
    assert len(mapper.get_ring2(corner_cid)) == 5

    # Distance to direct N/S 0.25-deg neighbor should be ~27.8 km; 2-ring ~55 km
    north_nbr = "cell_16.75_72.50_0.25"
    two_north = "cell_17.00_72.50_0.25"
    assert 25.0 <= mapper.distance_km(center_cid, north_nbr) <= 30.0
    assert 50.0 <= mapper.distance_km(center_cid, two_north) <= 60.0


def test_zero_leakage_spatial_neighbor_causality():
    """Mutating neighbor cells on T+1 must produce ZERO change at T."""
    raw = _make_synthetic_grid_history("2023-01-01", "2023-01-25")
    mapper = SpatialAdjacencyMapper(raw)

    res = validate_spatial_neighbor_causality(
        raw_df=raw,
        builder_fn=lambda f: compute_spatial_neighborhood_features(f, mapper, gfw_lag_days=0),
        target_date_T="2023-01-20",
        spatial_cols=SPATIAL_NEIGHBOR_FEATURES,
    )
    assert res["status"] == "PASS"


def test_zero_leakage_rolling_ocean_causality():
    """Mutating Chl-a and SST on T+1 must produce ZERO change in lag3/lag7/lag14/anomaly/SST-front at T."""
    raw = _make_synthetic_grid_history("2023-01-01", "2023-01-25")
    mapper = SpatialAdjacencyMapper(raw)

    res = validate_rolling_ocean_causality(
        raw_df=raw,
        builder_fn=lambda f: compute_ocean_habitat_features(f, mapper),
        target_date_T="2023-01-20",
        ocean_cols=[
            "chl_a_lag3_mean",
            "chl_a_lag7_mean",
            "chl_a_lag14_mean",
            "chl_a_anomaly",
            "sst_spatial_gradient",
        ],
    )
    assert res["status"] == "PASS"


def test_cloud_cover_nan_resilience(tmp_path):
    """Ensure heavy cloud-cover NaNs in Chl-a / SST set clean _isna flags and never crash Phase 4 training/scoring."""
    raw = _make_synthetic_grid_history("2023-01-01", "2023-03-10", lat_steps=3, lon_steps=3)
    # Wipe out 60% of Chl-a and SST observations to simulate heavy monsoon cloud cover
    rng = np.random.default_rng(7)
    raw.loc[rng.random(len(raw)) < 0.6, "chl_a"] = np.nan
    raw.loc[rng.random(len(raw)) < 0.5, "sst"] = np.nan

    pq_path = tmp_path / "cloudy_synthetic.parquet"
    raw.to_parquet(pq_path, index=False)

    ds = build_phase4_causal_dataset(source_parquet_paths=pq_path, lookback_days=14, gfw_lag_days=0)
    assert len(ds) > 0
    assert (ds["chl_a_isna"].isin([0.0, 1.0])).all()
    assert (ds["sst_isna"].isin([0.0, 1.0])).all()
    assert (ds["chl_a"].isna() == (ds["chl_a_isna"] == 1.0)).all()
    assert (ds["sst"].isna() == (ds["sst_isna"] == 1.0)).all()


def test_phase4_leakage_validators_reject_violations():
    """Verify Stage-1 purity, OOF causality, and calibration isolation validators raise DataLeakageError."""
    with pytest.raises(DataLeakageError, match="Purity Violation"):
        validate_stage1_feature_purity(["sst", "chl_a", "fishing_hours_14d_mean"])

    with pytest.raises(DataLeakageError, match="Purity Violation"):
        validate_stage1_feature_purity(["sst", "nbr_1ring_fishing_mean"])

    # Valid pure list passes
    assert validate_stage1_feature_purity(STAGE1_HABITAT_FEATURES)["status"] == "PASS"

    # Bad OOF fold overlapping into validation
    bad_folds = [
        {
            "fold": 1,
            "train_min_date": "2023-01-01",
            "train_max_date": "2023-08-15",
            "pred_min_date": "2023-08-10",  # Leakage: pred_min <= train_max
            "pred_max_date": "2023-09-01",
        }
    ]
    with pytest.raises(DataLeakageError, match="OOF Fold 1 leakage"):
        validate_stage1_oof_causality(
            bad_folds,
            val_dates=pd.date_range("2023-09-10", "2023-10-15"),
            test_dates=pd.date_range("2023-10-16", "2023-12-31"),
        )

    # Bad calibration overlap with Test
    with pytest.raises(DataLeakageError, match="Calibration Leakage"):
        validate_calibration_isolation(
            cal_dates=pd.date_range("2023-09-01", "2023-10-25"),
            test_dates=pd.date_range("2023-10-20", "2023-12-31"),
        )


def test_multi_year_full_year_test_split_and_single_year_compat():
    """Multi-year spans reserve 365 full test days covering all 12 months; single-year preserves 60/20/20."""
    # Multi-year (2022-01-01 to 2024-12-31 = 1096 days)
    multi_dates = pd.date_range("2022-01-01", "2024-12-31", freq="D")
    multi_df = pd.DataFrame(
        {
            "grid_cell_id": "cell_16.00_72.00_0.25",
            "prediction_date_T": multi_dates,
            "target_fishing_hours": 0.0,
        }
    )
    split_multi = split_chronological_dataset(multi_df, multi_year_test_days=365)
    assert split_multi["split_mode"] == "multi_year_full_test_year"
    assert len(split_multi["test_dates"]) == 365
    test_months = {d.month for d in split_multi["test_dates"]}
    assert test_months == set(range(1, 13))

    # Single-year backward compat
    single_dates = pd.date_range("2023-01-15", "2023-12-30", freq="D")
    single_df = pd.DataFrame(
        {
            "grid_cell_id": "cell_16.00_72.00_0.25",
            "prediction_date_T": single_dates,
            "target_fishing_hours": 0.0,
        }
    )
    split_single = split_chronological_dataset(single_df)
    assert split_single["split_mode"] == "single_year_60_20_20"
    assert len(split_single["train_dates"]) == int(len(single_dates) * 0.60)


def test_probability_calibrator_bounds():
    """Both Isotonic and Platt calibrators produce bounded probabilities in [0, 1]."""
    rng = np.random.default_rng(11)
    raw_p = rng.uniform(0.01, 0.99, size=200)
    y = (raw_p > 0.65).astype(int)

    for method in ("isotonic", "platt"):
        cal = ProbabilityCalibrator(method=method).fit(raw_p, y)
        out = cal.predict_proba(np.array([0.0, 0.2, 0.5, 0.8, 1.0]))
        assert len(out) == 5
        assert np.all((out >= 0.0) & (out <= 1.0))


def test_phase4_artifact_consistency_and_inference_safety():
    """Verify frozen Phase 4 JSONs match one consistent run and SafetyGate overrides Phase 4 output."""
    assert PHASE4_METADATA_PATH.exists(), "Run serialize_phase4_artifacts.py before tests"
    assert PHASE4_FEATURES_PATH.exists()
    assert PHASE4_THRESHOLD_PATH.exists()
    assert PHASE4_RESULTS_PATH.exists()

    meta = json.loads(PHASE4_METADATA_PATH.read_text())
    feats = json.loads(PHASE4_FEATURES_PATH.read_text())
    thresh = json.loads(PHASE4_THRESHOLD_PATH.read_text())
    results = json.loads(PHASE4_RESULTS_PATH.read_text())

    assert meta["model_version"] == "Phase4_SpatioOcean_v1"
    assert meta["run_id"] == feats["run_id"] == thresh["run_id"] == results["run_id"]
    assert meta["decision_threshold"] == thresh["decision_threshold"]
    assert meta["test_metrics"] == results["benchmark_comparison"]["Phase4_SpatioOcean_v1"]["test"]
    assert validate_stage1_feature_purity(feats["stage1_features"])["status"] == "PASS"

    pipeline = Phase4InferencePipeline(demo_mode=True, prefer_phase4=True)
    pipeline.load_artifacts()
    assert pipeline._pipeline_mode == "phase4"
    preds = pipeline.predict()
    assert len(preds) >= 97
    assert all(0.0 <= p["predicted_apparent_fishing_probability"] <= 1.0 for p in preds)
    assert all(0.0 <= p["habitat_suitability_score"] <= 1.0 for p in preds)

    # Confirm SafetyGate independently overrides extreme Phase 4 ML probabilities
    now = datetime.now(timezone.utc)
    severe_warning = {
        "severity": "SEVERE",
        "valid_from": now - timedelta(hours=1),
        "valid_until": now + timedelta(hours=12),
        "description": "Cyclone warning",
    }
    high_cell = dict(preds[0])
    high_cell["predicted_apparent_fishing_probability"] = 0.99
    high_cell["predicted_apparent_fishing_binary"] = 1
    gated = SafetyGate(marine_warnings=[severe_warning]).apply([high_cell])
    assert gated[0]["safety_status"] == "UNSAFE"
    assert gated[0]["safety_override"] is True


def test_multiyear_seasonal_climatology_inference():
    """Verify multi-year demo inference anchors to matching calendar window rather than Dec-31 dead zones."""
    pipeline = Phase4InferencePipeline(demo_mode=True, prefer_phase4=True)
    pipeline.load_artifacts()
    preds = pipeline.predict()
    prov = pipeline.get_last_provenance()
    gfw_src = prov["sources"]["global_fishing_watch"]

    hist = pipeline._load_historical_context()
    if not hist.empty and hist["observation_date"].dt.year.nunique() >= 2:
        assert gfw_src["context_mode"] == "multiyear_seasonal_climatology"
        assert gfw_src["seasonal_anchor_date"] is not None
        assert preds[0]["prediction_mode"] == "seasonal_climatology"
        active = sum(p["predicted_apparent_fishing_binary"] for p in preds)
        assert active >= 10
        assert max(p["predicted_apparent_fishing_probability"] for p in preds) <= 0.75
    assert all(0.0 <= p["predicted_apparent_fishing_probability"] <= 1.0 for p in preds)
