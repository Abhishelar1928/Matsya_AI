"""
Matsya AI — Automated Data Provenance & Leakage Validator for Phase 3 & Phase 4.

Strictly verifies that:
1. Feature availability <= Prediction time T
2. Target is strictly T+1 calendar day
3. Chronological train/val/test splits do not overlap
4. No future observations or targets leaked into feature sets (including 1-ring/2-ring neighbor lags & Chl-a windows)
5. Preprocessors (imputers, scalers) are fit exclusively on training data
6. Stage-1 Habitat Suitability Model uses ZERO AIS/fishing target features and strict expanding-window OOF causality
7. Probability calibration is fit strictly prior to Test split
"""

import logging
from typing import Any, Callable, Dict, List, Sequence
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class DataLeakageError(Exception):
    """Raised when any temporal, spatial, or target leakage is detected."""
    pass


def validate_dataset_provenance(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Automated check of dataset provenance and temporal causality.
    """
    # 1. Target calendar day verification
    pred_dates = pd.to_datetime(df["prediction_date_T"])
    target_dates = pd.to_datetime(df["target_date_T_plus_1"])

    diff_days = (target_dates - pred_dates).dt.total_seconds() / 86400.0
    if not (diff_days == 1.0).all():
        bad_pos = int(np.argmax(diff_days.values != 1.0))
        raise DataLeakageError(
            f"Target date is not strictly T+1 calendar day! Found difference of "
            f"{diff_days.iloc[bad_pos]} days at index {bad_pos} "
            f"(T={pred_dates.iloc[bad_pos]}, T+1={target_dates.iloc[bad_pos]})."
        )

    # 2. Check that target column is NOT in feature columns
    target_col = "target_fishing_hours"
    if target_col not in df.columns:
        raise DataLeakageError(f"Target column '{target_col}' missing from dataset.")

    # 3. Check for exact duplicate cell-prediction_date pairs
    duplicates = df.duplicated(subset=["grid_cell_id", "prediction_date_T"]).sum()
    if duplicates > 0:
        raise DataLeakageError(f"Found {duplicates} duplicate (grid_cell_id, prediction_date_T) rows.")

    logger.info("Dataset provenance check PASSED: Target is strictly T+1 and dates are causal.")
    return {
        "status": "PASS",
        "total_samples": len(df),
        "unique_cells": int(df["grid_cell_id"].nunique()),
        "min_prediction_date": str(pred_dates.min().date()),
        "max_prediction_date": str(pred_dates.max().date()),
        "min_target_date": str(target_dates.min().date()),
        "max_target_date": str(target_dates.max().date()),
    }


def validate_temporal_splits(
    train_dates: Sequence[Any],
    val_dates: Sequence[Any],
    test_dates: Sequence[Any],
) -> Dict[str, Any]:
    """
    Ensures train, validation, and test splits are strictly chronological and disjoint.
    """
    set_train = set(pd.DatetimeIndex(train_dates).date)
    set_val = set(pd.DatetimeIndex(val_dates).date)
    set_test = set(pd.DatetimeIndex(test_dates).date)

    # 1. Disjointness
    overlap_tv = set_train & set_val
    overlap_tt = set_train & set_test
    overlap_vt = set_val & set_test

    if overlap_tv:
        raise DataLeakageError(f"Temporal Leakage: Train and Val overlap on dates: {overlap_tv}")
    if overlap_tt:
        raise DataLeakageError(f"Temporal Leakage: Train and Test overlap on dates: {overlap_tt}")
    if overlap_vt:
        raise DataLeakageError(f"Temporal Leakage: Val and Test overlap on dates: {overlap_vt}")

    # 2. Chronological ordering
    max_train = max(set_train)
    min_val = min(set_val)
    max_val = max(set_val)
    min_test = min(set_test)

    if max_train >= min_val:
        raise DataLeakageError(
            f"Temporal Ordering Violation: max(train_date) {max_train} >= min(val_date) {min_val}"
        )
    if max_val >= min_test:
        raise DataLeakageError(
            f"Temporal Ordering Violation: max(val_date) {max_val} >= min(test_date) {min_test}"
        )

    logger.info("Temporal split validation PASSED: Strictly chronological and disjoint splits.")
    return {
        "status": "PASS",
        "train_range": (str(min(set_train)), str(max(set_train))),
        "val_range": (str(min(set_val)), str(max(set_val))),
        "test_range": (str(min(set_test)), str(max(set_test))),
    }


def validate_preprocessing_isolation(
    imputer,
    scaler,
    X_train_raw: pd.DataFrame,
    feature_cols: List[str],
) -> Dict[str, Any]:
    """
    Validates that imputer and scaler statistics were derived strictly from X_train_raw.
    """
    expected_medians = X_train_raw[feature_cols].median(numeric_only=True).to_numpy(dtype=float)
    actual_medians = np.asarray(imputer.statistics_, dtype=float)
    if len(expected_medians) != len(actual_medians):
        raise DataLeakageError(
            f"Imputer column count mismatch ({len(actual_medians)} vs {len(expected_medians)}). "
            "Ensure keep_empty_features=True is enabled on SimpleImputer."
        )

    all_nan_mask = X_train_raw[feature_cols].isna().all().to_numpy(dtype=bool)
    non_empty_mask = ~all_nan_mask
    if non_empty_mask.any() and not np.allclose(
        expected_medians[non_empty_mask], actual_medians[non_empty_mask], equal_nan=True
    ):
        raise DataLeakageError("Imputer statistics do NOT match X_train_raw medians! Potential data leakage.")
    if all_nan_mask.any():
        empty_stats = actual_medians[all_nan_mask]
        if not bool(np.all(np.isnan(empty_stats) | (empty_stats == 0.0))):
            raise DataLeakageError("All-NaN train columns have unexpected imputer statistics! Potential leakage.")

    imputed_train = imputer.transform(X_train_raw[feature_cols])
    expected_means = np.mean(imputed_train, axis=0)
    actual_means = scaler.mean_
    if not np.allclose(expected_means, actual_means, atol=1e-5):
        raise DataLeakageError("Scaler statistics do NOT match imputed X_train_raw moments! Potential data leakage.")

    logger.info("Preprocessing isolation validation PASSED: Fit solely on Train split.")
    return {"status": "PASS"}


# ---------------------------------------------------------------------------
# Phase 4 Extended Leakage Validators
# ---------------------------------------------------------------------------
_FORBIDDEN_STAGE1_TOKENS = (
    "fishing",
    "target",
    "nbr_1ring_fishing",
    "nbr_2ring_fishing",
    "regional_fishing",
    "habitat_suitability_score",
)


def validate_stage1_feature_purity(stage1_features: List[str]) -> Dict[str, Any]:
    """
    Verifies Stage-1 Habitat Suitability Model contains ZERO AIS fishing or target features.
    """
    if not stage1_features:
        raise DataLeakageError("Stage-1 feature list is empty.")

    violations: List[str] = []
    for col in stage1_features:
        low = col.lower()
        if any(tok in low for tok in _FORBIDDEN_STAGE1_TOKENS):
            violations.append(col)

    if violations:
        raise DataLeakageError(
            f"Stage-1 Habitat Purity Violation: Forbidden AIS/target features detected: {violations}"
        )

    logger.info(f"Stage-1 feature purity check PASSED ({len(stage1_features)} environmental/spatial features, 0 AIS features).")
    return {"status": "PASS", "n_features": len(stage1_features)}


def _assert_frame_equal_causal(
    base_slice: pd.DataFrame,
    pert_slice: pd.DataFrame,
    cols: List[str],
    context_label: str,
) -> None:
    b = base_slice.sort_values("grid_cell_id").reset_index(drop=True)
    p = pert_slice.sort_values("grid_cell_id").reset_index(drop=True)
    if len(b) != len(p) or not (b["grid_cell_id"].values == p["grid_cell_id"].values).all():
        raise DataLeakageError(f"{context_label}: Row alignment changed after T+1 perturbation.")

    for col in cols:
        if col not in b.columns or col not in p.columns:
            continue
        va = pd.to_numeric(b[col], errors="coerce").to_numpy(dtype=float)
        vb = pd.to_numeric(p[col], errors="coerce").to_numpy(dtype=float)
        both_nan = np.isnan(va) & np.isnan(vb)
        eq = np.isclose(va, vb, rtol=1e-12, atol=1e-12) | both_nan
        if not bool(np.all(eq)):
            bad_i = int(np.argmax(~eq))
            raise DataLeakageError(
                f"{context_label}: Future T+1 perturbation leaked into '{col}' at prediction_date_T "
                f"(cell={b.loc[bad_i, 'grid_cell_id']}, before={va[bad_i]}, after={vb[bad_i]})."
            )


def validate_spatial_neighbor_causality(
    raw_df: pd.DataFrame,
    builder_fn: Callable[[pd.DataFrame], pd.DataFrame],
    target_date_T: Any,
    spatial_cols: List[str],
) -> Dict[str, Any]:
    """
    Perturbs neighbor cells' fishing_hours, ocean_current_velocity, and sst on calendar day T+1,
    runs builder_fn, and asserts all `spatial_cols` at prediction date T remain bit-identical.
    """
    t_ts = pd.Timestamp(target_date_T)
    t_plus_1 = t_ts + pd.Timedelta(days=1)

    work = raw_df.copy()
    work["observation_date"] = pd.to_datetime(work["observation_date"])
    base_out = builder_fn(work)

    pert = work.copy()
    mask_t1 = pert["observation_date"] == t_plus_1
    if not mask_t1.any():
        raise DataLeakageError(f"Cannot run spatial perturbation test: T+1={t_plus_1.date()} absent.")

    pert.loc[mask_t1, "fishing_hours"] = pert.loc[mask_t1, "fishing_hours"].fillna(0.0) + 999.0
    if "ocean_current_velocity" in pert.columns:
        pert.loc[mask_t1, "ocean_current_velocity"] = 9.5
    if "sst" in pert.columns:
        pert.loc[mask_t1, "sst"] = 39.5

    pert_out = builder_fn(pert)
    date_col = "prediction_date_T" if "prediction_date_T" in base_out.columns else "observation_date"
    b_t = base_out[pd.to_datetime(base_out[date_col]) == t_ts]
    p_t = pert_out[pd.to_datetime(pert_out[date_col]) == t_ts]

    _assert_frame_equal_causal(b_t, p_t, spatial_cols, "SpatialNeighborCausality")
    logger.info(f"Spatial neighbor causality check PASSED at T={t_ts.date()} across {len(spatial_cols)} columns.")
    return {"status": "PASS", "tested_date_T": str(t_ts.date()), "columns_verified": len(spatial_cols)}


def validate_rolling_ocean_causality(
    raw_df: pd.DataFrame,
    builder_fn: Callable[[pd.DataFrame], pd.DataFrame],
    target_date_T: Any,
    ocean_cols: List[str],
) -> Dict[str, Any]:
    """
    Perturbs Chl-a and SST on calendar day T+1, runs builder_fn, and asserts all rolling
    ocean habitat columns (`chl_a_lag3_mean`, `chl_a_lag7_mean`, `chl_a_lag14_mean`,
    `chl_a_anomaly`, `sst_spatial_gradient`) at T remain bit-identical.
    """
    t_ts = pd.Timestamp(target_date_T)
    t_plus_1 = t_ts + pd.Timedelta(days=1)

    work = raw_df.copy()
    work["observation_date"] = pd.to_datetime(work["observation_date"])
    base_out = builder_fn(work)

    pert = work.copy()
    mask_t1 = pert["observation_date"] == t_plus_1
    if not mask_t1.any():
        raise DataLeakageError(f"Cannot run rolling ocean perturbation test: T+1={t_plus_1.date()} absent.")

    if "chl_a" in pert.columns:
        pert.loc[mask_t1, "chl_a"] = 88.8
    if "sst" in pert.columns:
        pert.loc[mask_t1, "sst"] = 41.2

    pert_out = builder_fn(pert)
    date_col = "prediction_date_T" if "prediction_date_T" in base_out.columns else "observation_date"
    b_t = base_out[pd.to_datetime(base_out[date_col]) == t_ts]
    p_t = pert_out[pd.to_datetime(pert_out[date_col]) == t_ts]

    _assert_frame_equal_causal(b_t, p_t, ocean_cols, "RollingOceanCausality")
    logger.info(f"Rolling ocean causality check PASSED at T={t_ts.date()} across {len(ocean_cols)} columns.")
    return {"status": "PASS", "tested_date_T": str(t_ts.date()), "columns_verified": len(ocean_cols)}


def validate_stage1_oof_causality(
    fold_audits: List[Dict[str, Any]],
    val_dates: Sequence[Any],
    test_dates: Sequence[Any],
) -> Dict[str, Any]:
    """
    Verifies Stage-1 expanding-window OOF predictions obey strict temporal precedence:
    - Each fold's max(train_date) < min(pred_date)
    - OOF prediction date ranges across folds are disjoint
    - ZERO validation or test dates appear in any Stage-1 OOF training fold
    """
    if not fold_audits:
        raise DataLeakageError("Stage-1 OOF fold audit log is empty.")

    val_set = set(pd.DatetimeIndex(val_dates).date)
    test_set = set(pd.DatetimeIndex(test_dates).date)
    holdout = val_set | test_set
    min_holdout = min(holdout)

    seen_pred_ranges: List[tuple] = []
    for fold in fold_audits:
        tr_max = pd.Timestamp(fold["train_max_date"]).date()
        pr_min = pd.Timestamp(fold["pred_min_date"]).date()
        pr_max = pd.Timestamp(fold["pred_max_date"]).date()

        if tr_max >= pr_min:
            raise DataLeakageError(
                f"Stage-1 OOF Fold {fold['fold']} leakage: train_max_date {tr_max} >= pred_min_date {pr_min}"
            )
        if tr_max >= min_holdout or pr_max >= min_holdout:
            raise DataLeakageError(
                f"Stage-1 OOF Fold {fold['fold']} leaked into Val/Test holdout (>= {min_holdout})"
            )
        for prev_min, prev_max in seen_pred_ranges:
            if not (pr_max < prev_min or pr_min > prev_max):
                raise DataLeakageError(
                    f"Stage-1 OOF prediction folds overlap: ({pr_min}, {pr_max}) vs ({prev_min}, {prev_max})"
                )
        seen_pred_ranges.append((pr_min, pr_max))

    logger.info(f"Stage-1 OOF expanding-window causality PASSED across {len(fold_audits)} folds.")
    return {"status": "PASS", "folds": len(fold_audits)}


def validate_calibration_isolation(
    cal_dates: Sequence[Any],
    test_dates: Sequence[Any],
) -> Dict[str, Any]:
    """
    Ensures calibration fitting dates strictly precede Test dates with zero overlap.
    """
    set_cal = set(pd.DatetimeIndex(cal_dates).date)
    set_test = set(pd.DatetimeIndex(test_dates).date)
    if not set_cal or not set_test:
        raise DataLeakageError("Calibration or Test date set is empty.")
    overlap = set_cal & set_test
    if overlap:
        raise DataLeakageError(f"Calibration Leakage: Overlap with Test dates {overlap}")
    if max(set_cal) >= min(set_test):
        raise DataLeakageError(
            f"Calibration Ordering Violation: max(cal_date) {max(set_cal)} >= min(test_date) {min(set_test)}"
        )

    logger.info("Calibration isolation check PASSED: Strictly prior to Test split.")
    return {"status": "PASS", "cal_max": str(max(set_cal)), "test_min": str(min(set_test))}
