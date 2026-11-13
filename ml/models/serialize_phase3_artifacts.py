"""
Matsya AI — Phase 3 Model Artifact Serializer.

Serializes the exact validated Phase 3 XGBoost model and preprocessing pipeline
trained on the 2023 dataset (primary threshold > 1.0 hr, seed 42) into backend/app/ml/artifacts/.
Does NOT change training methodology or feature definitions.
"""

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import json
import logging
from datetime import datetime, timezone
import joblib
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from backend.app.ml.config import ARTIFACTS_DIR, HISTORICAL_CACHE_PATH
from ml.features.causal_dataset import FEATURE_COLUMNS, build_causal_dataset

logger = logging.getLogger(__name__)


def serialize_phase3():
    logging.basicConfig(level=logging.INFO)
    logger.info("Building causal dataset from historical cache...")
    df = build_causal_dataset(HISTORICAL_CACHE_PATH, lookback_days=14, gfw_lag_days=0)
    
    # 60% Train split
    pred_dates = sorted(df["prediction_date_T"].dt.date.unique())
    train_dates = pred_dates[: int(len(pred_dates) * 0.60)]
    train_df = df[df["prediction_date_T"].dt.date.isin(train_dates)].copy()
    
    # Primary target threshold: > 1.0 fishing hours
    target_threshold = 1.0
    y_train = (train_df["target_fishing_hours"].values > target_threshold).astype(int)
    
    feature_cols = [c for c in FEATURE_COLUMNS if c in train_df.columns]
    X_train_raw = train_df[feature_cols]
    
    logger.info(f"Fitting preprocessors on {len(X_train_raw)} training rows...")
    imputer = SimpleImputer(strategy="median")
    imputer.fit(X_train_raw)
    X_train_imp = imputer.transform(X_train_raw)
    
    scaler = StandardScaler()
    scaler.fit(X_train_imp)
    X_train_scaled = scaler.transform(X_train_imp)
    
    scale_pos = float((len(y_train) - y_train.sum()) / max(1, y_train.sum()))
    logger.info(f"Training XGBoost classifier (scale_pos_weight={scale_pos:.4f})...")
    xgb = XGBClassifier(
        n_estimators=100,
        max_depth=4,
        learning_rate=0.05,
        scale_pos_weight=scale_pos,
        eval_metric="logloss",
        random_state=42,
    )
    xgb.fit(X_train_scaled, y_train)
    
    # Frozen decision threshold from Phase 3 validation tuning
    decision_threshold = 0.47
    
    # Ensure artifacts directory exists
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    
    model_path = ARTIFACTS_DIR / "phase3_xgboost_model.joblib"
    imputer_path = ARTIFACTS_DIR / "phase3_imputer.joblib"
    scaler_path = ARTIFACTS_DIR / "phase3_scaler.joblib"
    meta_path = ARTIFACTS_DIR / "phase3_metadata.json"
    thresh_path = ARTIFACTS_DIR / "phase3_threshold.json"
    features_path = ARTIFACTS_DIR / "phase3_feature_columns.json"
    
    joblib.dump(xgb, model_path)
    joblib.dump(imputer, imputer_path)
    joblib.dump(scaler, scaler_path)
    
    with open(features_path, "w") as f:
        json.dump(feature_cols, f, indent=2)
        
    with open(thresh_path, "w") as f:
        json.dump({
            "target_threshold_hours": target_threshold,
            "decision_threshold": decision_threshold,
            "target_interpretation": "next-calendar-day apparent fishing activity (>1.0 fishing hours)"
        }, f, indent=2)
        
    metadata = {
        "model_version": "Phase3_XGBoost_v1",
        "algorithm": "XGBoost Classifier",
        "training_start_date": str(min(train_dates)),
        "training_end_date": str(max(train_dates)),
        "training_samples": len(X_train_raw),
        "target_threshold_hours": target_threshold,
        "decision_threshold": decision_threshold,
        "features": feature_cols,
        "target_definition": "Predicted apparent fishing activity on next calendar day (T+1)",
        "serialization_timestamp": datetime.now(timezone.utc).isoformat(),
        "disclaimer": "Predicts apparent fishing activity derived from historical GFW AIS patterns. Does not predict fish presence, biomass, species, or catch guarantee.",
        "environmental_training_source": "Open-Meteo Historical Marine & Weather Archive (CMEMS and INCOIS PFZ were NOT used as training features)."
    }
    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=2)
        
    logger.info("Successfully serialized Phase 3 artifacts:")
    logger.info(f" - Model: {model_path}")
    logger.info(f" - Imputer: {imputer_path}")
    logger.info(f" - Scaler: {scaler_path}")
    logger.info(f" - Metadata: {meta_path}")
    logger.info(f" - Threshold: {thresh_path}")
    logger.info(f" - Feature columns: {features_path}")


if __name__ == "__main__":
    serialize_phase3()
