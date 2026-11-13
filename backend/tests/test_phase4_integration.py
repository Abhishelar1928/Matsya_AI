"""
MatsyaAI Maharashtra — Phase 4 Integration and Verification Test Suite.

Tests:
1. Feature schema compatibility with validated Phase 3 model.
2. Real-time prediction generation (171 canonical cells, probabilities in [0, 1]).
3. Strict target interpretation and user-facing terminology.
4. Independent safety gate decoupling (ML high probability cannot override rough sea/warnings).
5. INCOIS PFZ integration and status handling.
6. Map summary API endpoint contract and demo fallback mode.
"""

import pytest
from datetime import datetime, timezone, timedelta
import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.ml.inference import Phase4InferencePipeline, get_inference_pipeline
from backend.app.ml.safety_gate import SafetyGate
from ml.features.causal_dataset import FEATURE_COLUMNS


@pytest.fixture
def inference_pipeline():
    pipeline = Phase4InferencePipeline(demo_mode=True)
    pipeline.load_artifacts()
    return pipeline


def test_feature_schema_compatibility(inference_pipeline):
    """Verify inference pipeline feature columns match Phase 3 training schema exactly."""
    expected_features = inference_pipeline._feature_columns
    assert len(expected_features) == 29
    assert expected_features == FEATURE_COLUMNS
    assert "target_fishing_hours" not in expected_features
    assert "fishing_hours" not in expected_features


def test_prediction_generation_and_terminology(inference_pipeline):
    """Verify predictions generated for all 171 cells with strict terminology."""
    predictions = inference_pipeline.predict()
    assert len(predictions) == 171

    first = predictions[0]
    # Required keys
    assert "grid_cell_id" in first
    assert "latitude" in first
    assert "longitude" in first
    assert "predicted_apparent_fishing_probability" in first
    assert "predicted_apparent_fishing_binary" in first
    assert "prediction_label" in first
    assert "target_interpretation" in first
    assert "decision_threshold" in first
    assert "model_version" in first
    assert "disclaimer" in first

    # Probability bounds
    probs = [p["predicted_apparent_fishing_probability"] for p in predictions]
    assert all(0.0 <= pr <= 1.0 for pr in probs)

    # Decision threshold check
    decision_thresh = first["decision_threshold"]
    assert decision_thresh == 0.47
    for p in predictions:
        expected_binary = 1 if p["predicted_apparent_fishing_probability"] >= decision_thresh else 0
        assert p["predicted_apparent_fishing_binary"] == expected_binary

    # Strict terminology validation
    valid_labels = [
        "High predicted apparent fishing activity",
        "Low predicted apparent fishing activity",
    ]
    assert all(p["prediction_label"] in valid_labels for p in predictions)
    assert first["target_interpretation"] == "next-calendar-day apparent fishing activity (>1.0 fishing hours)"

    # Forbidden terminology check
    for p in predictions:
        text = (p["prediction_label"] + " " + p["target_interpretation"]).lower()
        assert "fish biomass" not in text
        assert "guaranteed catch" not in text
        assert "fish presence" not in text
        assert "abundance" not in text


def test_safety_gate_decoupling():
    """Verify ML predictions never determine safety."""
    # Mock prediction with high apparent fishing probability (0.95)
    high_fishing_pred = {
        "grid_cell_id": "cell_1",
        "predicted_apparent_fishing_probability": 0.95,
        "predicted_apparent_fishing_binary": 1,
        "current_wave_height_m": 4.5,  # Exceeds 4.0m safety threshold
        "current_wind_speed_kmh": 25.0,
    }

    gate = SafetyGate(marine_warnings=[])
    result = gate.apply([high_fishing_pred])
    # Even though fishing is high, rough sea MUST produce CAUTION, NEVER SAFE
    assert result[0]["safety_status"] == "CAUTION"

    # Test Case 2: Severe warning active
    now = datetime.now(timezone.utc)
    severe_warning = {
        "severity": "SEVERE",
        "valid_from": now - timedelta(hours=1),
        "valid_until": now + timedelta(hours=24),
        "description": "Cyclone warning",
    }
    gate_severe = SafetyGate(marine_warnings=[severe_warning])
    high_fishing_calm = {
        "grid_cell_id": "cell_2",
        "predicted_apparent_fishing_probability": 0.99,
        "predicted_apparent_fishing_binary": 1,
        "current_wave_height_m": 1.0,
        "current_wind_speed_kmh": 10.0,
    }
    res_severe = gate_severe.apply([high_fishing_calm])
    assert res_severe[0]["safety_status"] == "UNSAFE"
    assert res_severe[0]["safety_override"] is True

    # Test Case 3: No warning data available
    gate_empty = SafetyGate(marine_warnings=[])
    calm_cell = {
        "grid_cell_id": "cell_3",
        "predicted_apparent_fishing_probability": 0.80,
        "predicted_apparent_fishing_binary": 1,
        "current_wave_height_m": 1.0,
        "current_wind_speed_kmh": 10.0,
    }
    res_empty = gate_empty.apply([calm_cell])
    # Must be NO_WARNING_DATA, NEVER SAFE
    assert res_empty[0]["safety_status"] == "NO_WARNING_DATA"


def test_map_summary_api_endpoint():
    """Verify GET /api/v1/map/summary contract."""
    from unittest.mock import patch
    
    mock_preds = []
    # Create 171 mock predictions as if from DB
    for i in range(171):
        mock_preds.append({
            "grid_cell_id": f"cell_{i}",
            "latitude": 15.0,
            "longitude": 73.0,
            "distance_to_coast_km": 10.0,
            "is_coastal": True,
            "predicted_apparent_fishing_probability": 0.9,
            "predicted_apparent_fishing_binary": 1,
            "prediction_label": "High predicted apparent fishing activity",
            "target_interpretation": "next-calendar-day apparent fishing activity (>1.0 fishing hours)",
            "decision_threshold": 0.47,
            "model_version": "Phase3_XGBoost_v1",
            "prediction_timestamp": "2023-12-31T00:00:00Z",
            "data_freshness_status": "LIVE",
            "disclaimer": "Predictions indicate apparent fishing activity derived from historical vessel tracking patterns. Matsya AI does NOT predict fish presence, biomass, species abundance, or guaranteed catch.",
            "current_wave_height_m": None,
            "current_wind_speed_kmh": None,
            "safety_status": "SAFE_CONFIRMED",
            "safety_override": False,
        })

    with patch("backend.app.api.v1.map.fetch_latest_persisted_predictions", autospec=True) as mock_fetch:
        # It's an async function, we need to return an async result
        async def mock_async_fetch(*args, **kwargs):
            return mock_preds
        mock_fetch.side_effect = mock_async_fetch

        client = TestClient(app)
        response = client.get("/api/v1/map/summary?demo=true")
        assert response.status_code == 200
    
        data = response.json()
        assert "metadata" in data
        assert "marine_safety" in data
        assert "predictions" in data
        assert "pfz_advisory" in data
        assert "landing_centres" in data

    # Metadata check
    assert data["metadata"]["model_version"] == "Phase3_XGBoost_v1"
    assert data["metadata"]["demo_mode"] is True
    assert "fish biomass" not in data["metadata"]["disclaimer"].lower()

    # Predictions check
    assert len(data["predictions"]) == 171
    assert len(data["landing_centres"]) >= 8

    # Safety check
    assert data["marine_safety"]["independent_of_ml"] is True
    assert data["marine_safety"]["overall_status"] in ["SAFE_CONFIRMED", "CAUTION", "UNSAFE", "NO_WARNING_DATA"]


def test_predictions_latest_endpoint():
    """Verify GET /api/v1/predictions/latest contract."""
    from unittest.mock import patch
    
    mock_preds = []
    # Create 171 mock predictions as if from DB
    for i in range(171):
        mock_preds.append({
            "grid_cell_id": f"cell_{i}",
            "latitude": 15.0,
            "longitude": 73.0,
            "distance_to_coast_km": 10.0,
            "is_coastal": True,
            "predicted_apparent_fishing_probability": 0.9,
            "predicted_apparent_fishing_binary": 1,
            "prediction_label": "High predicted apparent fishing activity",
            "target_interpretation": "next-calendar-day apparent fishing activity (>1.0 fishing hours)",
            "decision_threshold": 0.47,
            "model_version": "Phase3_XGBoost_v1",
            "prediction_timestamp": "2023-12-31T00:00:00Z",
            "data_freshness_status": "LIVE",
            "disclaimer": "Predictions indicate apparent fishing activity derived from historical vessel tracking patterns. Matsya AI does NOT predict fish presence, biomass, species abundance, or guaranteed catch.",
            "current_wave_height_m": None,
            "current_wind_speed_kmh": None,
            "safety_status": "SAFE_CONFIRMED",
            "safety_override": False,
        })

    with patch("backend.app.api.v1.predictions.fetch_latest_persisted_predictions", autospec=True) as mock_fetch:
        async def mock_async_fetch(*args, **kwargs):
            return mock_preds
        mock_fetch.side_effect = mock_async_fetch

        client = TestClient(app)
        response = client.get("/api/v1/predictions/latest?demo=true")
        assert response.status_code == 200
        preds = response.json()
        assert isinstance(preds, list)
        assert len(preds) == 171
        assert preds[0]["model_version"] == "Phase3_XGBoost_v1"


def test_pfz_latest_endpoint():
    """Verify GET /api/v1/pfz/latest contract in both demo and live/fallback modes."""
    client = TestClient(app)
    
    # 1. Demo mode
    resp_demo = client.get("/api/v1/pfz/latest?demo=true")
    assert resp_demo.status_code == 200
    data_demo = resp_demo.json()
    assert data_demo["source"] == "INCOIS"
    assert data_demo["status"] == "DEMO_HISTORICAL"
    assert data_demo["count"] == 3
    assert len(data_demo["locations"]) == 3
    
    # 2. Live/offline mode (gracefully returns UNAVAILABLE when db is unpopulated/unreachable)
    resp_live = client.get("/api/v1/pfz/latest?demo=false")
    assert resp_live.status_code == 200
    data_live = resp_live.json()
    assert data_live["status"] in ["LIVE", "STALE", "UNAVAILABLE"]


def test_stale_warning_never_safe():
    """Verify expired/stale warnings NEVER result in SAFE_CONFIRMED."""
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    expired_time = now - timedelta(days=5)
    
    stale_warning = {
        "severity": "SEVERE",
        "valid_from": expired_time - timedelta(days=1),
        "valid_until": expired_time,
        "description": "Old expired warning",
    }
    gate = SafetyGate(marine_warnings=[stale_warning])
    
    pred = {
        "grid_cell_id": "cell_stale_test",
        "predicted_apparent_fishing_probability": 0.90,
        "current_wave_height_m": 1.0,
        "current_wind_speed_kmh": 10.0,
    }
    res = gate.apply([pred])
    assert res[0]["safety_status"] == "NO_WARNING_DATA"
    assert res[0]["safety_status"] != "SAFE_CONFIRMED"

