"""
MatsyaAI Maharashtra — Phase 4 Experiment & Benchmark Harness (`Phase4_SpatioOcean_v1`).

Benchmarks on identical chronological Train / Validation / Test splits:
1. Phase3_XGBoost_Baseline  (29 isolated grid + Open-Meteo + AIS features)
2. Phase4_Spatial_Only      (Phase 3 + 3x3 Moore / 2-ring neighbor + current convergence)
3. Phase4_Stage1_Habitat    (Pure ocean + bathymetry + weather + calendar; ZERO AIS)
4. Phase4_SpatioOcean_v1    (Full Two-Stage expanding OOF + Stage-2 XGBoost + Calibration)

Reports: PR-AUC, ROC-AUC, F1, Precision, Recall, Brier Score, daily Precision@top-K,
coastal vs offshore generalization, AIS-persistence shift analysis, and strict leakage audits.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from backend.app.ml.config import ARTIFACTS_DIR, HISTORICAL_CACHE_PATH, MULTIYEAR_HISTORICAL_CACHE_PATH
from ml.evaluation.leakage_validator import (
    validate_dataset_provenance,
    validate_preprocessing_isolation,
    validate_rolling_ocean_causality,
    validate_spatial_neighbor_causality,
    validate_stage1_feature_purity,
    validate_stage1_oof_causality,
)
from ml.features.causal_dataset import FEATURE_COLUMNS as PHASE3_FEATURE_COLUMNS
from ml.features.features_spatial_ocean import (
    OCEAN_CACHE_DIR,
    OCEAN_HABITAT_FEATURES,
    SPATIAL_NEIGHBOR_FEATURES,
    SPATIAL_ONLY_FEATURES,
    STAGE1_HABITAT_FEATURES,
    STAGE2_OPERATIONAL_FEATURES,
    SpatialAdjacencyMapper,
    _load_multi_source_raw,
    build_phase4_causal_dataset,
    compute_ocean_habitat_features,
    compute_spatial_neighborhood_features,
)
from ml.models.phase4_pipeline import (
    build_seasonal_climatology_frame,
    build_stage2_estimator,
    compute_phase4_metrics,
    fit_calibrator_and_tune_threshold,
    generate_expanding_oof_stage1,
    score_stage1_bundle,
    split_chronological_dataset,
    tune_f1_threshold,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

AIS_PERSISTENCE_PREFIXES = ("fishing_hours_", "regional_fishing_hours_", "nbr_1ring_fishing", "nbr_2ring_fishing", "nbr_1ring_active")


def _fit_single_stage_xgb(
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    test_df: pd.DataFrame,
    features: List[str],
    target_threshold: float,
    model_name: str,
) -> Dict[str, Any]:
    """Train & evaluate a baseline single-stage XGBoost classifier with strict Train-only preprocessing."""
    y_train = (train_df["target_fishing_hours"].values > target_threshold).astype(int)
    y_val = (val_df["target_fishing_hours"].values > target_threshold).astype(int)
    y_test = (test_df["target_fishing_hours"].values > target_threshold).astype(int)

    imp = SimpleImputer(strategy="median", keep_empty_features=True)
    scl = StandardScaler()
    X_tr_raw = train_df[features]
    X_tr_imp = imp.fit_transform(X_tr_raw)
    X_tr_scl = scl.fit_transform(X_tr_imp)
    validate_preprocessing_isolation(imp, scl, X_tr_raw, features)

    X_val_scl = scl.transform(imp.transform(val_df[features]))
    X_te_scl = scl.transform(imp.transform(test_df[features]))

    pos = int(y_train.sum())
    neg = int(len(y_train) - pos)
    spw = float(neg / max(1, pos))

    xgb = XGBClassifier(
        n_estimators=100,
        max_depth=4,
        learning_rate=0.05,
        scale_pos_weight=spw,
        eval_metric="logloss",
        random_state=42,
    )
    xgb.fit(X_tr_scl, y_train)

    val_probs = np.clip(xgb.predict_proba(X_val_scl)[:, 1], 0.0, 1.0)
    test_probs = np.clip(xgb.predict_proba(X_te_scl)[:, 1], 0.0, 1.0)

    best_t, _ = tune_f1_threshold(y_val, val_probs)
    val_preds = (val_probs >= best_t).astype(int)
    test_preds = (test_probs >= best_t).astype(int)

    importances = dict(
        sorted(
            zip(features, [round(float(v), 6) for v in xgb.feature_importances_]),
            key=lambda kv: kv[1],
            reverse=True,
        )
    )
    logger.info(
        f"[{model_name}] Val PR-AUC={compute_phase4_metrics(val_df, y_val, val_probs, val_preds)['pr_auc']:.4f} | "
        f"Test PR-AUC={compute_phase4_metrics(test_df, y_test, test_probs, test_preds)['pr_auc']:.4f}, "
        f"F1={compute_phase4_metrics(test_df, y_test, test_probs, test_preds)['f1']:.4f}"
    )

    return {
        "tuned_threshold": best_t,
        "val": compute_phase4_metrics(val_df, y_val, val_probs, val_preds),
        "test": compute_phase4_metrics(test_df, y_test, test_probs, test_preds),
        "feature_importances": importances,
        "test_probs": test_probs,
        "test_preds": test_preds,
    }


def _summarize_importance_share(importances: Dict[str, float]) -> Dict[str, float]:
    total = float(sum(importances.values())) or 1.0
    self_ais = sum(v for k, v in importances.items() if k.startswith(("fishing_hours_", "regional_fishing_hours_"))) / total
    nbr_ais = sum(v for k, v in importances.items() if k.startswith(("nbr_1ring_fishing", "nbr_2ring_fishing", "nbr_1ring_active"))) / total
    habitat_score = importances.get("habitat_suitability_score", 0.0) / total
    ocean_bathy = sum(v for k, v in importances.items() if k in OCEAN_HABITAT_FEATURES or k == "current_convergence_proxy") / total
    return {
        "self_ais_persistence_share": round(self_ais, 4),
        "spatial_neighbor_ais_share": round(nbr_ais, 4),
        "stage1_habitat_score_share": round(habitat_score, 4),
        "direct_ocean_bathymetry_share": round(ocean_bathy, 4),
        "non_ais_signal_share": round(max(0.0, 1.0 - self_ais - nbr_ais), 4),
    }


def _run_perturbation_audits(
    dataset_df: pd.DataFrame,
    spatial_cols: List[str],
    ocean_cols: List[str],
) -> Dict[str, Any]:
    """
    Construct a causal slice with explicit SST & Chl-a observations and verify that
    perturbing T+1 values never changes spatial or rolling ocean features at T.
    """
    dates = sorted(pd.to_datetime(dataset_df["prediction_date_T"]).unique())
    mid_idx = min(len(dates) - 2, max(16, len(dates) // 2))
    target_T = pd.Timestamp(dates[mid_idx])
    window_start = target_T - pd.Timedelta(days=15)
    window_end = target_T + pd.Timedelta(days=1)

    sub = dataset_df[
        (pd.to_datetime(dataset_df["prediction_date_T"]) >= window_start)
        & (pd.to_datetime(dataset_df["prediction_date_T"]) <= window_end)
    ].copy()
    sub = sub.rename(columns={"prediction_date_T": "observation_date"})
    sub["fishing_hours"] = sub["fishing_hours_recent"]

    # Ensure finite synthetic fallback values on the audit window if ocean caches were sparse on those exact days
    if "sst" not in sub.columns or sub["sst"].isna().all():
        sub["sst"] = 28.0 + 0.05 * (sub["latitude"] - 16.0)
    if "chl_a" not in sub.columns or sub["chl_a"].isna().all():
        sub["chl_a"] = 0.8 + 0.02 * (sub["longitude"] - 72.0)

    mapper = SpatialAdjacencyMapper(sub)

    spatial_res = validate_spatial_neighbor_causality(
        sub,
        lambda frame: compute_spatial_neighborhood_features(frame, mapper, gfw_lag_days=0),
        target_date_T=target_T,
        spatial_cols=spatial_cols,
    )
    ocean_res = validate_rolling_ocean_causality(
        sub,
        lambda frame: compute_ocean_habitat_features(frame, mapper),
        target_date_T=target_T,
        ocean_cols=ocean_cols,
    )
    return {"spatial_neighbor_causality": spatial_res, "rolling_ocean_causality": ocean_res}


def run_phase4_experiment(
    source_parquet_paths: Optional[Union[Path, str, Sequence[Union[Path, str]]]] = None,
    ocean_cache_dir: Optional[Path] = None,
    target_threshold: float = 1.0,
    return_artifacts: bool = False,
    save_results: bool = True,
) -> Any:
    """
    Execute the complete Phase 4 benchmark & validation suite.
    When return_artifacts=True, returns `(results_dict, winning_artifacts_bundle)`.
    """
    logger.info("=== Starting MatsyaAI Phase 4 Experiment (Phase4_SpatioOcean_v1) ===")
    run_id = f"p4_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    exec_ts = datetime.now(timezone.utc).isoformat()
    cache_dir = ocean_cache_dir or OCEAN_CACHE_DIR

    # 1. Build Phase 4 causal dataset (preferring multi-year 2020-2024 when available)
    resolved_source = source_parquet_paths or (
        MULTIYEAR_HISTORICAL_CACHE_PATH if MULTIYEAR_HISTORICAL_CACHE_PATH.exists() else HISTORICAL_CACHE_PATH
    )
    dataset_df = build_phase4_causal_dataset(
        source_parquet_paths=resolved_source,
        lookback_days=14,
        gfw_lag_days=0,
        ocean_cache_dir=cache_dir,
        allow_ocean_fetch=False,
    )
    prov_res = validate_dataset_provenance(dataset_df)
    split_info = split_chronological_dataset(dataset_df, multi_year_test_days=365)

    train_df: pd.DataFrame = split_info["train_df"]
    val_df: pd.DataFrame = split_info["val_df"]
    test_df: pd.DataFrame = split_info["test_df"]
    train_dates = split_info["train_dates"]
    val_dates = split_info["val_dates"]
    test_dates = split_info["test_dates"]

    logger.info(
        f"Split [{split_info['split_mode']}]: "
        f"Train={len(train_df)} ({len(train_dates)}d), "
        f"Val={len(val_df)} ({len(val_dates)}d), "
        f"Test={len(test_df)} ({len(test_dates)}d)"
    )

    p3_features = [c for c in PHASE3_FEATURE_COLUMNS if c in dataset_df.columns]
    spatial_only_features = [c for c in SPATIAL_ONLY_FEATURES if c in dataset_df.columns]
    stage1_features = [c for c in STAGE1_HABITAT_FEATURES if c in dataset_df.columns]
    stage2_features = [
        c
        for c in STAGE2_OPERATIONAL_FEATURES
        if c == "habitat_suitability_score" or c in dataset_df.columns
    ]

    # 2. Causality perturbation audits
    pert_audits = _run_perturbation_audits(
        dataset_df,
        spatial_cols=SPATIAL_NEIGHBOR_FEATURES,
        ocean_cols=["chl_a_lag3_mean", "chl_a_lag7_mean", "chl_a_lag14_mean", "chl_a_anomaly", "sst_spatial_gradient"],
    )

    # 3. Benchmark 1 — Phase 3 XGBoost Baseline (29 features)
    p3_res = _fit_single_stage_xgb(
        train_df, val_df, test_df, p3_features, target_threshold, "Phase3_XGBoost_Baseline"
    )

    # 4. Benchmark 2 — Phase 4 Spatial-Only (29 + 9 neighbor/current convergence features)
    sp_res = _fit_single_stage_xgb(
        train_df, val_df, test_df, spatial_only_features, target_threshold, "Phase4_Spatial_Only"
    )

    # 5. Benchmark 3 — Stage 1 Habitat Suitability (Pure Ocean + Bathymetry + Weather + Calendar; 0 AIS)
    validate_stage1_feature_purity(stage1_features)
    stage2_train_df, fold_audits, stage1_bundle = generate_expanding_oof_stage1(
        train_df=train_df,
        stage1_features=stage1_features,
        target_threshold=target_threshold,
        n_blocks=7,
        random_state=42,
    )
    oof_audit = validate_stage1_oof_causality(fold_audits, val_dates=val_dates, test_dates=test_dates)

    y_val = (val_df["target_fishing_hours"].values > target_threshold).astype(int)
    y_test = (test_df["target_fishing_hours"].values > target_threshold).astype(int)

    val_s1_scores = score_stage1_bundle(stage1_bundle, val_df)
    test_s1_scores = score_stage1_bundle(stage1_bundle, test_df)
    s1_best_t, _ = tune_f1_threshold(y_val, val_s1_scores)
    s1_val_metrics = compute_phase4_metrics(val_df, y_val, val_s1_scores, (val_s1_scores >= s1_best_t).astype(int))
    s1_test_metrics = compute_phase4_metrics(test_df, y_test, test_s1_scores, (test_s1_scores >= s1_best_t).astype(int))
    s1_importances = dict(
        sorted(
            zip(stage1_features, [round(float(v), 6) for v in stage1_bundle["model"].feature_importances_]),
            key=lambda kv: kv[1],
            reverse=True,
        )
    )
    logger.info(
        f"[Phase4_Stage1_Habitat_Only ({stage1_bundle['algorithm']})] "
        f"Val PR-AUC={s1_val_metrics['pr_auc']:.4f} | Test PR-AUC={s1_test_metrics['pr_auc']:.4f}, F1={s1_test_metrics['f1']:.4f}"
    )

    # 6. Benchmark 4 — Full Two-Stage Phase 4 (Stage 1 OOF + Stage 2 Operational XGBoost + Calibration)
    val_s2_df = val_df.copy()
    test_s2_df = test_df.copy()
    val_s2_df["habitat_suitability_score"] = val_s1_scores
    test_s2_df["habitat_suitability_score"] = test_s1_scores

    y_tr_s2 = (stage2_train_df["target_fishing_hours"].values > target_threshold).astype(int)
    s2_imp = SimpleImputer(strategy="median", keep_empty_features=True)
    s2_scl = StandardScaler()

    X_tr_s2_raw = stage2_train_df[stage2_features]
    X_tr_s2_imp = s2_imp.fit_transform(X_tr_s2_raw)
    X_tr_s2_scl = s2_scl.fit_transform(X_tr_s2_imp)
    validate_preprocessing_isolation(s2_imp, s2_scl, X_tr_s2_raw, stage2_features)

    X_val_s2_scl = s2_scl.transform(s2_imp.transform(val_s2_df[stage2_features]))
    X_te_s2_scl = s2_scl.transform(s2_imp.transform(test_s2_df[stage2_features]))

    pos_s2 = int(y_tr_s2.sum())
    neg_s2 = int(len(y_tr_s2) - pos_s2)
    spw_s2 = float(neg_s2 / max(1, pos_s2))

    stage2_model = build_stage2_estimator(scale_pos_weight=spw_s2, random_state=42)
    stage2_model.fit(X_tr_s2_scl, y_tr_s2)

    raw_val_probs = np.clip(stage2_model.predict_proba(X_val_s2_scl)[:, 1], 0.0, 1.0)
    raw_test_probs = np.clip(stage2_model.predict_proba(X_te_s2_scl)[:, 1], 0.0, 1.0)

    # Validation calibration (Isotonic vs Platt). For multi-year runs where Validation spans
    # nearly a full year (289d across 2023), shifting to an older 2020-2022 prior causes
    # +0.08..+0.15 daily over-confidence; keep target_prior only for single-year partial Validation.
    train_prior = float((train_df["target_fishing_hours"].values > target_threshold).mean())
    cal_target_prior = None if split_info["split_mode"] == "multi_year_full_test_year" else train_prior
    calibrator, p4_threshold, cal_report = fit_calibrator_and_tune_threshold(
        val_s2_df, y_val, raw_val_probs, test_dates=test_dates, target_prior=cal_target_prior
    )
    cal_val_probs = calibrator.predict_proba(raw_val_probs)
    cal_test_probs = calibrator.predict_proba(raw_test_probs)

    # 6b. Dedicated Seasonal-Climatology Calibrator (for multi-year demo/historical inference)
    seasonal_calibrator = None
    seasonal_threshold = p4_threshold
    seasonal_cal_report: Optional[Dict[str, Any]] = None
    seasonal_test_metrics: Optional[Dict[str, Any]] = None
    if split_info["split_mode"] == "multi_year_full_test_year":
        raw_hist_df, _, tmp_hist_dir = _load_multi_source_raw(resolved_source)
        try:
            mapper_s = SpatialAdjacencyMapper(raw_hist_df)
            val_clim_ais = build_seasonal_climatology_frame(
                raw_hist_df, val_dates, mapper=mapper_s, noise_floor=1.0
            )
            test_clim_ais = build_seasonal_climatology_frame(
                raw_hist_df, test_dates, mapper=mapper_s, noise_floor=1.0
            )
        finally:
            if tmp_hist_dir is not None:
                tmp_hist_dir.cleanup()

        ais_replace_cols = [c for c in val_clim_ais.columns if c not in ("grid_cell_id", "prediction_date_T")]

        def _score_with_climatology(base_s2_df: pd.DataFrame, clim_ais_df: pd.DataFrame) -> np.ndarray:
            work_df = base_s2_df.drop(columns=[c for c in ais_replace_cols if c in base_s2_df.columns]).copy()
            work_df["_pdate_key"] = pd.to_datetime(work_df["prediction_date_T"])
            clim_keyed = clim_ais_df.rename(columns={"prediction_date_T": "_pdate_key"}).copy()
            clim_keyed["_pdate_key"] = pd.to_datetime(clim_keyed["_pdate_key"])
            merged_clim = work_df.merge(clim_keyed, on=["grid_cell_id", "_pdate_key"], how="left")
            for c in ais_replace_cols:
                if c in merged_clim.columns:
                    merged_clim[c] = merged_clim[c].fillna(0.0)
            X_c_scl = s2_scl.transform(s2_imp.transform(merged_clim[stage2_features]))
            return np.clip(stage2_model.predict_proba(X_c_scl)[:, 1], 0.0, 1.0)

        if not val_clim_ais.empty and not test_clim_ais.empty:
            raw_seasonal_val = _score_with_climatology(val_s2_df, val_clim_ais)
            raw_seasonal_test = _score_with_climatology(test_s2_df, test_clim_ais)
            seasonal_calibrator, seasonal_threshold, seasonal_cal_report = fit_calibrator_and_tune_threshold(
                val_s2_df, y_val, raw_seasonal_val, test_dates=test_dates, target_prior=None
            )
            cal_seasonal_test = seasonal_calibrator.predict_proba(raw_seasonal_test)
            seasonal_test_metrics = compute_phase4_metrics(
                test_s2_df, y_test, cal_seasonal_test, (cal_seasonal_test >= seasonal_threshold).astype(int)
            )
            logger.info(
                f"[Phase4_Seasonal_Climatology (calibrated={seasonal_calibrator.method}, thr={seasonal_threshold})] "
                f"Test PR-AUC={seasonal_test_metrics['pr_auc']:.4f}, Brier={seasonal_test_metrics['brier_score']:.5f}, "
                f"ECE={seasonal_test_metrics['reliability']['ece']:.5f}"
            )

    raw_t, _ = tune_f1_threshold(y_val, raw_val_probs)
    raw_test_metrics = compute_phase4_metrics(test_s2_df, y_test, raw_test_probs, (raw_test_probs >= raw_t).astype(int))
    cal_val_metrics = compute_phase4_metrics(val_s2_df, y_val, cal_val_probs, (cal_val_probs >= p4_threshold).astype(int))
    cal_test_metrics = compute_phase4_metrics(test_s2_df, y_test, cal_test_probs, (cal_test_probs >= p4_threshold).astype(int))

    s2_importances = dict(
        sorted(
            zip(stage2_features, [round(float(v), 6) for v in stage2_model.feature_importances_]),
            key=lambda kv: kv[1],
            reverse=True,
        )
    )
    logger.info(
        f"[Phase4_SpatioOcean_v1 (calibrated={calibrator.method}, thr={p4_threshold})] "
        f"Test PR-AUC={cal_test_metrics['pr_auc']:.4f}, ROC-AUC={cal_test_metrics['roc_auc']:.4f}, "
        f"F1={cal_test_metrics['f1']:.4f}, Brier={cal_test_metrics['brier_score']:.5f}, "
        f"P@10={cal_test_metrics['precision_at_k'].get('p@10', 0):.4f}"
    )

    # 7. Coastal vs Offshore breakdown on Test
    coastal_m = (test_s2_df["is_coastal"] == 1.0).values
    spatial_gen = {
        "coastal_phase3": compute_phase4_metrics(
            test_df[coastal_m], y_test[coastal_m], p3_res["test_probs"][coastal_m], p3_res["test_preds"][coastal_m]
        ),
        "coastal_phase4": compute_phase4_metrics(
            test_s2_df[coastal_m], y_test[coastal_m], cal_test_probs[coastal_m], (cal_test_probs[coastal_m] >= p4_threshold).astype(int)
        ),
        "offshore_phase3": compute_phase4_metrics(
            test_df[~coastal_m], y_test[~coastal_m], p3_res["test_probs"][~coastal_m], p3_res["test_preds"][~coastal_m]
        ),
        "offshore_phase4": compute_phase4_metrics(
            test_s2_df[~coastal_m], y_test[~coastal_m], cal_test_probs[~coastal_m], (cal_test_probs[~coastal_m] >= p4_threshold).astype(int)
        ),
    }

    ocean_coverage = {
        col: round(float(dataset_df[col].notna().mean()), 4)
        for col in ("sst", "sst_spatial_gradient", "chl_a", "chl_a_lag14_mean", "depth_m", "seabed_slope", "current_convergence_proxy")
        if col in dataset_df.columns
    }

    results: Dict[str, Any] = {
        "run_id": run_id,
        "model_version": "Phase4_SpatioOcean_v1",
        "execution_timestamp": exec_ts,
        "target_threshold_hours": target_threshold,
        "target_interpretation": f"next-calendar-day apparent fishing activity (>{target_threshold} fishing hours)",
        "metadata": {
            "total_samples": int(len(dataset_df)),
            "stage2_train_samples": int(len(stage2_train_df)),
            "unique_cells": int(dataset_df["grid_cell_id"].nunique()),
            "split_mode": split_info["split_mode"],
            "train_dates": [str(min(train_dates)), str(max(train_dates))],
            "val_dates": [str(min(val_dates)), str(max(val_dates))],
            "test_dates": [str(min(test_dates)), str(max(test_dates))],
            "stage1_algorithm": stage1_bundle["algorithm"],
            "stage2_algorithm": "XGBClassifier",
            "calibration_method": calibrator.method,
            "decision_threshold": p4_threshold,
            "stage1_feature_count": len(stage1_features),
            "stage2_feature_count": len(stage2_features),
        },
        "ocean_coverage": ocean_coverage,
        "leakage_checks": {
            "provenance": prov_res,
            "stage1_purity": {"status": "PASS", "n_features": len(stage1_features)},
            "stage1_oof": oof_audit,
            "stage1_oof_folds": fold_audits,
            "perturbation_audits": pert_audits,
        },
        "calibration_report": cal_report,
        "seasonal_calibration_report": seasonal_cal_report,
        "seasonal_climatology_test": seasonal_test_metrics,
        "benchmark_comparison": {
            "Phase3_XGBoost_Baseline": {
                "tuned_threshold": p3_res["tuned_threshold"],
                "val": p3_res["val"],
                "test": p3_res["test"],
            },
            "Phase4_Spatial_Only": {
                "tuned_threshold": sp_res["tuned_threshold"],
                "val": sp_res["val"],
                "test": sp_res["test"],
            },
            "Phase4_Stage1_Habitat_Only": {
                "algorithm": stage1_bundle["algorithm"],
                "tuned_threshold": s1_best_t,
                "val": s1_val_metrics,
                "test": s1_test_metrics,
            },
            "Phase4_SpatioOcean_v1_Uncalibrated": {
                "tuned_threshold": raw_t,
                "test": raw_test_metrics,
            },
            "Phase4_SpatioOcean_v1": {
                "calibration_method": calibrator.method,
                "tuned_threshold": p4_threshold,
                "val": cal_val_metrics,
                "test": cal_test_metrics,
            },
        },
        "spatial_generalization": spatial_gen,
        "feature_importances": {
            "phase3_baseline": p3_res["feature_importances"],
            "phase4_stage1_habitat": s1_importances,
            "phase4_stage2_operational": s2_importances,
        },
        "persistence_shift_analysis": {
            "phase3_baseline": _summarize_importance_share(p3_res["feature_importances"]),
            "phase4_stage2": _summarize_importance_share(s2_importances),
        },
        "disclaimer": (
            "Predicts next-calendar-day apparent fishing activity (>1.0 fishing hours) derived "
            "from historical GFW AIS patterns combined with physical/biological oceanographic habitat cues. "
            "Does NOT predict fish presence, biomass, species abundance, or guaranteed catch. "
            "Safety status is determined independently by SafetyGate."
        ),
    }

    if save_results:
        ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = ARTIFACTS_DIR / "phase4_results.json"
        with open(out_path, "w") as fp:
            json.dump(results, fp, indent=2)
        logger.info(f"Saved Phase 4 benchmark results to {out_path}")

    if return_artifacts:
        artifacts_bundle = {
            "run_id": run_id,
            "execution_timestamp": exec_ts,
            "stage1_bundle": stage1_bundle,
            "stage2_model": stage2_model,
            "stage2_imputer": s2_imp,
            "stage2_scaler": s2_scl,
            "calibrator": calibrator,
            "seasonal_calibrator": seasonal_calibrator,
            "seasonal_decision_threshold": seasonal_threshold,
            "seasonal_calibration_report": seasonal_cal_report,
            "stage1_features": stage1_features,
            "stage2_features": stage2_features,
            "target_threshold": target_threshold,
            "decision_threshold": p4_threshold,
            "split_mode": split_info["split_mode"],
            "train_dates": train_dates,
            "val_dates": val_dates,
            "test_dates": test_dates,
            "n_train_rows": int(len(stage2_train_df)),
            "n_total_rows": int(len(dataset_df)),
            "unique_cells": int(dataset_df["grid_cell_id"].nunique()),
        }
        return results, artifacts_bundle

    return results


if __name__ == "__main__":
    summary = run_phase4_experiment(save_results=True)
    comp = summary["benchmark_comparison"]
    print("\n=== Phase 4 Benchmark Summary (Held-Out Test Set) ===")
    for name in ("Phase3_XGBoost_Baseline", "Phase4_Spatial_Only", "Phase4_Stage1_Habitat_Only", "Phase4_SpatioOcean_v1"):
        t = comp[name]["test"]
        print(
            f"  {name:28s} | PR-AUC={t['pr_auc']:.4f} | ROC-AUC={t['roc_auc']:.4f} | "
            f"F1={t['f1']:.4f} | Brier={t['brier_score']:.5f} | P@10={t['precision_at_k'].get('p@10', 0):.4f}"
        )
