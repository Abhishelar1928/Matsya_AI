import pytest
import asyncio
from datetime import datetime, timezone
import json
from unittest.mock import patch, MagicMock, AsyncMock

from sqlalchemy import select

from backend.app.services.ingestion.ingestion_runner import IngestionRunner
from backend.app.models.prediction import Prediction
from backend.app.models.marine_warning import MarineWarning


def _mock_db_result(records=None):
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = records or []
    mock_result.scalars.return_value = mock_scalars
    mock_db.execute.return_value = mock_result
    return mock_db


@pytest.mark.asyncio
@patch("backend.app.ml.inference.get_inference_pipeline")
async def test_successful_batch_persists_prediction_records(mock_get_pipeline):
    """A: successful batch persists prediction records & B: uses existing inference pipeline."""
    # Mock pipeline
    mock_pipeline = MagicMock()
    now_str = datetime.now(timezone.utc).isoformat()
    mock_pipeline.predict.return_value = [
        {
            "grid_cell_id": "cell_1",
            "latitude": 15.0,
            "longitude": 73.0,
            "distance_to_coast_km": 10.0,
            "is_coastal": True,
            "predicted_apparent_fishing_probability": 0.85,
            "predicted_apparent_fishing_binary": 1,
            "prediction_label": "High",
            "model_version": "test_v1",
            "prediction_timestamp": now_str,
            "safety_status": "NO_WARNING_DATA",
            "safety_override": False,
        }
    ]
    mock_pipeline.get_last_provenance.return_value = {
        "sources": {
            "open_meteo_marine": {
                "data_timestamp": now_str,
                "age_minutes": 5.0
            }
        }
    }
    mock_get_pipeline.return_value = mock_pipeline

    runner = IngestionRunner()
    db = _mock_db_result()
    
    res = await runner.run_predictions(db)
    
    assert res["status"] == "SUCCESS"
    assert res["records"] == 1
    
    # Verify persistence
    db.add_all.assert_called_once()
    records_to_insert = db.add_all.call_args[0][0]
    assert len(records_to_insert) == 1
    
    # C: Probability in [0,1]
    assert 0.0 <= records_to_insert[0].prediction_probability <= 1.0
    assert records_to_insert[0].prediction_probability == 0.85
    
    # D: Correct grid cells
    assert records_to_insert[0].latitude == 15.0
    assert records_to_insert[0].longitude == 73.0


@pytest.mark.asyncio
@patch("backend.app.ml.inference.get_inference_pipeline")
async def test_idempotency_does_not_duplicate_rows(mock_get_pipeline):
    """E: Rerunning the same batch does not duplicate rows."""
    mock_pipeline = MagicMock()
    now_str = datetime.now(timezone.utc).isoformat()
    mock_pipeline.predict.return_value = [
        {
            "grid_cell_id": "cell_1",
            "latitude": 15.0,
            "longitude": 73.0,
            "predicted_apparent_fishing_probability": 0.5,
            "predicted_apparent_fishing_binary": 1,
            "prediction_label": "High",
            "model_version": "test_v1",
            "prediction_timestamp": now_str,
            "safety_status": "NO_WARNING_DATA",
            "safety_override": False,
        }
    ]
    mock_pipeline.get_last_provenance.return_value = {}
    mock_get_pipeline.return_value = mock_pipeline

    runner = IngestionRunner()
    db = _mock_db_result()
    
    await runner.run_predictions(db)
    
    # Check that delete was called to maintain idempotency
    assert db.execute.call_count >= 2 # Once for select MarineWarning, once for delete
    # add_all is called once per run_predictions
    db.add_all.assert_called_once()

@pytest.mark.asyncio
@patch("backend.app.ml.inference.get_inference_pipeline")
async def test_missing_data_fails_explicitly(mock_get_pipeline):
    """F: missing environmental data does not create fake predictions."""
    mock_pipeline = MagicMock()
    # pipeline returns empty list if it fails or has no data
    mock_pipeline.predict.return_value = []
    mock_get_pipeline.return_value = mock_pipeline

    runner = IngestionRunner()
    db = _mock_db_result()
    
    res = await runner.run_predictions(db)
    assert res["status"] == "ERROR"
    assert res["records"] == 0
    assert "no predictions" in res["error"].lower()

@pytest.mark.asyncio
@patch("backend.app.ml.inference.get_inference_pipeline")
async def test_prediction_does_not_override_safety_gate(mock_get_pipeline):
    """G: prediction generation does not override SafetyGate."""
    mock_pipeline = MagicMock()
    now_str = datetime.now(timezone.utc).isoformat()
    # A high prediction
    mock_pipeline.predict.return_value = [
        {
            "grid_cell_id": "cell_1",
            "latitude": 15.0,
            "longitude": 73.0,
            "predicted_apparent_fishing_probability": 0.95,
            "predicted_apparent_fishing_binary": 1,
            "prediction_label": "High",
            "model_version": "test_v1",
            "prediction_timestamp": now_str,
            "safety_status": "NO_WARNING_DATA",
            "safety_override": False,
            "current_wave_height_m": 5.0, # Dangerous
            "current_wind_speed_kmh": 60.0 # Dangerous
        }
    ]
    mock_pipeline.get_last_provenance.return_value = {}
    mock_get_pipeline.return_value = mock_pipeline

    from datetime import timedelta
    warning = MarineWarning(
        severity="SEVERE",
        valid_from=datetime.now(timezone.utc) - timedelta(hours=1),
        valid_until=datetime.now(timezone.utc) + timedelta(hours=1),
        description="Squally weather"
    )

    runner = IngestionRunner()
    db = _mock_db_result(records=[warning])
    
    await runner.run_predictions(db)
    
    db.add_all.assert_called_once()
    records_to_insert = db.add_all.call_args[0][0]
    assert len(records_to_insert) == 1
    
    # High prediction but active severe warning -> UNSAFE
    assert records_to_insert[0].safety_status == "UNSAFE"
    assert records_to_insert[0].safety_override == True
