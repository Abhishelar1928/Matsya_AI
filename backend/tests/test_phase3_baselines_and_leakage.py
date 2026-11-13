"""
Unit tests for Phase 3: Causal Dataset Builder, Data Leakage Validator, and Baselines.
"""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

from ml.features.causal_dataset import build_causal_dataset, FEATURE_COLUMNS
from ml.evaluation.leakage_validator import (
    validate_dataset_provenance,
    validate_temporal_splits,
    validate_preprocessing_isolation,
    DataLeakageError,
)
from ml.models.baselines import (
    RecentActivityBaseline,
    Trailing7DayHistoricalBaseline,
    SeasonalSpatialBaseline,
    compute_classification_metrics,
)


@pytest.fixture
def mock_raw_history(tmp_path):
    """Generates a small multi-day synthetic raw parquet to test causal properties."""
    dates = pd.date_range("2023-01-01", "2023-01-30")
    cells = ["cell_15.5_72.0", "cell_15.5_72.1"]
    
    records = []
    for c in cells:
        for d in dates:
            records.append({
                "grid_cell_id": c,
                "latitude": 15.5,
                "longitude": 72.0 if "72.0" in c else 72.1,
                "observation_date": d.strftime("%Y-%m-%d"),
                "fishing_hours": 5.0 if d.day % 2 == 0 else 0.0,
                "wave_height": 1.5,
                "wave_period": 8.0,
                "wave_direction": 180.0,
                "swell_wave_height": 1.0,
                "ocean_current_velocity": 0.5,
                "wind_speed": 15.0,
                "distance_to_coast_km": 30.0,
                "day_of_year": d.dayofyear,
            })
    df = pd.DataFrame(records)
    file_path = tmp_path / "mock_history.parquet"
    df.to_parquet(file_path)
    return file_path


def test_causal_dataset_target_alignment(mock_raw_history):
    """Verify target is strictly next calendar day T+1."""
    df = build_causal_dataset(mock_raw_history, lookback_days=7, gfw_lag_days=0)
    assert len(df) > 0
    
    # Check provenance
    prov = validate_dataset_provenance(df)
    assert prov["status"] == "PASS"
    
    # For day T=2023-01-10 (even day, effort=5.0), target T+1=2023-01-11 (odd day, effort=0.0)
    sample_even = df[(df["prediction_date_T"] == "2023-01-10") & (df["grid_cell_id"] == "cell_15.5_72.0")].iloc[0]
    assert sample_even["fishing_hours_recent"] == 5.0
    assert sample_even["target_fishing_hours"] == 0.0
    assert sample_even["target_date_T_plus_1"] == pd.Timestamp("2023-01-11")


def test_causal_isolation(tmp_path):
    """Test that modifying T+1 effort does NOT alter features computed at T."""
    dates = pd.date_range("2023-01-01", "2023-01-20")
    records1 = []
    records2 = []
    
    for d in dates:
        r1 = {
            "grid_cell_id": "cell_1",
            "latitude": 15.5,
            "longitude": 72.0,
            "observation_date": d.strftime("%Y-%m-%d"),
            "fishing_hours": 2.0,
            "distance_to_coast_km": 20.0,
            "day_of_year": d.dayofyear,
        }
        r2 = dict(r1)
        if d == pd.Timestamp("2023-01-15"):
            # Alter future day 15 effort in dataset 2
            r2["fishing_hours"] = 999.0
            
        records1.append(r1)
        records2.append(r2)
        
    p1 = tmp_path / "p1.parquet"
    p2 = tmp_path / "p2.parquet"
    pd.DataFrame(records1).to_parquet(p1)
    pd.DataFrame(records2).to_parquet(p2)
    
    df1 = build_causal_dataset(p1, lookback_days=5)
    df2 = build_causal_dataset(p2, lookback_days=5)
    
    # At prediction time T = 2023-01-14: features MUST BE IDENTICAL between df1 and df2!
    f1_t14 = df1[df1["prediction_date_T"] == "2023-01-14"][FEATURE_COLUMNS].iloc[0].to_dict()
    f2_t14 = df2[df2["prediction_date_T"] == "2023-01-14"][FEATURE_COLUMNS].iloc[0].to_dict()
    
    for k in FEATURE_COLUMNS:
        v1 = f1_t14[k]
        v2 = f2_t14[k]
        if pd.isna(v1) and pd.isna(v2):
            continue
        assert v1 == v2, f"Feature {k} at T was contaminated by future modification at T+1!"


def test_leakage_validator_detects_overlap():
    """Verify leakage validator raises DataLeakageError when splits overlap."""
    train_dates = pd.date_range("2023-01-01", "2023-01-10")
    val_dates = pd.date_range("2023-01-10", "2023-01-15")  # Overlaps on 2023-01-10!
    test_dates = pd.date_range("2023-01-16", "2023-01-20")
    
    with pytest.raises(DataLeakageError, match="Temporal Leakage: Train and Val overlap"):
        validate_temporal_splits(train_dates, val_dates, test_dates)


def test_leakage_validator_detects_inverted_chronology():
    """Verify leakage validator rejects future-to-past ordering."""
    train_dates = pd.date_range("2023-01-15", "2023-01-20")
    val_dates = pd.date_range("2023-01-01", "2023-01-10")  # Earlier than train!
    test_dates = pd.date_range("2023-01-21", "2023-01-25")
    
    with pytest.raises(DataLeakageError, match="Temporal Ordering Violation"):
        validate_temporal_splits(train_dates, val_dates, test_dates)


def test_baselines_execution(mock_raw_history):
    """Test all three baselines calculate valid scores and metrics."""
    df = build_causal_dataset(mock_raw_history, lookback_days=7)
    
    # 1. Recent Activity Baseline
    b_recent = RecentActivityBaseline(threshold_hours=1.0)
    res_recent = b_recent.evaluate(df)
    assert "pr_auc" in res_recent
    assert "f1" in res_recent
    assert 0.0 <= res_recent["pr_auc"] <= 1.0
    
    # 2. 7-Day Trailing Baseline
    b_7d = Trailing7DayHistoricalBaseline(threshold_hours=1.0)
    res_7d = b_7d.evaluate(df)
    assert "pr_auc" in res_7d
    assert "f1" in res_7d
    
    # 3. Seasonal Spatial Baseline
    b_spatial = SeasonalSpatialBaseline(threshold_hours=1.0)
    b_spatial.fit(df.iloc[:20])
    res_spatial = b_spatial.evaluate(df.iloc[20:])
    assert "pr_auc" in res_spatial
    assert "f1" in res_spatial


def test_preprocessing_isolation_check():
    """Verify preprocessor isolation catches leaking test set moments."""
    from sklearn.impute import SimpleImputer
    from sklearn.preprocessing import StandardScaler
    
    X_train = pd.DataFrame({
        "feat1": [1.0, 2.0, 3.0, np.nan],
        "feat2": [10.0, 20.0, 30.0, 40.0]
    })
    
    # Correctly fitted on train
    imp = SimpleImputer(strategy="median")
    scaler = StandardScaler()
    imp.fit(X_train[["feat1", "feat2"]])
    scaler.fit(imp.transform(X_train[["feat1", "feat2"]]))
    
    # Should pass
    res = validate_preprocessing_isolation(imp, scaler, X_train, ["feat1", "feat2"])
    assert res["status"] == "PASS"
    
    # Leaked imputer (fitted on contaminated data)
    X_leaked = pd.DataFrame({
        "feat1": [100.0, 200.0, 300.0, 400.0],
        "feat2": [10.0, 20.0, 30.0, 40.0]
    })
    imp_leaked = SimpleImputer(strategy="median")
    imp_leaked.fit(X_leaked[["feat1", "feat2"]])
    with pytest.raises(DataLeakageError, match="Imputer statistics do NOT match"):
        validate_preprocessing_isolation(imp_leaked, scaler, X_train, ["feat1", "feat2"])

