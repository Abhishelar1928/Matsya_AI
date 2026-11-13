"""
Matsya AI — Phase 3: ML Baselines & Proof of Concept Experiment Harness.

Executes end-to-end scientific evaluation:
1. Causal dataset construction (T -> T+1)
2. Automated provenance & leakage validation
3. Evaluation across all four candidate thresholds (>0.5h, >1.0h, >2.0h, >5.0h)
4. Implementation and evaluation of 3 domain baselines:
   - Recent Activity Baseline
   - 7-Day Trailing Historical Baseline
   - Seasonal/Spatial Baseline
5. ML Model evaluation:
   - Logistic Regression
   - Random Forest Classifier
   - XGBoost Classifier
6. Regression evaluation (MAE, RMSE, R²)
7. Strict chronological temporal validation (Train -> Val -> Test)
8. Spatial generalization (Overall, Coastal vs Offshore, Top Active Cells)
9. Acceptance criteria evaluation & report generation
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import json
import logging
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from backend.app.ml.config import ARTIFACTS_DIR, HISTORICAL_CACHE_PATH
from ml.evaluation.leakage_validator import (
    DataLeakageError,
    validate_dataset_provenance,
    validate_preprocessing_isolation,
    validate_temporal_splits,
)
from ml.features.causal_dataset import FEATURE_COLUMNS, build_causal_dataset
from ml.models.baselines import (
    RecentActivityBaseline,
    SeasonalSpatialBaseline,
    Trailing7DayHistoricalBaseline,
    compute_classification_metrics,
    compute_regression_metrics,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

THRESHOLDS = [0.5, 1.0, 2.0, 5.0]


def tune_classification_threshold(
    y_val: np.ndarray, val_scores: np.ndarray
) -> Tuple[float, float]:
    """
    Finds the probability / score decision threshold that maximizes F1 on validation set.
    """
    best_t = 0.5
    best_f1 = -1.0
    # Search from min to max of validation scores
    candidate_thresholds = np.linspace(0.01, 0.95, 95)
    for t in candidate_thresholds:
        preds = (val_scores >= t).astype(int)
        res = compute_classification_metrics(y_val, val_scores, preds)
        if res["f1"] > best_f1:
            best_f1 = res["f1"]
            best_t = float(t)
    return best_t, best_f1


def run_experiment() -> Dict[str, Any]:
    logger.info("=== Starting Phase 3: ML Baselines & Proof of Concept ===")
    
    # 1. Build Causal Dataset from actual historical data
    logger.info(f"Loading actual data from {HISTORICAL_CACHE_PATH}...")
    dataset_df = build_causal_dataset(HISTORICAL_CACHE_PATH, lookback_days=14, gfw_lag_days=0)
    
    # 2. Automated Provenance & Leakage Verification
    prov_res = validate_dataset_provenance(dataset_df)
    logger.info(f"Provenance Validation: {prov_res}")

    # 3. Define Strict Chronological Splits
    pred_dates = sorted(dataset_df["prediction_date_T"].dt.date.unique())
    n_dates = len(pred_dates)
    train_cutoff_idx = int(n_dates * 0.60)
    val_cutoff_idx = int(n_dates * 0.80)
    
    train_dates = pred_dates[:train_cutoff_idx]
    val_dates = pred_dates[train_cutoff_idx:val_cutoff_idx]
    test_dates = pred_dates[val_cutoff_idx:]
    
    split_res = validate_temporal_splits(train_dates, val_dates, test_dates)
    logger.info(f"Temporal Split Validation: {split_res}")
    
    train_df = dataset_df[dataset_df["prediction_date_T"].dt.date.isin(train_dates)].copy()
    val_df = dataset_df[dataset_df["prediction_date_T"].dt.date.isin(val_dates)].copy()
    test_df = dataset_df[dataset_df["prediction_date_T"].dt.date.isin(test_dates)].copy()
    
    logger.info(
        f"Split counts: Train={len(train_df)} rows ({len(train_dates)} days), "
        f"Val={len(val_df)} rows ({len(val_dates)} days), "
        f"Test={len(test_df)} rows ({len(test_dates)} days)"
    )

    # 4. Preprocessing — Strict Isolation: Fit ONLY on Train
    imputer = SimpleImputer(strategy="median")
    scaler = StandardScaler()
    
    feature_cols = [c for c in FEATURE_COLUMNS if c in dataset_df.columns]
    
    X_train_raw = train_df[feature_cols]
    imputer.fit(X_train_raw)
    X_train_imp = imputer.transform(X_train_raw)
    scaler.fit(X_train_imp)
    
    # Run automated preprocessor leakage check
    validate_preprocessing_isolation(imputer, scaler, X_train_raw, feature_cols)
    
    X_train = scaler.transform(X_train_imp)
    X_val = scaler.transform(imputer.transform(val_df[feature_cols]))
    X_test = scaler.transform(imputer.transform(test_df[feature_cols]))
    
    results = {
        "metadata": {
            "execution_timestamp": datetime.now(timezone.utc).isoformat(),
            "total_samples": len(dataset_df),
            "unique_cells": dataset_df["grid_cell_id"].nunique(),
            "feature_columns": feature_cols,
            "train_dates": [str(min(train_dates)), str(max(train_dates))],
            "val_dates": [str(min(val_dates)), str(max(val_dates))],
            "test_dates": [str(min(test_dates)), str(max(test_dates))],
        },
        "threshold_evaluations": {},
        "regression_evaluation": {},
        "spatial_generalization": {},
        "feature_importances": {},
    }

    # 5. Evaluate all four thresholds
    for th in THRESHOLDS:
        logger.info(f"\n--- Evaluating Candidate Threshold > {th} fishing hours ---")
        th_key = f"thresh_{th}h"
        
        y_train = (train_df["target_fishing_hours"].values > th).astype(int)
        y_val = (val_df["target_fishing_hours"].values > th).astype(int)
        y_test = (test_df["target_fishing_hours"].values > th).astype(int)
        
        th_data = {
            "threshold_hours": th,
            "sample_counts": {
                "train_pos": int(y_train.sum()),
                "train_total": len(y_train),
                "train_prevalence": float(y_train.mean()),
                "val_pos": int(y_val.sum()),
                "val_total": len(y_val),
                "val_prevalence": float(y_val.mean()),
                "test_pos": int(y_test.sum()),
                "test_total": len(y_test),
                "test_prevalence": float(y_test.mean()),
            },
            "baselines": {},
            "ml_models": {},
        }
        
        # --- BASELINE 1: Recent Activity Baseline ---
        b_recent = RecentActivityBaseline(threshold_hours=th)
        th_data["baselines"]["Recent_Activity"] = {
            "val": b_recent.evaluate(val_df),
            "test": b_recent.evaluate(test_df),
        }
        
        # --- BASELINE 2: 7-Day Trailing Baseline ---
        b_7d = Trailing7DayHistoricalBaseline(threshold_hours=th)
        th_data["baselines"]["Trailing_7Day"] = {
            "val": b_7d.evaluate(val_df),
            "test": b_7d.evaluate(test_df),
        }
        
        # --- BASELINE 3: Seasonal/Spatial Baseline ---
        b_spatial = SeasonalSpatialBaseline(threshold_hours=th)
        b_spatial.fit(train_df)
        th_data["baselines"]["Seasonal_Spatial"] = {
            "val": b_spatial.evaluate(val_df),
            "test": b_spatial.evaluate(test_df),
        }
        
        # --- ML MODEL 1: Logistic Regression ---
        lr = LogisticRegression(class_weight="balanced", max_iter=1000, random_state=42)
        lr.fit(X_train, y_train)
        val_probs_lr = lr.predict_proba(X_val)[:, 1]
        test_probs_lr = lr.predict_proba(X_test)[:, 1]
        best_t_lr, val_f1_lr = tune_classification_threshold(y_val, val_probs_lr)
        
        th_data["ml_models"]["Logistic_Regression"] = {
            "tuned_threshold": best_t_lr,
            "val": compute_classification_metrics(y_val, val_probs_lr, (val_probs_lr >= best_t_lr).astype(int)),
            "test": compute_classification_metrics(y_test, test_probs_lr, (test_probs_lr >= best_t_lr).astype(int)),
        }
        
        # --- ML MODEL 2: Random Forest Classifier ---
        rf = RandomForestClassifier(n_estimators=100, max_depth=8, class_weight="balanced", random_state=42)
        rf.fit(X_train, y_train)
        val_probs_rf = rf.predict_proba(X_val)[:, 1]
        test_probs_rf = rf.predict_proba(X_test)[:, 1]
        best_t_rf, val_f1_rf = tune_classification_threshold(y_val, val_probs_rf)
        
        th_data["ml_models"]["Random_Forest"] = {
            "tuned_threshold": best_t_rf,
            "val": compute_classification_metrics(y_val, val_probs_rf, (val_probs_rf >= best_t_rf).astype(int)),
            "test": compute_classification_metrics(y_test, test_probs_rf, (test_probs_rf >= best_t_rf).astype(int)),
        }
        
        # --- ML MODEL 3: XGBoost Classifier ---
        scale_pos = float((len(y_train) - y_train.sum()) / max(1, y_train.sum()))
        xgb = XGBClassifier(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.05,
            scale_pos_weight=scale_pos,
            eval_metric="logloss",
            random_state=42,
        )
        xgb.fit(X_train, y_train)
        val_probs_xgb = xgb.predict_proba(X_val)[:, 1]
        test_probs_xgb = xgb.predict_proba(X_test)[:, 1]
        best_t_xgb, val_f1_xgb = tune_classification_threshold(y_val, val_probs_xgb)
        
        th_data["ml_models"]["XGBoost"] = {
            "tuned_threshold": best_t_xgb,
            "val": compute_classification_metrics(y_val, val_probs_xgb, (val_probs_xgb >= best_t_xgb).astype(int)),
            "test": compute_classification_metrics(y_test, test_probs_xgb, (test_probs_xgb >= best_t_xgb).astype(int)),
        }
        
        results["threshold_evaluations"][th_key] = th_data

    # 6. Continuous Regression Models (T+1 fishing hours)
    logger.info("\n--- Evaluating Continuous Regression Models on T+1 Hours ---")
    y_reg_train = train_df["target_fishing_hours"].values
    y_reg_val = val_df["target_fishing_hours"].values
    y_reg_test = test_df["target_fishing_hours"].values
    
    # Regression Baselines
    b_recent_reg_test = compute_regression_metrics(y_reg_test, test_df["fishing_hours_recent"].values)
    b_7d_reg_test = compute_regression_metrics(y_reg_test, test_df["fishing_hours_7d_mean"].values)
    
    # ML Regressors
    rf_reg = RandomForestRegressor(n_estimators=100, max_depth=8, random_state=42)
    rf_reg.fit(X_train, y_reg_train)
    rf_reg_test = compute_regression_metrics(y_reg_test, rf_reg.predict(X_test))
    
    ridge_reg = Ridge(alpha=10.0, random_state=42)
    ridge_reg.fit(X_train, y_reg_train)
    ridge_reg_test = compute_regression_metrics(y_reg_test, ridge_reg.predict(X_test))
    
    results["regression_evaluation"] = {
        "Baseline_Recent_Activity": b_recent_reg_test,
        "Baseline_Trailing_7Day": b_7d_reg_test,
        "Random_Forest_Regressor": rf_reg_test,
        "Ridge_Regressor": ridge_reg_test,
    }

    # 7. Spatial Generalization (on primary candidate threshold: > 1.0 hr)
    logger.info("\n--- Evaluating Spatial Generalization (> 1.0 hr) ---")
    primary_th = 1.0
    y_test_primary = (test_df["target_fishing_hours"].values > primary_th).astype(int)
    test_df["y_true"] = y_test_primary
    
    # Re-use XGBoost model for 1.0h
    scale_pos = float((len(train_df) - (train_df["target_fishing_hours"] > primary_th).sum()) / max(1, (train_df["target_fishing_hours"] > primary_th).sum()))
    xgb_primary = XGBClassifier(n_estimators=100, max_depth=4, learning_rate=0.05, scale_pos_weight=scale_pos, eval_metric="logloss", random_state=42)
    xgb_primary.fit(X_train, (train_df["target_fishing_hours"] > primary_th).astype(int))
    
    test_probs = xgb_primary.predict_proba(X_test)[:, 1]
    tuned_t = results["threshold_evaluations"]["thresh_1.0h"]["ml_models"]["XGBoost"]["tuned_threshold"]
    test_preds = (test_probs >= tuned_t).astype(int)
    test_df["y_pred_xgb"] = test_preds
    test_df["prob_xgb"] = test_probs
    
    # A. Coastal vs Offshore
    coastal_mask = (test_df["is_coastal"] == 1.0)
    coastal_metrics_xgb = compute_classification_metrics(test_df[coastal_mask]["y_true"], test_df[coastal_mask]["prob_xgb"], test_df[coastal_mask]["y_pred_xgb"])
    offshore_metrics_xgb = compute_classification_metrics(test_df[~coastal_mask]["y_true"], test_df[~coastal_mask]["prob_xgb"], test_df[~coastal_mask]["y_pred_xgb"])
    
    # Baseline comparison in coastal vs offshore
    b7d_coastal = Trailing7DayHistoricalBaseline(threshold_hours=primary_th).evaluate(test_df[coastal_mask])
    b7d_offshore = Trailing7DayHistoricalBaseline(threshold_hours=primary_th).evaluate(test_df[~coastal_mask])
    
    # B. Canonical Grid Cells (Top 5 active cells in test period)
    cell_activity = test_df.groupby("grid_cell_id")["y_true"].sum().sort_values(ascending=False)
    top_cells = cell_activity.head(5).index.tolist()
    
    cell_breakdown = {}
    for cid in top_cells:
        c_sub = test_df[test_df["grid_cell_id"] == cid]
        if len(c_sub) > 0 and c_sub["y_true"].sum() > 0:
            c_xgb = compute_classification_metrics(c_sub["y_true"], c_sub["prob_xgb"], c_sub["y_pred_xgb"])
            c_b7d = Trailing7DayHistoricalBaseline(threshold_hours=primary_th).evaluate(c_sub)
            cell_breakdown[cid] = {
                "active_days_test": int(c_sub["y_true"].sum()),
                "total_days_test": len(c_sub),
                "xgb_f1": c_xgb["f1"],
                "xgb_pr_auc": c_xgb["pr_auc"],
                "b7d_f1": c_b7d["f1"],
                "b7d_pr_auc": c_b7d["pr_auc"],
            }
            
    results["spatial_generalization"] = {
        "coastal_xgb": coastal_metrics_xgb,
        "coastal_baseline_7d": b7d_coastal,
        "offshore_xgb": offshore_metrics_xgb,
        "offshore_baseline_7d": b7d_offshore,
        "top_cells": cell_breakdown,
    }

    # 8. Feature Importances (XGBoost primary model)
    xgb_importances = dict(zip(feature_cols, [float(x) for x in xgb_primary.feature_importances_]))
    sorted_importances = dict(sorted(xgb_importances.items(), key=lambda item: item[1], reverse=True))
    results["feature_importances"] = sorted_importances

    # 9. Model Acceptance Criteria Evaluation
    # Does ML meaningfully outperform all baselines on Test set?
    b_test_f1s = [
        results["threshold_evaluations"]["thresh_1.0h"]["baselines"]["Recent_Activity"]["test"]["f1"],
        results["threshold_evaluations"]["thresh_1.0h"]["baselines"]["Trailing_7Day"]["test"]["f1"],
        results["threshold_evaluations"]["thresh_1.0h"]["baselines"]["Seasonal_Spatial"]["test"]["f1"],
    ]
    b_test_praucs = [
        results["threshold_evaluations"]["thresh_1.0h"]["baselines"]["Recent_Activity"]["test"]["pr_auc"],
        results["threshold_evaluations"]["thresh_1.0h"]["baselines"]["Trailing_7Day"]["test"]["pr_auc"],
        results["threshold_evaluations"]["thresh_1.0h"]["baselines"]["Seasonal_Spatial"]["test"]["pr_auc"],
    ]
    
    ml_test_f1 = results["threshold_evaluations"]["thresh_1.0h"]["ml_models"]["XGBoost"]["test"]["f1"]
    ml_test_prauc = results["threshold_evaluations"]["thresh_1.0h"]["ml_models"]["XGBoost"]["test"]["pr_auc"]
    
    max_baseline_f1 = max(b_test_f1s)
    max_baseline_prauc = max(b_test_praucs)
    
    beats_f1 = ml_test_f1 > max_baseline_f1
    beats_prauc = ml_test_prauc > max_baseline_prauc
    
    if beats_f1 and beats_prauc:
        verdict = "ML demonstrates sufficient predictive value over historical baselines."
        status = "ACCEPT"
    else:
        verdict = "ML does not demonstrate sufficient predictive value under the current data and validation design."
        status = "REJECT_OR_INSUFFICIENT"
        
    results["acceptance"] = {
        "status": status,
        "verdict": verdict,
        "ml_test_f1": ml_test_f1,
        "max_baseline_f1": max_baseline_f1,
        "ml_test_prauc": ml_test_prauc,
        "max_baseline_prauc": max_baseline_prauc,
    }
    
    # Save results JSON
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    out_json_path = ARTIFACTS_DIR / "phase3_results.json"
    with open(out_json_path, "w") as f:
        json.dump(results, f, indent=2)
    logger.info(f"Saved complete Phase 3 results to {out_json_path}")
    
    return results


if __name__ == "__main__":
    res = run_experiment()
    print("\n=== Phase 3 Experiment Completed Successfully ===")
    print(f"Acceptance Verdict: {res['acceptance']['verdict']}")
