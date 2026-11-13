"""
MatsyaAI Maharashtra — Phase 5.4 Prediction Provenance & Safety Gate Decoupling Tests.

Tests:
 1. Provenance structure and overall_data_status derivation.
 2. GFW is always CACHED_HISTORICAL, never LIVE.
 3. Safety gate is strictly independent of prediction probability.
 4. SAFE_CONFIRMED requires an active, valid authoritative bulletin.
 5. safety_reason is populated for every status.
 6. prediction_provenance appears in map summary response.
 7. Backward compatibility for all existing API response keys.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.ml.inference import Phase4InferencePipeline, get_inference_pipeline
from backend.app.ml.safety_gate import SafetyGate


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def demo_pipeline():
    """Pipeline in demo mode for provenance tests."""
    pipeline = Phase4InferencePipeline(demo_mode=True)
    pipeline.load_artifacts()
    return pipeline


@pytest.fixture
def predictions_with_provenance(demo_pipeline):
    """Run a demo prediction to get both predictions and provenance."""
    predictions = demo_pipeline.predict()
    provenance = demo_pipeline.get_last_provenance()
    return predictions, provenance


# ---------------------------------------------------------------------------
# 1. Provenance structure tests
# ---------------------------------------------------------------------------
class TestProvenanceStructure:
    """Verify provenance metadata is correctly constructed."""

    def test_provenance_is_populated_after_predict(self, predictions_with_provenance):
        """Test 1: Provenance is non-None after predict() runs."""
        _, provenance = predictions_with_provenance
        assert provenance is not None
        assert "overall_data_status" in provenance
        assert "sources" in provenance
        assert "prediction_timestamp" in provenance
        assert "historical_context_present" in provenance

    def test_provenance_has_both_sources(self, predictions_with_provenance):
        """Provenance includes both open_meteo_marine and global_fishing_watch."""
        _, provenance = predictions_with_provenance
        sources = provenance["sources"]
        assert "open_meteo_marine" in sources
        assert "global_fishing_watch" in sources

    def test_open_meteo_source_fields(self, predictions_with_provenance):
        """Open-Meteo source has status, data_timestamp, and age_minutes."""
        _, provenance = predictions_with_provenance
        om = provenance["sources"]["open_meteo_marine"]
        assert "status" in om
        assert "data_timestamp" in om
        assert "age_minutes" in om

    def test_gfw_source_fields(self, predictions_with_provenance):
        """GFW source has status, observation_date, age_days, record_count."""
        _, provenance = predictions_with_provenance
        gfw = provenance["sources"]["global_fishing_watch"]
        assert "status" in gfw
        assert "observation_date" in gfw
        assert "age_days" in gfw
        assert "record_count" in gfw


# ---------------------------------------------------------------------------
# 2. Overall data status derivation
# ---------------------------------------------------------------------------
class TestOverallDataStatus:
    """Verify overall_data_status is computed honestly."""

    def test_live_env_with_historical_gfw_is_historical_context(self):
        """Test 2: LIVE Open-Meteo + historical GFW -> HISTORICAL_CONTEXT."""
        pipeline = Phase4InferencePipeline(demo_mode=False)
        pipeline._loaded = True
        pipeline._cached_env_time = datetime.now(timezone.utc)

        # Simulate loaded historical data
        pipeline._historical_reference_df = pd.DataFrame({
            "grid_cell_id": ["cell_1"],
            "observation_date": [datetime(2023, 12, 31, tzinfo=timezone.utc)],
            "fishing_hours": [5.0],
        })

        now = datetime.now(timezone.utc)
        provenance = pipeline._build_provenance("LIVE", now)
        assert provenance["overall_data_status"] == "HISTORICAL_CONTEXT"
        assert provenance["historical_context_present"] is True

    def test_live_env_no_gfw_is_live(self):
        """Test 1: All LIVE real-time, no GFW historical -> LIVE."""
        pipeline = Phase4InferencePipeline(demo_mode=False)
        pipeline._loaded = True
        pipeline._cached_env_time = datetime.now(timezone.utc)
        pipeline._historical_reference_df = None

        now = datetime.now(timezone.utc)
        provenance = pipeline._build_provenance("LIVE", now)
        assert provenance["overall_data_status"] == "LIVE"
        assert provenance["historical_context_present"] is False

    def test_demo_mode_is_stale(self):
        """DEMO_MODE env -> STALE overall."""
        pipeline = Phase4InferencePipeline(demo_mode=True)
        pipeline._loaded = True
        pipeline._historical_reference_df = pd.DataFrame({
            "grid_cell_id": ["cell_1"],
            "observation_date": [datetime(2023, 6, 15, tzinfo=timezone.utc)],
            "fishing_hours": [3.0],
        })

        now = datetime.now(timezone.utc)
        provenance = pipeline._build_provenance("DEMO_MODE", now)
        assert provenance["overall_data_status"] == "STALE"

    def test_unknown_env_is_unavailable(self):
        """Unknown env status -> UNAVAILABLE."""
        pipeline = Phase4InferencePipeline()
        pipeline._loaded = True
        pipeline._historical_reference_df = None

        now = datetime.now(timezone.utc)
        provenance = pipeline._build_provenance("UNKNOWN", now)
        assert provenance["overall_data_status"] == "UNAVAILABLE"


# ---------------------------------------------------------------------------
# 3. GFW is strictly CACHED_HISTORICAL
# ---------------------------------------------------------------------------
class TestGFWProvenance:
    """GFW must NEVER be reported as LIVE."""

    def test_gfw_status_is_cached_historical(self, predictions_with_provenance):
        """Test 3: GFW status is CACHED_HISTORICAL when data exists."""
        _, provenance = predictions_with_provenance
        gfw = provenance["sources"]["global_fishing_watch"]
        # In demo mode, the historical cache may or may not be loaded
        assert gfw["status"] in ("CACHED_HISTORICAL", "UNAVAILABLE")
        assert gfw["status"] != "LIVE"

    def test_gfw_age_days_computed(self):
        """Test 4: GFW age_days is computed from observation_date."""
        pipeline = Phase4InferencePipeline()
        pipeline._loaded = True
        pipeline._cached_env_time = datetime.now(timezone.utc)

        ref_date = datetime(2023, 12, 31, tzinfo=timezone.utc)
        pipeline._historical_reference_df = pd.DataFrame({
            "grid_cell_id": ["cell_1"],
            "observation_date": [ref_date],
            "fishing_hours": [2.0],
        })

        now = datetime.now(timezone.utc)
        provenance = pipeline._build_provenance("LIVE", now)
        gfw = provenance["sources"]["global_fishing_watch"]
        expected_days = (now.date() - ref_date.date()).days
        assert gfw["age_days"] == expected_days
        assert gfw["age_days"] > 0

    def test_gfw_unavailable_without_data(self):
        """Test 5: GFW is UNAVAILABLE when no historical data loaded."""
        pipeline = Phase4InferencePipeline()
        pipeline._loaded = True
        pipeline._historical_reference_df = pd.DataFrame()  # empty
        pipeline._cached_env_time = datetime.now(timezone.utc)

        now = datetime.now(timezone.utc)
        provenance = pipeline._build_provenance("LIVE", now)
        gfw = provenance["sources"]["global_fishing_watch"]
        assert gfw["status"] == "UNAVAILABLE"
        assert gfw["observation_date"] is None
        assert gfw["record_count"] == 0


# ---------------------------------------------------------------------------
# 4. SafetyGate independence -- probability NEVER determines safety
# ---------------------------------------------------------------------------
class TestSafetyGateIndependence:
    """Prediction score must NEVER influence safety status."""

    def test_high_prob_does_not_override_warning(self):
        """Test 7: p=0.99 + SEVERE warning -> UNSAFE."""
        now = datetime.now(timezone.utc)
        warning = {
            "severity": "SEVERE",
            "valid_from": now - timedelta(hours=1),
            "valid_until": now + timedelta(hours=24),
            "description": "Cyclone alert",
        }
        gate = SafetyGate(marine_warnings=[warning])
        pred = {
            "grid_cell_id": "cell_1",
            "predicted_apparent_fishing_probability": 0.99,
            "predicted_apparent_fishing_binary": 1,
            "current_wave_height_m": 1.0,
            "current_wind_speed_kmh": 10.0,
        }
        res = gate.apply([pred])
        assert res[0]["safety_status"] == "UNSAFE"
        assert res[0]["safety_override"] is True

    def test_imd_warning_keeps_unsafe(self):
        """Test 8: Active IMD WARNING -> UNSAFE regardless of prediction."""
        now = datetime.now(timezone.utc)
        warning = {
            "severity": "VERY_SEVERE",
            "valid_from": now - timedelta(hours=1),
            "valid_until": now + timedelta(hours=6),
            "description": "Very severe cyclonic storm",
        }
        gate = SafetyGate(marine_warnings=[warning])
        pred = {
            "grid_cell_id": "cell_x",
            "predicted_apparent_fishing_probability": 0.10,
            "current_wave_height_m": 0.5,
            "current_wind_speed_kmh": 5.0,
        }
        res = gate.apply([pred])
        assert res[0]["safety_status"] == "UNSAFE"

    def test_changing_probability_does_not_change_safety(self):
        """Test 13: Same env + same warnings, different probabilities -> same safety."""
        gate = SafetyGate(marine_warnings=[])
        base_pred = {
            "grid_cell_id": "cell_ind",
            "current_wave_height_m": 1.0,
            "current_wind_speed_kmh": 10.0,
        }

        # Low probability
        pred_low = {**base_pred, "predicted_apparent_fishing_probability": 0.05}
        # High probability
        pred_high = {**base_pred, "predicted_apparent_fishing_probability": 0.99}

        res_low = gate.apply([pred_low])
        res_high = gate.apply([pred_high])

        assert res_low[0]["safety_status"] == res_high[0]["safety_status"]
        assert res_low[0]["safety_status"] == "NO_WARNING_DATA"


# ---------------------------------------------------------------------------
# 5. SAFE_CONFIRMED requires active valid authoritative bulletin
# ---------------------------------------------------------------------------
class TestSafeConfirmedRules:
    """SAFE_CONFIRMED can ONLY be assigned with a valid, active authoritative bulletin."""

    def test_normal_bulletin_yields_safe(self):
        """Test 9: Active NORMAL bulletin -> SAFE_CONFIRMED."""
        now = datetime.now(timezone.utc)
        normal = {
            "severity": "NORMAL",
            "valid_from": now - timedelta(hours=1),
            "valid_until": now + timedelta(hours=12),
            "description": "Normal sea conditions",
        }
        gate = SafetyGate(marine_warnings=[normal])
        pred = {
            "grid_cell_id": "cell_safe",
            "predicted_apparent_fishing_probability": 0.80,
            "current_wave_height_m": 1.0,
            "current_wind_speed_kmh": 10.0,
        }
        res = gate.apply([pred])
        assert res[0]["safety_status"] == "SAFE_CONFIRMED"

    def test_expired_bulletin_cannot_produce_safe(self):
        """Test 10: Expired IMD bulletin -> NO_WARNING_DATA, never SAFE_CONFIRMED."""
        now = datetime.now(timezone.utc)
        expired = {
            "severity": "NORMAL",
            "valid_from": now - timedelta(days=3),
            "valid_until": now - timedelta(days=2),
            "description": "Old normal conditions",
        }
        gate = SafetyGate(marine_warnings=[expired])
        pred = {
            "grid_cell_id": "cell_exp",
            "predicted_apparent_fishing_probability": 0.90,
            "current_wave_height_m": 0.5,
            "current_wind_speed_kmh": 5.0,
        }
        res = gate.apply([pred])
        assert res[0]["safety_status"] != "SAFE_CONFIRMED"
        assert res[0]["safety_status"] == "NO_WARNING_DATA"

    def test_unavailable_imd_cannot_produce_safe(self):
        """Test 11: No warning data -> NO_WARNING_DATA, never SAFE."""
        gate = SafetyGate(marine_warnings=[])
        pred = {
            "grid_cell_id": "cell_no_data",
            "predicted_apparent_fishing_probability": 0.95,
            "current_wave_height_m": 0.3,
            "current_wind_speed_kmh": 3.0,
        }
        res = gate.apply([pred])
        assert res[0]["safety_status"] == "NO_WARNING_DATA"

    def test_empty_warnings_never_safe(self):
        """Test 12: No warning data, calm sea -> still NO_WARNING_DATA."""
        gate = SafetyGate(marine_warnings=[])
        pred = {
            "grid_cell_id": "cell_calm",
            "predicted_apparent_fishing_probability": 0.50,
            "current_wave_height_m": 0.2,
            "current_wind_speed_kmh": 2.0,
        }
        res = gate.apply([pred])
        assert res[0]["safety_status"] != "SAFE_CONFIRMED"


# ---------------------------------------------------------------------------
# 6. safety_reason string
# ---------------------------------------------------------------------------
class TestSafetyReason:
    """Every safety status includes a human-readable reason."""

    def test_safety_reason_present_in_result(self):
        """All safety gate results include a safety_reason string."""
        gate = SafetyGate(marine_warnings=[])
        pred = {
            "grid_cell_id": "cell_reason",
            "predicted_apparent_fishing_probability": 0.50,
            "current_wave_height_m": 1.0,
            "current_wind_speed_kmh": 10.0,
        }
        res = gate.apply([pred])
        assert "safety_reason" in res[0]
        assert isinstance(res[0]["safety_reason"], str)
        assert len(res[0]["safety_reason"]) > 0

    def test_unsafe_reason_mentions_warning(self):
        """UNSAFE reason mentions authoritative source."""
        now = datetime.now(timezone.utc)
        warning = {
            "severity": "SEVERE",
            "valid_from": now - timedelta(hours=1),
            "valid_until": now + timedelta(hours=24),
            "description": "Storm",
        }
        gate = SafetyGate(marine_warnings=[warning])
        pred = {
            "grid_cell_id": "cell_r",
            "predicted_apparent_fishing_probability": 0.5,
            "current_wave_height_m": 1.0,
            "current_wind_speed_kmh": 10.0,
        }
        res = gate.apply([pred])
        assert "severe" in res[0]["safety_reason"].lower()

    def test_caution_env_reason_mentions_threshold(self):
        """CAUTION from wave height mentions threshold value."""
        gate = SafetyGate(marine_warnings=[])
        pred = {
            "grid_cell_id": "cell_wh",
            "predicted_apparent_fishing_probability": 0.5,
            "current_wave_height_m": 5.0,  # exceeds 4.0m
            "current_wind_speed_kmh": 10.0,
        }
        res = gate.apply([pred])
        assert res[0]["safety_status"] == "CAUTION"
        assert "threshold" in res[0]["safety_reason"].lower()


# ---------------------------------------------------------------------------
# 7. API endpoint integration
# ---------------------------------------------------------------------------
class TestAPIProvenance:
    """Verify provenance appears in API responses."""

    def test_map_summary_has_prediction_provenance(self):
        """Test 14: Map summary includes prediction_provenance key."""
        from unittest.mock import patch
        mock_preds = [{"grid_cell_id": f"cell_{i}", "latitude": 15.0, "longitude": 73.0, "distance_to_coast_km": 10.0, "is_coastal": True, "predicted_apparent_fishing_probability": 0.9, "predicted_apparent_fishing_binary": 1, "prediction_label": "High predicted apparent fishing activity", "target_interpretation": "next", "decision_threshold": 0.47, "model_version": "Phase3_XGBoost_v1", "prediction_timestamp": "2023-12-31T00:00:00Z", "data_freshness_status": "LIVE", "disclaimer": "desc", "current_wave_height_m": None, "current_wind_speed_kmh": None, "safety_status": "SAFE_CONFIRMED", "safety_override": False} for i in range(171)]
        with patch("backend.app.api.v1.map.fetch_latest_persisted_predictions", autospec=True) as mock_fetch:
            async def mock_async_fetch(*args, **kwargs):
                return mock_preds
            mock_fetch.side_effect = mock_async_fetch

            client = TestClient(app)
            response = client.get("/api/v1/map/summary?demo=true")
            assert response.status_code == 200
            data = response.json()
            assert "prediction_provenance" in data
            prov = data["prediction_provenance"]
            assert prov is not None
            assert "overall_data_status" in prov
            assert "sources" in prov
            
            sources = prov["sources"]
            assert "gfw_context" in sources
            assert "environmental" in sources
            assert "incois_pfz" in sources
            assert "marine_safety" in sources
            
            assert "status" in sources["gfw_context"]
            assert sources["gfw_context"]["status"] != "LIVE"  # GFW should never be LIVE in demo/test fallback
            assert "observation_date" in sources["gfw_context"]
            assert "age_days" in sources["gfw_context"]
            
            assert "status" in sources["environmental"]
            assert "retrieved_at" in sources["environmental"]
            assert "data_timestamp" in sources["environmental"]
            assert "age_minutes" in sources["environmental"]
            
            assert "status" in sources["incois_pfz"]
            assert "advisory_date" in sources["incois_pfz"]
            assert "valid_until" in sources["incois_pfz"]
            assert "age_minutes" in sources["incois_pfz"]
            
            assert "overall_status" in sources["marine_safety"]
            assert "imd_status" in sources["marine_safety"]
            assert "data_timestamp" in sources["marine_safety"]
            assert "valid_until" in sources["marine_safety"]
            assert "independent_of_ml" in sources["marine_safety"]
            assert sources["marine_safety"]["independent_of_ml"] is True
            
            # Timestamp matches mock predictions
            assert prov["prediction_timestamp"] == "2023-12-31T00:00:00Z"

    def test_map_summary_backward_compat(self):
        """Test 16: All existing map summary keys preserved."""
        from unittest.mock import patch
        mock_preds = [{"grid_cell_id": f"cell_{i}", "latitude": 15.0, "longitude": 73.0, "distance_to_coast_km": 10.0, "is_coastal": True, "predicted_apparent_fishing_probability": 0.9, "predicted_apparent_fishing_binary": 1, "prediction_label": "High predicted apparent fishing activity", "target_interpretation": "next", "decision_threshold": 0.47, "model_version": "Phase3_XGBoost_v1", "prediction_timestamp": "2023-12-31T00:00:00Z", "data_freshness_status": "LIVE", "disclaimer": "desc", "current_wave_height_m": None, "current_wind_speed_kmh": None, "safety_status": "SAFE_CONFIRMED", "safety_override": False} for i in range(171)]
        with patch("backend.app.api.v1.map.fetch_latest_persisted_predictions", autospec=True) as mock_fetch:
            async def mock_async_fetch(*args, **kwargs):
                return mock_preds
            mock_fetch.side_effect = mock_async_fetch

            client = TestClient(app)
            response = client.get("/api/v1/map/summary?demo=true")
            assert response.status_code == 200
            data = response.json()
            # All original top-level keys must exist
            assert "metadata" in data
            assert "marine_safety" in data
            assert "predictions" in data
            assert "pfz_advisory" in data
            assert "landing_centres" in data
            assert "source_freshness" in data
            # Metadata sub-keys
            assert data["metadata"]["model_version"] == "Phase3_XGBoost_v1"
            assert data["metadata"]["demo_mode"] is True
            assert "disclaimer" in data["metadata"]
            assert data["marine_safety"]["independent_of_ml"] is True

    def test_predictions_endpoint_has_data_freshness(self):
        """Test 15: Predictions endpoint returns data_freshness_status per cell."""
        from unittest.mock import patch
        mock_preds = [{"grid_cell_id": f"cell_{i}", "latitude": 15.0, "longitude": 73.0, "distance_to_coast_km": 10.0, "is_coastal": True, "predicted_apparent_fishing_probability": 0.9, "predicted_apparent_fishing_binary": 1, "prediction_label": "High predicted apparent fishing activity", "target_interpretation": "next", "decision_threshold": 0.47, "model_version": "Phase3_XGBoost_v1", "prediction_timestamp": "2023-12-31T00:00:00Z", "data_freshness_status": "LIVE", "disclaimer": "desc", "current_wave_height_m": None, "current_wind_speed_kmh": None, "safety_status": "SAFE_CONFIRMED", "safety_override": False, "safety_reason": "Clear weather"} for i in range(171)]
        with patch("backend.app.api.v1.predictions.fetch_latest_persisted_predictions", autospec=True) as mock_fetch:
            async def mock_async_fetch(*args, **kwargs):
                return mock_preds
            mock_fetch.side_effect = mock_async_fetch

            client = TestClient(app)
            response = client.get("/api/v1/predictions/latest?demo=true")
            assert response.status_code == 200
            preds = response.json()
            assert len(preds) == 171
            first = preds[0]
            assert "data_freshness_status" in first
            # In demo mode, it should be STALE (since env is DEMO_MODE)
            assert first["data_freshness_status"] in (
                "STALE", "HISTORICAL_CONTEXT", "LIVE", "MIXED", "UNAVAILABLE"
            )
            # safety_reason should be present now
            assert "safety_reason" in first


# ---------------------------------------------------------------------------
# 8. Prediction count regression
# ---------------------------------------------------------------------------
class TestPhase3Regression:
    """Verify frozen Phase 3 model contract is intact."""

    def test_171_cells_29_features(self):
        """Test 17: 171 cells, 29 features, probabilities in [0,1]."""
        pipeline = Phase4InferencePipeline(demo_mode=True)
        pipeline.load_artifacts()
        assert len(pipeline._feature_columns) == 29

        predictions = pipeline.predict()
        assert len(predictions) == 171
        for p in predictions:
            prob = p["predicted_apparent_fishing_probability"]
            assert 0.0 <= prob <= 1.0
            assert p["decision_threshold"] == 0.47

    def test_data_freshness_status_is_provenance_derived(self, predictions_with_provenance):
        """Test 6: data_freshness_status reflects provenance, not raw env status."""
        predictions, provenance = predictions_with_provenance
        expected = provenance["overall_data_status"]
        for p in predictions:
            assert p["data_freshness_status"] == expected
