"""
Phase 6 End-to-End Safety Gate Verification Tests.

Covers exact invariants:
CASE A: Current authoritative marine warning says NORMAL/Nil AND conditions verified -> SAFE_CONFIRMED.
CASE B: Marine warning data is missing -> NEVER SAFE_CONFIRMED (NO_WARNING_DATA).
CASE C: Marine warning data is stale/expired -> NEVER SAFE_CONFIRMED.
CASE D: IMD warning exists AND fishing prediction HIGH -> WARNING remains dominant.
CASE E: Fishing prediction is LOW AND warning exists -> WARNING remains visible.
CASE F: GFW historical activity is high -> Must NOT imply current safe fishing conditions.
CASE G: Any source is unavailable -> Do not silently convert to SAFE.
"""

import pytest
from datetime import datetime, timezone, timedelta
from backend.app.ml.safety_gate import SafetyGate

def test_case_a_normal_warning():
    """CASE A: NORMAL/Nil warning -> SAFE_CONFIRMED."""
    now = datetime.now(timezone.utc)
    normal_warning = {
        "severity": "NORMAL",
        "valid_from": now - timedelta(hours=1),
        "valid_until": now + timedelta(hours=23),
        "description": "Nil warning"
    }
    gate = SafetyGate(marine_warnings=[normal_warning])
    
    calm_pred = {
        "grid_cell_id": "cell_1",
        "predicted_apparent_fishing_probability": 0.5,
        "current_wave_height_m": 1.0,
        "current_wind_speed_kmh": 10.0,
    }
    res = gate.apply([calm_pred])
    assert res[0]["safety_status"] == "SAFE_CONFIRMED"
    assert res[0]["safety_override"] is False


def test_case_b_missing_warning():
    """CASE B: Marine warning data is missing -> NEVER SAFE_CONFIRMED."""
    gate = SafetyGate(marine_warnings=[])
    
    calm_pred = {
        "grid_cell_id": "cell_1",
        "predicted_apparent_fishing_probability": 0.5,
        "current_wave_height_m": 1.0,
        "current_wind_speed_kmh": 10.0,
    }
    res = gate.apply([calm_pred])
    assert res[0]["safety_status"] == "NO_WARNING_DATA"
    assert res[0]["safety_status"] != "SAFE_CONFIRMED"


def test_case_c_stale_warning():
    """CASE C: Marine warning data is stale -> NEVER SAFE_CONFIRMED."""
    now = datetime.now(timezone.utc)
    stale_warning = {
        "severity": "NORMAL",
        "valid_from": now - timedelta(days=2),
        "valid_until": now - timedelta(hours=1), # Expired 1 hour ago
        "description": "Nil warning"
    }
    gate = SafetyGate(marine_warnings=[stale_warning])
    
    calm_pred = {
        "grid_cell_id": "cell_1",
        "predicted_apparent_fishing_probability": 0.5,
        "current_wave_height_m": 1.0,
        "current_wind_speed_kmh": 10.0,
    }
    res = gate.apply([calm_pred])
    assert res[0]["safety_status"] == "NO_WARNING_DATA"
    assert res[0]["safety_status"] != "SAFE_CONFIRMED"


def test_case_d_high_prediction_warning_dominant():
    """CASE D: IMD warning exists AND fishing prediction HIGH -> WARNING remains dominant."""
    now = datetime.now(timezone.utc)
    severe_warning = {
        "severity": "SEVERE",
        "valid_from": now - timedelta(hours=1),
        "valid_until": now + timedelta(hours=23),
        "description": "Squally weather"
    }
    gate = SafetyGate(marine_warnings=[severe_warning])
    
    high_pred = {
        "grid_cell_id": "cell_1",
        "predicted_apparent_fishing_probability": 0.99, # Extremely high
        "current_wave_height_m": 1.0,
        "current_wind_speed_kmh": 10.0,
    }
    res = gate.apply([high_pred])
    assert res[0]["safety_status"] == "UNSAFE"
    assert res[0]["safety_override"] is True


def test_case_e_low_prediction_warning_dominant():
    """CASE E: Fishing prediction is LOW AND warning exists -> Warning still remains visible."""
    now = datetime.now(timezone.utc)
    warning = {
        "severity": "WARNING",
        "valid_from": now - timedelta(hours=1),
        "valid_until": now + timedelta(hours=23),
        "description": "Strong winds"
    }
    gate = SafetyGate(marine_warnings=[warning])
    
    low_pred = {
        "grid_cell_id": "cell_1",
        "predicted_apparent_fishing_probability": 0.10, # Very low
        "current_wave_height_m": 1.0,
        "current_wind_speed_kmh": 10.0,
    }
    res = gate.apply([low_pred])
    assert res[0]["safety_status"] == "CAUTION"
    assert res[0]["safety_override"] is False


def test_case_f_gfw_historical_not_imply_safe():
    """CASE F: GFW historical activity is high -> Must NOT imply current safe fishing conditions."""
    gate = SafetyGate(marine_warnings=[])
    
    pred_with_gfw_context = {
        "grid_cell_id": "cell_1",
        "predicted_apparent_fishing_probability": 0.85,
        "current_wave_height_m": 1.0,
        "current_wind_speed_kmh": 10.0,
        "historical_gfw_fishing_hours": 100.0 # High historical GFW
    }
    res = gate.apply([pred_with_gfw_context])
    # Must remain NO_WARNING_DATA because we lack current authoritative safety data
    assert res[0]["safety_status"] == "NO_WARNING_DATA"
    assert res[0]["safety_status"] != "SAFE_CONFIRMED"


def test_case_g_source_unavailable():
    """CASE G: Any source is unavailable (e.g. env data) -> Do not silently convert to SAFE."""
    now = datetime.now(timezone.utc)
    normal_warning = {
        "severity": "NORMAL",
        "valid_from": now - timedelta(hours=1),
        "valid_until": now + timedelta(hours=23),
        "description": "Nil warning"
    }
    gate = SafetyGate(marine_warnings=[normal_warning])
    
    # Missing environmental safety data (wave/wind is None/unavailable)
    missing_env_pred = {
        "grid_cell_id": "cell_1",
        "predicted_apparent_fishing_probability": 0.5,
        "current_wave_height_m": None,
        "current_wind_speed_kmh": None,
    }
    res = gate.apply([missing_env_pred])
    # The normal warning implies safe, BUT local env conditions could not be verified
    assert res[0]["safety_status"] == "NO_WARNING_DATA"
    assert res[0]["safety_status"] != "SAFE_CONFIRMED"

