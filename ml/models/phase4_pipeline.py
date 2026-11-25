"""
MatsyaAI Maharashtra — Phase 4 Two-Stage Model & Probability Calibration Primitives.

Importable module (so joblib serialization never depends on __main__) containing:
1. ProbabilityCalibrator: Isotonic Regression or Platt (logit logistic regression) scaling
2. Stage-1 (HabitatSuitabilityModel) & Stage-2 (OperationalActivityModel) estimator builders
3. Chronological dataset splitter (multi-year full-year test vs single-year 60/20/20 fallback)
4. Expanding-window strict-causal out-of-fold Stage-1 scoring (`generate_expanding_oof_stage1`)
5. Validation OOF calibration selection + F1 threshold tuner (`fit_calibrator_and_tune_threshold`)
6. Phase 4 evaluation metrics (PR-AUC, ROC-AUC, F1, Brier Score, daily Precision@top-K)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from ml.evaluation.leakage_validator import (
    validate_calibration_isolation,
    validate_preprocessing_isolation,
    validate_stage1_feature_purity,
    validate_temporal_splits,
)
from ml.models.baselines import compute_classification_metrics

logger = logging.getLogger(__name__)

try:
    from lightgbm import LGBMClassifier  # type: ignore
    LIGHTGBM_AVAILABLE = True
except ImportError:
    LGBMClassifier = None
    LIGHTGBM_AVAILABLE = False


class ProbabilityCalibrator:
    """
    Post-hoc probability calibrator supporting:
    - 'isotonic': non-parametric monotonic calibration on [0, 1]
    - 'platt': logistic calibration on clipped log-odds logit(p)
    """

    def __init__(self, method: str = "isotonic", target_prior: Optional[float] = None):
        if method not in ("isotonic", "platt"):
            raise ValueError(f"Unsupported calibration method: {method}")
        self.method = method
        self.target_prior = float(target_prior) if target_prior is not None else None
        self._calibrator: Any = None
        self._source_prior: float = 0.05
        self._fallback_prior: float = 0.05

    @staticmethod
    def _to_logits(probs: np.ndarray) -> np.ndarray:
        clipped = np.clip(np.asarray(probs, dtype=float), 1e-6, 1.0 - 1e-6)
        return np.log(clipped / (1.0 - clipped)).reshape(-1, 1)

    @staticmethod
    def _apply_bayes_prior_shift(
        probs: np.ndarray, source_prior: float, target_prior: float
    ) -> np.ndarray:
        """
        Saerens-Latinne-Decaestecker exact Bayes prior-rate adjustment.
        Strictly monotonic shift from calibration source base rate (e.g. monsoon Val)
        to target operational base rate (e.g. annual Train prior).
        """
        p = np.clip(np.asarray(probs, dtype=float), 1e-6, 1.0 - 1e-6)
        pi_src = float(np.clip(source_prior, 1e-5, 1.0 - 1e-5))
        pi_tgt = float(np.clip(target_prior, 1e-5, 1.0 - 1e-5))
        num = p * (pi_tgt / pi_src)
        den = num + (1.0 - p) * ((1.0 - pi_tgt) / (1.0 - pi_src))
        return np.clip(num / np.maximum(den, 1e-12), 0.0, 1.0)

    def fit(self, raw_probs: np.ndarray, y_true: np.ndarray) -> "ProbabilityCalibrator":
        p = np.clip(np.asarray(raw_probs, dtype=float), 0.0, 1.0)
        y = np.asarray(y_true, dtype=int)
        emp_prior = float(np.mean(y)) if len(y) > 0 else 0.05
        self._source_prior = float(np.clip(emp_prior, 1e-5, 1.0 - 1e-5))
        self._fallback_prior = emp_prior

        if len(np.unique(y)) < 2:
            self._calibrator = None
            return self

        if self.method == "isotonic":
            iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
            iso.fit(p, y)
            self._calibrator = iso
        else:
            lr = LogisticRegression(C=1.0, max_iter=1000, random_state=42)
            lr.fit(self._to_logits(p), y)
            self._calibrator = lr
        return self

    def predict_proba(self, raw_probs: np.ndarray) -> np.ndarray:
        p = np.clip(np.asarray(raw_probs, dtype=float), 0.0, 1.0)
        if self._calibrator is None:
            out = np.full(len(p), self._fallback_prior, dtype=float)
        elif self.method == "isotonic":
            out = np.clip(np.asarray(self._calibrator.predict(p), dtype=float), 0.0, 1.0)
        else:
            out = np.clip(np.asarray(self._calibrator.predict_proba(self._to_logits(p))[:, 1], dtype=float), 0.0, 1.0)

        if self.target_prior is not None and 0.0 < self.target_prior < 1.0:
            out = self._apply_bayes_prior_shift(out, self._source_prior, self.target_prior)
        return np.clip(out, 0.0, 1.0)


def build_stage1_estimator(
    scale_pos_weight: float,
    random_state: int = 42,
) -> Tuple[Any, str]:
    """
    Build Stage-1 HabitatSuitabilityModel: LightGBM if installed, otherwise regularized XGBoost.
    """
    if LIGHTGBM_AVAILABLE and LGBMClassifier is not None:
        model = LGBMClassifier(
            n_estimators=140,
            max_depth=4,
            num_leaves=15,
            learning_rate=0.04,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_lambda=2.0,
            scale_pos_weight=scale_pos_weight,
            random_state=random_state,
            verbose=-1,
        )
        return model, "LGBMClassifier"

    model = XGBClassifier(
        n_estimators=120,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_lambda=2.0,
        scale_pos_weight=scale_pos_weight,
        eval_metric="logloss",
        random_state=random_state,
    )
    return model, "XGBClassifier"


def build_stage2_estimator(
    scale_pos_weight: float,
    random_state: int = 42,
) -> XGBClassifier:
    """
    Build Stage-2 OperationalActivityModel combining habitat suitability, spatial neighbor
    AIS momentum, weather, and coastal distance.
    """
    return XGBClassifier(
        n_estimators=150,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_lambda=2.0,
        scale_pos_weight=scale_pos_weight,
        eval_metric="logloss",
        random_state=random_state,
    )


def split_chronological_dataset(
    dataset_df: pd.DataFrame,
    multi_year_test_days: int = 365,
) -> Dict[str, Any]:
    """
    Strictly chronological Train / Validation / Test split:
    - Multi-year spans (>= 700 unique prediction days): reserves the final 365 days as a full
      seasonal-cycle Test year, preceding 20% of remaining days (clamped 90..365) as Validation,
      and earlier history as Train.
    - Single-year spans (< 700 days, e.g. 2023): preserves Phase 3 60% / 20% / 20% split.
    """
    pred_dates = sorted(pd.to_datetime(dataset_df["prediction_date_T"]).dt.date.unique())
    n_dates = len(pred_dates)
    if n_dates < 12:
        raise ValueError(f"Need at least 12 unique prediction dates to split; got {n_dates}")

    if n_dates >= 700 and n_dates > multi_year_test_days + 180:
        test_days = int(multi_year_test_days)
        pre_test_count = n_dates - test_days
        val_days = min(365, max(90, int(round(pre_test_count * 0.20))))
        train_days = pre_test_count - val_days
        train_dates = pred_dates[:train_days]
        val_dates = pred_dates[train_days:pre_test_count]
        test_dates = pred_dates[pre_test_count:]
        split_mode = "multi_year_full_test_year"
    else:
        train_cutoff = max(4, int(n_dates * 0.60))
        val_cutoff = max(train_cutoff + 2, int(n_dates * 0.80))
        if val_cutoff >= n_dates:
            val_cutoff = n_dates - 1
        train_dates = pred_dates[:train_cutoff]
        val_dates = pred_dates[train_cutoff:val_cutoff]
        test_dates = pred_dates[val_cutoff:]
        split_mode = "single_year_60_20_20"

    validate_temporal_splits(train_dates, val_dates, test_dates)

    pdate_series = pd.to_datetime(dataset_df["prediction_date_T"]).dt.date
    train_df = dataset_df[pdate_series.isin(train_dates)].copy()
    val_df = dataset_df[pdate_series.isin(val_dates)].copy()
    test_df = dataset_df[pdate_series.isin(test_dates)].copy()

    return {
        "split_mode": split_mode,
        "train_dates": train_dates,
        "val_dates": val_dates,
        "test_dates": test_dates,
        "train_df": train_df,
        "val_df": val_df,
        "test_df": test_df,
    }


def generate_expanding_oof_stage1(
    train_df: pd.DataFrame,
    stage1_features: List[str],
    target_threshold: float = 1.0,
    n_blocks: int = 5,
    random_state: int = 42,
) -> Tuple[pd.DataFrame, List[Dict[str, Any]], Dict[str, Any]]:
    """
    Generate strictly causal out-of-fold `habitat_suitability_score` predictions on Train
    using an expanding chronological window:
      - Fold k trains only on sequential blocks B_0..B_{k-1} and predicts on B_k.
      - Warm-up block B_0 is dynamically extended if needed so both classes are present.
      - Final Stage-1 model + preprocessors are fit on 100% of Train for Val/Test/Inference.
    """
    validate_stage1_feature_purity(stage1_features)

    work = train_df.copy()
    work["_pdate"] = pd.to_datetime(work["prediction_date_T"]).dt.date
    unique_dates = sorted(work["_pdate"].unique())
    if len(unique_dates) < 4:
        raise ValueError(f"Need at least 4 training dates for expanding OOF; got {len(unique_dates)}")

    eff_blocks = min(n_blocks, max(2, len(unique_dates) // 2))
    raw_blocks = [list(b) for b in np.array_split(unique_dates, eff_blocks) if len(b) > 0]

    # Merge initial blocks until block 0 has both positive and negative classes
    y_all = (work["target_fishing_hours"].values > target_threshold).astype(int)
    while len(raw_blocks) > 2:
        b0_mask = work["_pdate"].isin(raw_blocks[0]).values
        if len(np.unique(y_all[b0_mask])) >= 2:
            break
        raw_blocks[0] = raw_blocks[0] + raw_blocks[1]
        raw_blocks.pop(1)

    oof_frames: List[pd.DataFrame] = []
    fold_audits: List[Dict[str, Any]] = []

    for k in range(1, len(raw_blocks)):
        fold_train_dates = [d for b in raw_blocks[:k] for d in b]
        fold_pred_dates = raw_blocks[k]

        tr_mask = work["_pdate"].isin(fold_train_dates).values
        pr_mask = work["_pdate"].isin(fold_pred_dates).values

        tr_sub = work.iloc[tr_mask]
        pr_sub = work.iloc[pr_mask].copy()

        y_tr = (tr_sub["target_fishing_hours"].values > target_threshold).astype(int)
        imp = SimpleImputer(strategy="median", keep_empty_features=True)
        scl = StandardScaler()

        X_tr_imp = imp.fit_transform(tr_sub[stage1_features])
        X_tr_scl = scl.fit_transform(X_tr_imp)
        X_pr_scl = scl.transform(imp.transform(pr_sub[stage1_features]))

        if len(np.unique(y_tr)) < 2:
            pr_sub["habitat_suitability_score"] = float(np.mean(y_tr))
        else:
            pos = int(y_tr.sum())
            neg = int(len(y_tr) - pos)
            spw = float(neg / max(1, pos))
            est, _ = build_stage1_estimator(scale_pos_weight=spw, random_state=random_state)
            est.fit(X_tr_scl, y_tr)
            pr_sub["habitat_suitability_score"] = np.clip(est.predict_proba(X_pr_scl)[:, 1], 0.0, 1.0)

        oof_frames.append(pr_sub.drop(columns=["_pdate"]))
        fold_audits.append(
            {
                "fold": k,
                "train_min_date": str(min(fold_train_dates)),
                "train_max_date": str(max(fold_train_dates)),
                "pred_min_date": str(min(fold_pred_dates)),
                "pred_max_date": str(max(fold_pred_dates)),
                "n_train": int(len(tr_sub)),
                "n_pred": int(len(pr_sub)),
                "train_pos": int(y_tr.sum()),
            }
        )

    stage2_train_df = pd.concat(oof_frames, ignore_index=True)

    # Fit final Stage-1 bundle strictly on full Train split
    y_full_train = (work["target_fishing_hours"].values > target_threshold).astype(int)
    pos_full = int(y_full_train.sum())
    neg_full = int(len(y_full_train) - pos_full)
    spw_full = float(neg_full / max(1, pos_full))

    final_imp = SimpleImputer(strategy="median", keep_empty_features=True)
    final_scl = StandardScaler()
    X_full_raw = work[stage1_features]
    X_full_imp = final_imp.fit_transform(X_full_raw)
    X_full_scl = final_scl.fit_transform(X_full_imp)
    validate_preprocessing_isolation(final_imp, final_scl, X_full_raw, stage1_features)

    final_est, algo_name = build_stage1_estimator(scale_pos_weight=spw_full, random_state=random_state)
    final_est.fit(X_full_scl, y_full_train)

    final_bundle = {
        "model": final_est,
        "imputer": final_imp,
        "scaler": final_scl,
        "algorithm": algo_name,
        "features": list(stage1_features),
        "scale_pos_weight": spw_full,
    }
    return stage2_train_df, fold_audits, final_bundle


def score_stage1_bundle(
    stage1_bundle: Dict[str, Any],
    df: pd.DataFrame,
) -> np.ndarray:
    """Apply frozen Stage-1 bundle to output habitat_suitability_score in [0, 1]."""
    feats = stage1_bundle["features"]
    X_imp = stage1_bundle["imputer"].transform(df[feats])
    X_scl = stage1_bundle["scaler"].transform(X_imp)
    return np.clip(stage1_bundle["model"].predict_proba(X_scl)[:, 1], 0.0, 1.0)


def tune_f1_threshold(
    y_true: np.ndarray,
    scores: np.ndarray,
    min_t: float = 0.05,
    max_t: float = 0.95,
    steps: int = 91,
) -> Tuple[float, float]:
    """Find decision threshold maximizing binary F1 without touching Test."""
    best_t = 0.5
    best_f1 = -1.0
    for t in np.linspace(min_t, max_t, steps):
        preds = (scores >= t).astype(int)
        res = compute_classification_metrics(y_true, scores, preds)
        if res["f1"] > best_f1:
            best_f1 = res["f1"]
            best_t = float(round(float(t), 4))
    return best_t, float(best_f1)


def fit_calibrator_and_tune_threshold(
    val_df: pd.DataFrame,
    y_val: np.ndarray,
    raw_val_probs: np.ndarray,
    test_dates: Optional[Sequence[Any]] = None,
    target_prior: Optional[float] = None,
) -> Tuple[ProbabilityCalibrator, float, Dict[str, Any]]:
    """
    Evaluate Isotonic vs Platt calibration honestly via chronological K-fold OOF inside Validation:
    - Evaluates Validation OOF Brier Score at Validation's empirical base rate
    - Applies optional leak-free Bayes prior adjustment (`target_prior` from Train)
    - Tunes F1 threshold on adjusted Validation OOF calibrated probabilities
    - Refits the winning calibrator on full Validation split for downstream Test & inference
    """
    val_dates = sorted(pd.to_datetime(val_df["prediction_date_T"]).dt.date.unique())
    if test_dates is not None and len(list(test_dates)) > 0:
        validate_calibration_isolation(val_dates, test_dates)

    val_pdates = pd.to_datetime(val_df["prediction_date_T"]).dt.date.values
    n_folds = 3 if len(val_dates) >= 9 else 2
    folds = [set(b) for b in np.array_split(val_dates, n_folds) if len(b) > 0]

    oof_unshifted: Dict[str, np.ndarray] = {
        "isotonic": np.copy(raw_val_probs),
        "platt": np.copy(raw_val_probs),
    }
    oof_adjusted: Dict[str, np.ndarray] = {
        "isotonic": np.copy(raw_val_probs),
        "platt": np.copy(raw_val_probs),
    }

    for fold_dates in folds:
        val_m = np.isin(val_pdates, list(fold_dates))
        tr_m = ~val_m
        if int(tr_m.sum()) == 0 or len(np.unique(y_val[tr_m])) < 2:
            continue
        for method in ("isotonic", "platt"):
            cal_raw = ProbabilityCalibrator(method=method, target_prior=None).fit(raw_val_probs[tr_m], y_val[tr_m])
            oof_unshifted[method][val_m] = cal_raw.predict_proba(raw_val_probs[val_m])

            cal_adj = ProbabilityCalibrator(method=method, target_prior=target_prior).fit(raw_val_probs[tr_m], y_val[tr_m])
            oof_adjusted[method][val_m] = cal_adj.predict_proba(raw_val_probs[val_m])

    raw_brier = float(brier_score_loss(y_val, np.clip(raw_val_probs, 0.0, 1.0)))
    iso_brier = float(brier_score_loss(y_val, np.clip(oof_unshifted["isotonic"], 0.0, 1.0)))
    platt_brier = float(brier_score_loss(y_val, np.clip(oof_unshifted["platt"], 0.0, 1.0)))

    # Prefer Platt when within 0.002 Brier of Isotonic because Platt is strictly monotonic
    # and preserves continuous probability ranking (PR-AUC / ROC-AUC) without flat steps.
    winning_method = "isotonic" if iso_brier + 0.002 < platt_brier else "platt"
    best_t, val_oof_f1 = tune_f1_threshold(y_val, oof_adjusted[winning_method])

    final_cal = ProbabilityCalibrator(method=winning_method, target_prior=target_prior)
    final_cal.fit(raw_val_probs, y_val)

    val_prior = float(np.mean(y_val)) if len(y_val) > 0 else 0.0
    cal_report = {
        "selected_method": winning_method,
        "val_prior": round(val_prior, 6),
        "target_prior": round(float(target_prior), 6) if target_prior is not None else round(val_prior, 6),
        "val_oof_brier_uncalibrated": round(raw_brier, 6),
        "val_oof_brier_isotonic": round(iso_brier, 6),
        "val_oof_brier_platt": round(platt_brier, 6),
        "val_oof_f1_calibrated": round(val_oof_f1, 6),
        "tuned_decision_threshold": best_t,
    }
    return final_cal, best_t, cal_report


DEFAULT_RELIABILITY_BINS: Tuple[float, ...] = (0.0, 0.05, 0.15, 0.30, 0.44, 0.60, 0.80, 1.01)


def compute_reliability_diagram(
    y_true: np.ndarray,
    probs: np.ndarray,
    bin_edges: Sequence[float] = DEFAULT_RELIABILITY_BINS,
) -> Dict[str, Any]:
    """Compute binned calibration reliability table and Expected Calibration Error (ECE)."""
    y_arr = np.asarray(y_true, dtype=int)
    p_arr = np.clip(np.asarray(probs, dtype=float), 0.0, 1.0)
    n_tot = max(1, len(y_arr))
    bins_out: List[Dict[str, Any]] = []
    ece = 0.0
    for lo, hi in zip(bin_edges[:-1], bin_edges[1:]):
        mask = (p_arr >= lo) & (p_arr < hi)
        cnt = int(mask.sum())
        if cnt == 0:
            continue
        mp = float(np.mean(p_arr[mask]))
        obs = float(np.mean(y_arr[mask]))
        gap = mp - obs
        ece += (cnt / n_tot) * abs(gap)
        bins_out.append(
            {
                "bin_low": round(float(lo), 4),
                "bin_high": round(min(1.0, float(hi)), 4),
                "count": cnt,
                "mean_predicted": round(mp, 6),
                "observed_rate": round(obs, 6),
                "gap": round(gap, 6),
            }
        )
    return {"ece": round(float(ece), 6), "bins": bins_out}


def build_seasonal_climatology_frame(
    hist_df: pd.DataFrame,
    target_dates: Sequence[Any],
    mapper: Optional[Any] = None,
    noise_floor: float = 1.0,
) -> pd.DataFrame:
    """
    Build strictly prior-year 14-day seasonal climatology AIS features for each target date T.
    For every unique calendar date T (from year Y), averages `fishing_hours` over prior years
    strictly < Y within T's trailing 14-day day-of-year window, applying `< noise_floor -> 0.0`,
    then computes causal self-AIS and spatial neighbor AIS features.
    """
    from ml.features.features_spatial_ocean import (
        SpatialAdjacencyMapper,
        compute_spatial_neighborhood_features,
    )

    if mapper is None:
        mapper = SpatialAdjacencyMapper(hist_df)

    work = hist_df[["grid_cell_id", "observation_date", "fishing_hours"]].copy()
    work["obs_dt"] = pd.to_datetime(work["observation_date"])
    work["obs_year"] = work["obs_dt"].dt.year
    work["doy"] = work["obs_dt"].dt.dayofyear
    work["fishing_hours"] = work["fishing_hours"].fillna(0.0).astype(float)
    cell_ids = mapper.cell_ids
    n_cells = len(cell_ids)

    # Pre-aggregate per (year, doy, cell) matrix indexed by doy for fast vectorized lookup
    by_year_doy = (
        work.groupby(["obs_year", "doy", "grid_cell_id"], as_index=False)["fishing_hours"]
        .mean()
    )

    parsed_targets = sorted({pd.Timestamp(d) for d in target_dates})
    by_target_yr: Dict[int, List[pd.Timestamp]] = {}
    for ts in parsed_targets:
        by_target_yr.setdefault(int(ts.year), []).append(ts)

    # Group target dates by target year so each year uses strictly prior years < target_year
    rows_out: List[pd.DataFrame] = []
    for target_year, yr_dates in sorted(by_target_yr.items()):
        prior = by_year_doy[by_year_doy["obs_year"] < int(target_year)]
        if prior.empty:
            continue

        # Average across all prior years (< target_year) for each (doy, grid_cell_id)
        doy_clim = prior.groupby(["doy", "grid_cell_id"], as_index=False)["fishing_hours"].mean()
        mat_df = (
            doy_clim.pivot(index="doy", columns="grid_cell_id", values="fishing_hours")
            .reindex(index=range(1, 367), columns=cell_ids)
            .fillna(0.0)
        )
        arr_full = mat_df.values  # shape (366, n_cells), row idx = doy - 1
        arr_full[arr_full < noise_floor] = 0.0
        # 366 -> map to 365 if sparse; wrap cyclically over 1..365
        arr = arr_full[:365]  # (365, n_cells)

        r1_adj = mapper.ring1_adj
        r2_adj = mapper.ring2_adj
        r1_cnt = np.maximum(1.0, r1_adj.sum(axis=1))
        r2_cnt = np.maximum(1.0, r2_adj.sum(axis=1))

        # Vectorized evaluation across every target date in `target_year`
        for ts in yr_dates:
            tdoy = min(365, int(ts.timetuple().tm_yday))
            # Trailing 14 DOYs: [tdoy-13 .. tdoy] wrapped modulo 365
            win14_idx = [((tdoy - 13 + k - 1) % 365) for k in range(14)]
            w14 = arr[win14_idx]  # (14, n_cells)
            w7 = w14[-7:]         # (7, n_cells)
            recent = w14[-1]
            lag1 = w14[-2]
            lag2 = w14[-3]
            lag3 = w14[-4]

            # Spatial 1-ring & 2-ring summaries on climatological window
            nbr1_recent = w14[-1] @ r1_adj.T / r1_cnt
            # Row-wise max over non-zero adjacency neighbors
            nbr1_max_recent = np.max(w14[-1][None, :] * r1_adj, axis=1)
            nbr1_act_recent = ((w14[-1] > 0.0).astype(float)) @ r1_adj.T
            w7_mean = w7.mean(axis=0)
            nbr1_7d_mean = w7_mean @ r1_adj.T / r1_cnt
            w7_max = w7.max(axis=0)
            nbr1_7d_max = np.max(w7_max[None, :] * r1_adj, axis=1)
            w7_any = (w7 > 0.0).any(axis=0).astype(float)
            nbr1_7d_act = w7_any @ r1_adj.T
            nbr2_mean = w14[-1] @ r2_adj.T / r2_cnt

            date_df = pd.DataFrame(
                {
                    "grid_cell_id": cell_ids,
                    "prediction_date_T": ts,
                    "fishing_hours_recent": recent,
                    "fishing_hours_lag_1": lag1,
                    "fishing_hours_lag_2": lag2,
                    "fishing_hours_lag_3": lag3,
                    "fishing_hours_7d_mean": w7_mean,
                    "fishing_hours_7d_max": w7_max,
                    "fishing_hours_7d_std": w7.std(axis=0),
                    "fishing_hours_7d_pos_freq": (w7 > 0.0).mean(axis=0),
                    "fishing_hours_14d_mean": w14.mean(axis=0),
                    "regional_fishing_hours_T": float(recent.sum()),
                    "nbr_1ring_fishing_mean": nbr1_recent,
                    "nbr_1ring_fishing_max": nbr1_max_recent,
                    "nbr_1ring_active_count": nbr1_act_recent,
                    "nbr_1ring_fishing_7d_mean": nbr1_7d_mean,
                    "nbr_1ring_fishing_7d_max": nbr1_7d_max,
                    "nbr_1ring_active_7d_count": nbr1_7d_act,
                    "nbr_2ring_fishing_mean": nbr2_mean,
                }
            )
            rows_out.append(date_df)

    if not rows_out:
        return pd.DataFrame()
    return pd.concat(rows_out, ignore_index=True)


def compute_phase4_metrics(
    eval_df: pd.DataFrame,
    y_true: np.ndarray,
    probs: np.ndarray,
    preds: np.ndarray,
    top_ks: Sequence[int] = (5, 10, 15, 20),
) -> Dict[str, Any]:
    """
    Compute complete Phase 4 metrics:
    - PR-AUC, ROC-AUC, Precision, Recall, F1, Confusion Matrix
    - Brier Score + binned Reliability Diagram / ECE
    - Daily Precision@top-K across all evaluation days AND across active days
    """
    y_arr = np.asarray(y_true, dtype=int)
    p_arr = np.clip(np.asarray(probs, dtype=float), 0.0, 1.0)
    pred_arr = np.asarray(preds, dtype=int)

    metrics = compute_classification_metrics(y_arr, p_arr, pred_arr)
    metrics["brier_score"] = float(brier_score_loss(y_arr, p_arr))
    metrics["reliability"] = compute_reliability_diagram(y_arr, p_arr)

    work = pd.DataFrame(
        {
            "date": pd.to_datetime(eval_df["prediction_date_T"]).dt.date.values,
            "y": y_arr,
            "p": p_arr,
        }
    )

    p_at_k: Dict[str, float] = {}
    p_at_k_active: Dict[str, float] = {}
    grouped = list(work.groupby("date", sort=True))

    for k in top_ks:
        all_day_vals: List[float] = []
        act_day_vals: List[float] = []
        for _d, g in grouped:
            if len(g) < k:
                continue
            top = g.sort_values("p", ascending=False).iloc[:k]
            prec_k = float(top["y"].mean())
            all_day_vals.append(prec_k)
            if int(g["y"].sum()) > 0:
                act_day_vals.append(prec_k)
        p_at_k[f"p@{k}"] = round(float(np.mean(all_day_vals)) if all_day_vals else 0.0, 6)
        p_at_k_active[f"p@{k}"] = round(float(np.mean(act_day_vals)) if act_day_vals else 0.0, 6)

    metrics["precision_at_k"] = p_at_k
    metrics["precision_at_k_active_days"] = p_at_k_active
    return metrics
