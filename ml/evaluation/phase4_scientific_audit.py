"""
MatsyaAI Maharashtra — Comprehensive Phase 4 Scientific Audit Suite.

Executes five strict zero-leakage validation experiments and writes
`backend/app/ml/artifacts/phase4_scientific_audit.json`:
  A. Strictly Independent Nov 2024 Validation (2020-2023 climatology ONLY -> Nov 26-Dec 10 & Nov 15-Dec 5, 2024)
  B. Full 2024 Daily & Seasonal Reliability Diagrams (ECE, Brier, calibration bins)
  C. Clean Oceanographic Ablations (no year-confounded *_isna) + Permutation Importance
  D. Spatial Block Cross-Validation (Leave-One-Latitude-Band-Out across Maharashtra coast)
  E. Independent INCOIS PFZ Spatial Comparison vs GFW seasonal hotspots & Stage-1 habitat
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import json
import logging
import math
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.impute import SimpleImputer
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from backend.app.ml.config import ARTIFACTS_DIR, MULTIYEAR_HISTORICAL_CACHE_PATH
from backend.app.ml.inference import Phase4InferencePipeline
from ml.features.causal_dataset import FEATURE_COLUMNS as PHASE3_FEATURE_COLUMNS
from ml.features.features_spatial_ocean import (
    OCEAN_CACHE_DIR,
    OCEAN_HABITAT_FEATURES,
    SPATIAL_NEIGHBOR_FEATURES,
    STAGE1_HABITAT_FEATURES,
    STAGE2_OPERATIONAL_FEATURES,
    YEAR_CONFOUNDED_MISSINGNESS_FLAGS,
    SpatialAdjacencyMapper,
    build_phase4_causal_dataset,
)
from ml.models.phase4_pipeline import (
    build_seasonal_climatology_frame,
    compute_reliability_diagram,
    split_chronological_dataset,
    tune_f1_threshold,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2.0) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2.0) ** 2
    )
    return r * 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))


def _fit_xgb_ablation(
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    test_df: pd.DataFrame,
    cols: List[str],
    name: str,
) -> Dict[str, Any]:
    y_tr = (train_df["target_fishing_hours"].values > 1.0).astype(int)
    y_va = (val_df["target_fishing_hours"].values > 1.0).astype(int)
    y_te = (test_df["target_fishing_hours"].values > 1.0).astype(int)

    imp = SimpleImputer(strategy="median", keep_empty_features=True)
    scl = StandardScaler()
    X_tr = scl.fit_transform(imp.fit_transform(train_df[cols]))
    X_va = scl.transform(imp.transform(val_df[cols]))
    X_te = scl.transform(imp.transform(test_df[cols]))

    pos = int(y_tr.sum())
    neg = int(len(y_tr) - pos)
    model = XGBClassifier(
        n_estimators=130,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_lambda=2.0,
        scale_pos_weight=float(neg / max(1, pos)),
        eval_metric="logloss",
        random_state=42,
    )
    model.fit(X_tr, y_tr)
    p_va = np.clip(model.predict_proba(X_va)[:, 1], 0.0, 1.0)
    p_te = np.clip(model.predict_proba(X_te)[:, 1], 0.0, 1.0)
    thr, val_f1 = tune_f1_threshold(y_va, p_va)
    te_pred = (p_te >= thr).astype(int)
    tp = int(((te_pred == 1) & (y_te == 1)).sum())
    fp = int(((te_pred == 1) & (y_te == 0)).sum())
    fn = int(((te_pred == 0) & (y_te == 1)).sum())
    prec = tp / max(1, tp + fp)
    rec = tp / max(1, tp + fn)
    f1 = 2 * prec * rec / max(1e-12, prec + rec)
    return {
        "model": name,
        "n_features": len(cols),
        "val_pr_auc": round(float(average_precision_score(y_va, p_va)), 4),
        "val_roc_auc": round(float(roc_auc_score(y_va, p_va)), 4),
        "val_f1": round(float(val_f1), 4),
        "test_pr_auc": round(float(average_precision_score(y_te, p_te)), 4),
        "test_roc_auc": round(float(roc_auc_score(y_te, p_te)), 4),
        "test_f1": round(float(f1), 4),
    }


def run_scientific_audit() -> Dict[str, Any]:
    logger.info("=== Running Phase 4 Scientific Audit (Experiments A–E) ===")
    raw_hist = pd.read_parquet(MULTIYEAR_HISTORICAL_CACHE_PATH)
    raw_hist["observation_date"] = pd.to_datetime(raw_hist["observation_date"])

    pipe = Phase4InferencePipeline(demo_mode=True, prefer_phase4=True)
    pipe.load_artifacts()

    # ------------------------------------------------------------------
    # Experiment A: Strictly Independent Nov 2024 Validation (2020-2023 ONLY)
    # ------------------------------------------------------------------
    hist_20_23 = raw_hist[raw_hist["observation_date"].dt.year <= 2023].copy()
    pipe._historical_reference_df = hist_20_23
    pipe._cached_env_df = None
    preds_a = pd.DataFrame(pipe.predict())
    prov_a = pipe.get_last_provenance()

    gt_fut = raw_hist[
        (raw_hist["observation_date"] >= "2024-11-26")
        & (raw_hist["observation_date"] <= "2024-12-10")
    ].groupby("grid_cell_id").agg(
        fut_days=("fishing_hours", lambda s: int((s > 1.0).sum())),
        fut_tot=("fishing_hours", "count"),
        fut_hrs=("fishing_hours", "sum"),
    ).reset_index()
    gt_nov = raw_hist[
        (raw_hist["observation_date"] >= "2024-11-15")
        & (raw_hist["observation_date"] <= "2024-12-05")
    ].groupby("grid_cell_id").agg(
        n24_days=("fishing_hours", lambda s: int((s > 1.0).sum())),
        n24_tot=("fishing_hours", "count"),
        n24_hrs=("fishing_hours", "sum"),
    ).reset_index()

    ma = preds_a.merge(gt_fut, on="grid_cell_id", how="left").merge(gt_nov, on="grid_cell_id", how="left")
    thr_s = float(preds_a["decision_threshold"].iloc[0])
    tiers_a: List[Dict[str, Any]] = []
    for label, mask in [
        ("HIGH", ma["predicted_apparent_fishing_binary"] == 1),
        ("MOD", (ma["predicted_apparent_fishing_binary"] == 0) & (ma["predicted_apparent_fishing_probability"] >= thr_s * 0.55)),
        ("LIGHT", (ma["predicted_apparent_fishing_probability"] >= min(0.05, thr_s * 0.25)) & (ma["predicted_apparent_fishing_probability"] < thr_s * 0.55)),
        ("VLOW", ma["predicted_apparent_fishing_probability"] < min(0.05, thr_s * 0.25)),
    ]:
        g = ma[mask]
        tiers_a.append(
            {
                "tier": label,
                "count": int(len(g)),
                "mean_predicted_p": round(float(g["predicted_apparent_fishing_probability"].mean()), 4) if len(g) else 0.0,
                "actual_daily_rate_nov26_dec10": round(float(g["fut_days"].sum() / max(1, g["fut_tot"].sum())), 4),
                "cells_fished_nov26_dec10": f"{int((g['fut_days'] > 0).sum())}/{len(g)}",
                "actual_daily_rate_nov15_dec05": round(float(g["n24_days"].sum() / max(1, g["n24_tot"].sum())), 4),
                "cells_fished_nov15_dec05": f"{int((g['n24_days'] > 0).sum())}/{len(g)}",
            }
        )
    hi_a = ma[ma["predicted_apparent_fishing_binary"] == 1]
    exp_a = {
        "anchor_date": prov_a["sources"]["global_fishing_watch"].get("seasonal_anchor_date"),
        "seasonal_threshold": thr_s,
        "tiers": tiers_a,
        "spearman_nov26_dec10": round(float(spearmanr(ma["predicted_apparent_fishing_probability"], ma["fut_hrs"])[0]), 4),
        "spearman_nov15_dec05": round(float(spearmanr(ma["predicted_apparent_fishing_probability"], ma["n24_hrs"])[0]), 4),
        "share_hours_nov26_dec10_in_high": round(float(hi_a["fut_hrs"].sum() / max(1e-6, ma["fut_hrs"].sum())), 4),
        "share_hours_nov15_dec05_in_high": round(float(hi_a["n24_hrs"].sum() / max(1e-6, ma["n24_hrs"].sum())), 4),
    }
    logger.info(f"Exp A (Zero-2024 Nov Test): thr={thr_s}, spearman_fut={exp_a['spearman_nov26_dec10']}, high_share={exp_a['share_hours_nov26_dec10_in_high']:.1%}")

    # ------------------------------------------------------------------
    # Build causal dataset once for Experiments B, C, D
    # ------------------------------------------------------------------
    ds = build_phase4_causal_dataset(
        source_parquet_paths=MULTIYEAR_HISTORICAL_CACHE_PATH,
        lookback_days=14,
        gfw_lag_days=0,
        ocean_cache_dir=OCEAN_CACHE_DIR,
        allow_ocean_fetch=False,
    )
    split_info = split_chronological_dataset(ds, multi_year_test_days=365)
    train_df = split_info["train_df"].copy()
    val_df = split_info["val_df"].copy()
    test_df = split_info["test_df"].copy()

    # ------------------------------------------------------------------
    # Experiment B: Full 2024 Daily & Seasonal Reliability Diagrams
    # ------------------------------------------------------------------
    y24 = (test_df["target_fishing_hours"].values > 1.0).astype(int)
    X1_24 = pipe._stage1_scaler.transform(pipe._stage1_imputer.transform(test_df[pipe._stage1_features]))
    test_s2 = test_df.copy()
    test_s2["habitat_suitability_score"] = np.clip(pipe._stage1_model.predict_proba(X1_24)[:, 1], 0.0, 1.0)
    X2_24 = pipe._stage2_scaler.transform(pipe._stage2_imputer.transform(test_s2[pipe._stage2_features]))
    p_raw_24 = np.clip(pipe._stage2_model.predict_proba(X2_24)[:, 1], 0.0, 1.0)
    p_daily_cal_24 = np.clip(pipe._calibrator.predict_proba(p_raw_24), 0.0, 1.0)

    # Seasonal 2024 evaluation using strictly 2020-2023 climatology
    mapper = SpatialAdjacencyMapper(raw_hist)
    clim_24 = build_seasonal_climatology_frame(raw_hist, split_info["test_dates"], mapper=mapper, noise_floor=1.0)
    ais_cols = [c for c in clim_24.columns if c not in ("grid_cell_id", "prediction_date_T")]
    w_s2 = test_s2.drop(columns=[c for c in ais_cols if c in test_s2.columns]).copy()
    w_s2["_pk"] = pd.to_datetime(w_s2["prediction_date_T"])
    clim_key = clim_24.rename(columns={"prediction_date_T": "_pk"}).copy()
    clim_key["_pk"] = pd.to_datetime(clim_key["_pk"])
    w_s2 = w_s2.merge(clim_key, on=["grid_cell_id", "_pk"], how="left")
    for c in ais_cols:
        w_s2[c] = w_s2[c].fillna(0.0)
    X2_seas = pipe._stage2_scaler.transform(pipe._stage2_imputer.transform(w_s2[pipe._stage2_features]))
    p_seas_raw_24 = np.clip(pipe._stage2_model.predict_proba(X2_seas)[:, 1], 0.0, 1.0)
    p_seas_with_daily_cal = np.clip(pipe._calibrator.predict_proba(p_seas_raw_24), 0.0, 1.0)
    p_seas_with_seas_cal = (
        np.clip(pipe._seasonal_calibrator.predict_proba(p_seas_raw_24), 0.0, 1.0)
        if pipe._seasonal_calibrator is not None
        else p_seas_with_daily_cal
    )

    exp_b = {
        "daily_test_2024": {
            "brier": round(float(brier_score_loss(y24, p_daily_cal_24)), 5),
            "pr_auc": round(float(average_precision_score(y24, p_daily_cal_24)), 4),
            "reliability": compute_reliability_diagram(y24, p_daily_cal_24),
        },
        "seasonal_climatology_2024_with_daily_calibrator": {
            "brier": round(float(brier_score_loss(y24, p_seas_with_daily_cal)), 5),
            "pr_auc": round(float(average_precision_score(y24, p_seas_with_daily_cal)), 4),
            "reliability": compute_reliability_diagram(y24, p_seas_with_daily_cal),
        },
        "seasonal_climatology_2024_with_seasonal_calibrator": {
            "brier": round(float(brier_score_loss(y24, p_seas_with_seas_cal)), 5),
            "pr_auc": round(float(average_precision_score(y24, p_seas_with_seas_cal)), 4),
            "reliability": compute_reliability_diagram(y24, p_seas_with_seas_cal),
        },
    }
    logger.info(
        f"Exp B (Calibration): Daily ECE={exp_b['daily_test_2024']['reliability']['ece']:.4f} | "
        f"Seasonal ECE naive={exp_b['seasonal_climatology_2024_with_daily_calibrator']['reliability']['ece']:.4f} -> "
        f"fixed={exp_b['seasonal_climatology_2024_with_seasonal_calibrator']['reliability']['ece']:.4f}"
    )

    # ------------------------------------------------------------------
    # Experiment C: Clean Oceanographic Ablation & Group Permutation Importance
    # ------------------------------------------------------------------
    ais_cols_only = [
        c for c in PHASE3_FEATURE_COLUMNS
        if c.startswith(("fishing_hours_", "regional_fishing_hours_"))
    ] + [c for c in SPATIAL_NEIGHBOR_FEATURES if not c.startswith("current_convergence")] + [
        "latitude", "longitude", "distance_to_coast_km", "is_coastal",
        "day_of_year", "month", "day_of_week", "sin_day_of_year", "cos_day_of_year",
    ]
    ocean_phys_no_isna = [
        "sst", "sst_spatial_gradient", "chl_a", "chl_a_lag3_mean", "chl_a_lag7_mean",
        "chl_a_lag14_mean", "chl_a_anomaly", "depth_m", "seabed_slope",
        "wave_height", "wave_period", "wave_direction_sin", "wave_direction_cos",
        "swell_wave_height", "ocean_current_velocity", "wind_speed", "current_convergence_proxy",
        "latitude", "longitude", "distance_to_coast_km", "is_coastal",
        "day_of_year", "month", "day_of_week", "sin_day_of_year", "cos_day_of_year",
    ]
    ocean_with_clean_isna = [c for c in STAGE1_HABITAT_FEATURES]
    ais_plus_ocean_no_isna = list(dict.fromkeys(ais_cols_only + ocean_phys_no_isna))

    ablations = [
        _fit_xgb_ablation(train_df, val_df, test_df, [c for c in ais_cols_only if c in ds.columns], "AIS_Plus_GeoCal_Only"),
        _fit_xgb_ablation(train_df, val_df, test_df, [c for c in ocean_phys_no_isna if c in ds.columns], "Ocean_Physical_No_ISNA_No_AIS"),
        _fit_xgb_ablation(train_df, val_df, test_df, [c for c in ocean_with_clean_isna if c in ds.columns], "Ocean_Clean_With_CloudLand_ISNA"),
        _fit_xgb_ablation(train_df, val_df, test_df, [c for c in ais_plus_ocean_no_isna if c in ds.columns], "Combined_AIS_Plus_Ocean_No_ISNA"),
    ]

    # Grouped Permutation Importance on Validation (PR-AUC drop across 3 seeds)
    y_val = (val_df["target_fishing_hours"].values > 1.0).astype(int)
    val_s2 = val_df.copy()
    X1_v = pipe._stage1_scaler.transform(pipe._stage1_imputer.transform(val_s2[pipe._stage1_features]))
    val_s2["habitat_suitability_score"] = np.clip(pipe._stage1_model.predict_proba(X1_v)[:, 1], 0.0, 1.0)
    X2_v_raw = val_s2[pipe._stage2_features].copy()
    base_val_p = np.clip(
        pipe._stage2_model.predict_proba(pipe._stage2_scaler.transform(pipe._stage2_imputer.transform(X2_v_raw)))[:, 1],
        0.0, 1.0,
    )
    base_val_pr = float(average_precision_score(y_val, base_val_p))

    perm_groups = {
        "self_ais_history": [c for c in pipe._stage2_features if c.startswith(("fishing_hours_", "regional_fishing_hours_"))],
        "spatial_neighbor_ais": [c for c in pipe._stage2_features if c.startswith("nbr_")],
        "stage1_habitat_score": ["habitat_suitability_score"],
        "bathymetry_depth_slope": [c for c in ("depth_m", "seabed_slope") if c in pipe._stage2_features],
        "sst_and_thermal_front": [c for c in ("sst", "sst_spatial_gradient", "sst_isna", "sst_spatial_gradient_isna") if c in pipe._stage2_features],
        "chlorophyll_a_blooms": [c for c in pipe._stage2_features if c.startswith("chl_a")],
        "waves_wind_currents": [c for c in ("wave_height", "wave_period", "wave_direction_sin", "wave_direction_cos", "swell_wave_height", "ocean_current_velocity", "wind_speed", "wind_speed_isna", "current_convergence_proxy") if c in pipe._stage2_features],
        "calendar_and_geo": [c for c in ("latitude", "longitude", "distance_to_coast_km", "is_coastal", "day_of_year", "month", "day_of_week", "sin_day_of_year", "cos_day_of_year") if c in pipe._stage2_features],
    }
    rng = np.random.default_rng(42)
    perm_importance: List[Dict[str, Any]] = []
    for gname, gcols in perm_groups.items():
        if not gcols:
            continue
        drops: List[float] = []
        for _ in range(3):
            X_perm = X2_v_raw.copy()
            perm_idx = rng.permutation(len(X_perm))
            for col in gcols:
                X_perm[col] = X_perm[col].values[perm_idx]
            p_perm = np.clip(
                pipe._stage2_model.predict_proba(pipe._stage2_scaler.transform(pipe._stage2_imputer.transform(X_perm)))[:, 1],
                0.0, 1.0,
            )
            drops.append(base_val_pr - float(average_precision_score(y_val, p_perm)))
        perm_importance.append(
            {
                "group": gname,
                "n_cols": len(gcols),
                "val_pr_auc_drop_mean": round(float(np.mean(drops)), 5),
                "val_pr_auc_drop_std": round(float(np.std(drops)), 5),
            }
        )
    perm_importance.sort(key=lambda r: r["val_pr_auc_drop_mean"], reverse=True)
    exp_c = {
        "ablations": ablations,
        "val_baseline_pr_auc": round(base_val_pr, 4),
        "permutation_importance_val": perm_importance,
    }
    logger.info(f"Exp C Ablations: {[(a['model'], a['test_pr_auc']) for a in ablations]}")

    # ------------------------------------------------------------------
    # Experiment D: Spatial Block Cross-Validation (Hold out district latitude bands)
    # ------------------------------------------------------------------
    ds_pre24 = ds[pd.to_datetime(ds["prediction_date_T"]).dt.year <= 2023].copy()
    blocks = [
        ("Sindhudurg_15.5_16.5", (15.5, 16.5)),
        ("Ratnagiri_16.5_17.5", (16.5, 17.5)),
        ("Raigad_17.5_18.5", (17.5, 18.5)),
        ("Mumbai_Palghar_18.5_20.5", (18.5, 20.5)),
    ]
    spatial_cv: List[Dict[str, Any]] = []
    for bname, (lat_lo, lat_hi) in blocks:
        m_test = (ds_pre24["latitude"] >= lat_lo) & (ds_pre24["latitude"] < lat_hi)
        tr_b = ds_pre24[~m_test]
        te_b = ds_pre24[m_test]
        y_tr_b = (tr_b["target_fishing_hours"].values > 1.0).astype(int)
        y_te_b = (te_b["target_fishing_hours"].values > 1.0).astype(int)

        # Stage-1 (Zero AIS) spatial generalization
        i1, s1 = SimpleImputer(strategy="median", keep_empty_features=True), StandardScaler()
        m1 = XGBClassifier(n_estimators=120, max_depth=4, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8, reg_lambda=2.0, scale_pos_weight=float((len(y_tr_b) - y_tr_b.sum()) / max(1, y_tr_b.sum())), eval_metric="logloss", random_state=42)
        m1.fit(s1.fit_transform(i1.fit_transform(tr_b[pipe._stage1_features])), y_tr_b)
        p1_te = m1.predict_proba(s1.transform(i1.transform(te_b[pipe._stage1_features])))[:, 1]

        # Full AIS+Spatial+Ocean generalization (Stage-2 direct features without OOF refit)
        s2_direct = [c for c in pipe._stage2_features if c != "habitat_suitability_score"]
        i2, s2 = SimpleImputer(strategy="median", keep_empty_features=True), StandardScaler()
        m2 = XGBClassifier(n_estimators=130, max_depth=4, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8, reg_lambda=2.0, scale_pos_weight=float((len(y_tr_b) - y_tr_b.sum()) / max(1, y_tr_b.sum())), eval_metric="logloss", random_state=42)
        m2.fit(s2.fit_transform(i2.fit_transform(tr_b[s2_direct])), y_tr_b)
        p2_te = m2.predict_proba(s2.transform(i2.transform(te_b[s2_direct])))[:, 1]

        spatial_cv.append(
            {
                "held_out_block": bname,
                "n_cells": int(te_b["grid_cell_id"].nunique()),
                "prevalence": round(float(y_te_b.mean()), 4),
                "stage1_ocean_only_pr_auc": round(float(average_precision_score(y_te_b, p1_te)), 4),
                "stage1_ocean_only_roc_auc": round(float(roc_auc_score(y_te_b, p1_te)), 4),
                "spatio_ocean_pr_auc": round(float(average_precision_score(y_te_b, p2_te)), 4),
                "spatio_ocean_roc_auc": round(float(roc_auc_score(y_te_b, p2_te)), 4),
            }
        )
    exp_d = {"leave_one_district_band_out_2020_2023": spatial_cv}
    logger.info(f"Exp D (Spatial CV): {[(s['held_out_block'], s['spatio_ocean_pr_auc']) for s in spatial_cv]}")

    # ------------------------------------------------------------------
    # Experiment E: Independent INCOIS PFZ Spatial Comparison
    # ------------------------------------------------------------------
    snap_path = Path("data/snapshots/map_summary_baseline.json")
    pfz_locs: List[Dict[str, Any]] = []
    if snap_path.exists():
        raw_bytes = snap_path.read_bytes()
        for enc in ("utf-8-sig", "utf-16", "utf-8"):
            try:
                pfz_locs = json.loads(raw_bytes.decode(enc)).get("pfz_advisory", {}).get("locations", [])
                break
            except Exception:
                continue

    bathy = pd.read_parquet(OCEAN_CACHE_DIR / "gebco_bathymetry_grid.parquet")
    preds_full = ma.merge(bathy[["grid_cell_id", "depth_m"]], on="grid_cell_id", how="left")
    hi_cells = preds_full[preds_full["predicted_apparent_fishing_binary"] == 1]

    pfz_stats: Dict[str, Any] = {"pfz_count": len(pfz_locs)}
    if pfz_locs and not preds_full.empty:
        pfz_depths: List[float] = []
        pfz_stage1_hab: List[float] = []
        pfz_stage2_p: List[float] = []
        nearest_high_dists: List[float] = []
        for loc in pfz_locs:
            pla, plo = float(loc["latitude"]), float(loc["longitude"])
            d_all = [_haversine_km(pla, plo, r.latitude, r.longitude) for r in preds_full.itertuples(index=False)]
            ni = int(np.argmin(d_all))
            row_n = preds_full.iloc[ni]
            if pd.notna(row_n.get("depth_m")):
                pfz_depths.append(float(row_n["depth_m"]))
            if pd.notna(row_n.get("habitat_suitability_score")):
                pfz_stage1_hab.append(float(row_n["habitat_suitability_score"]))
            pfz_stage2_p.append(float(row_n["predicted_apparent_fishing_probability"]))
            if not hi_cells.empty:
                nearest_high_dists.append(min(_haversine_km(pla, plo, r.latitude, r.longitude) for r in hi_cells.itertuples(index=False)))

        pfz_stats.update(
            {
                "pfz_nearest_cell_median_depth_m": round(float(np.median(pfz_depths)), 1) if pfz_depths else None,
                "gfw_high_cells_median_depth_m": round(float(hi_cells["depth_m"].median()), 1) if not hi_cells.empty else None,
                "pfz_mean_stage1_habitat_score": round(float(np.mean(pfz_stage1_hab)), 4) if pfz_stage1_hab else None,
                "all_cells_mean_stage1_habitat_score": round(float(preds_full["habitat_suitability_score"].mean()), 4),
                "pfz_mean_stage2_seasonal_p": round(float(np.mean(pfz_stage2_p)), 4),
                "median_distance_pfz_to_nearest_gfw_high_km": round(float(np.median(nearest_high_dists)), 1) if nearest_high_dists else None,
                "pfz_within_35km_of_gfw_high_pct": round(float(np.mean([d <= 35.0 for d in nearest_high_dists])), 4) if nearest_high_dists else None,
            }
        )
    exp_e = pfz_stats
    logger.info(f"Exp E (INCOIS PFZ comparison): {exp_e}")

    audit = {
        "run_id": pipe._metadata.get("run_id"),
        "experiment_a_independent_nov_2024": exp_a,
        "experiment_b_calibration_reliability": exp_b,
        "experiment_c_ocean_ablation_and_permutation": exp_c,
        "experiment_d_spatial_block_cv": exp_d,
        "experiment_e_incois_pfz_comparison": exp_e,
    }
    out_path = ARTIFACTS_DIR / "phase4_scientific_audit.json"
    out_path.write_text(json.dumps(audit, indent=2), encoding="utf-8")
    logger.info(f"Saved scientific audit report to {out_path}")
    return audit


if __name__ == "__main__":
    run_scientific_audit()
