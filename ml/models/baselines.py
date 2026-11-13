"""
Matsya AI — Baselines for Next-Calendar-Day Fishing Activity Prediction.

Implements three required domain baselines:
1. Recent Activity Baseline: Predict T+1 using most recent eligible historical effort.
2. 7-Day Historical Trailing Baseline: Predict T+1 using trailing 7-day mean / frequency.
3. Seasonal / Spatial Baseline: Predict T+1 using spatial prior learned from Training split.
"""

from typing import Dict, Any, Optional
import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    roc_auc_score,
    precision_score,
    recall_score,
    f1_score,
    confusion_matrix,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)


def compute_classification_metrics(
    y_true: np.ndarray,
    scores: np.ndarray,
    predictions: np.ndarray,
) -> Dict[str, Any]:
    """
    Computes standard classification metrics with emphasis on PR-AUC, F1, Precision, Recall.
    """
    y_true = np.asarray(y_true).astype(int)
    scores = np.asarray(scores)
    predictions = np.asarray(predictions).astype(int)
    
    pos_count = int(y_true.sum())
    neg_count = int(len(y_true) - pos_count)
    pos_prev = float(pos_count / max(1, len(y_true)))
    
    # PR-AUC
    if len(np.unique(y_true)) > 1 and not np.isnan(scores).any():
        try:
            pr_auc = float(average_precision_score(y_true, scores))
        except Exception:
            pr_auc = float(pos_prev)
        try:
            roc_auc = float(roc_auc_score(y_true, scores))
        except Exception:
            roc_auc = 0.5
    else:
        pr_auc = float(pos_prev)
        roc_auc = 0.5
        
    p = float(precision_score(y_true, predictions, zero_division=0))
    r = float(recall_score(y_true, predictions, zero_division=0))
    f1 = float(f1_score(y_true, predictions, zero_division=0))
    cm = confusion_matrix(y_true, predictions, labels=[0, 1]).tolist()
    
    return {
        "pr_auc": pr_auc,
        "roc_auc": roc_auc,
        "precision": p,
        "recall": r,
        "f1": f1,
        "confusion_matrix": cm,
        "pos_count": pos_count,
        "neg_count": neg_count,
        "prevalence": pos_prev,
        "pred_pos_count": int(predictions.sum()),
    }


def compute_regression_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
    """
    Computes continuous fishing hours regression metrics (MAE, RMSE, R²).
    """
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)
    mae = float(mean_absolute_error(y_true, y_pred))
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    r2 = float(r2_score(y_true, y_pred))
    return {
        "mae": mae,
        "rmse": rmse,
        "r2": r2,
    }


class RecentActivityBaseline:
    """
    Predicts T+1 fishing activity using the most recent eligible observation available at T.
    """
    def __init__(self, threshold_hours: float):
        self.threshold = threshold_hours
        
    def predict_scores(self, df: pd.DataFrame) -> np.ndarray:
        # Score is recent fishing effort (normalized or raw)
        return df["fishing_hours_recent"].values.astype(float)
        
    def predict_binary(self, df: pd.DataFrame) -> np.ndarray:
        return (df["fishing_hours_recent"].values > self.threshold).astype(int)
        
    def evaluate(self, df: pd.DataFrame) -> Dict[str, Any]:
        y_true = (df["target_fishing_hours"].values > self.threshold).astype(int)
        scores = self.predict_scores(df)
        preds = self.predict_binary(df)
        res = compute_classification_metrics(y_true, scores, preds)
        reg_res = compute_regression_metrics(df["target_fishing_hours"].values, scores)
        res.update(reg_res)
        return res


class Trailing7DayHistoricalBaseline:
    """
    Predicts T+1 activity using trailing 7-day historical statistics (mean/pos_frequency).
    """
    def __init__(self, threshold_hours: float):
        self.threshold = threshold_hours
        
    def predict_scores(self, df: pd.DataFrame) -> np.ndarray:
        return df["fishing_hours_7d_mean"].values.astype(float)
        
    def predict_binary(self, df: pd.DataFrame) -> np.ndarray:
        # Binary prediction: active if trailing 7-day mean > threshold
        return (df["fishing_hours_7d_mean"].values > self.threshold).astype(int)
        
    def evaluate(self, df: pd.DataFrame) -> Dict[str, Any]:
        y_true = (df["target_fishing_hours"].values > self.threshold).astype(int)
        scores = self.predict_scores(df)
        preds = self.predict_binary(df)
        res = compute_classification_metrics(y_true, scores, preds)
        reg_res = compute_regression_metrics(df["target_fishing_hours"].values, scores)
        res.update(reg_res)
        return res


class SeasonalSpatialBaseline:
    """
    Predicts T+1 activity using empirical spatial prior of cell i learned strictly from Train.
    """
    def __init__(self, threshold_hours: float):
        self.threshold = threshold_hours
        self.cell_priors: Dict[str, float] = {}
        self.global_prior: float = 0.0
        self.decision_threshold: float = 0.5
        
    def fit(self, train_df: pd.DataFrame):
        y_train = (train_df["target_fishing_hours"].values > self.threshold).astype(int)
        df_copy = train_df[["grid_cell_id"]].copy()
        df_copy["y"] = y_train
        
        self.global_prior = float(y_train.mean())
        # Compute cell-specific prior with Laplace / empirical Bayesian smoothing
        grouped = df_copy.groupby("grid_cell_id")["y"]
        cell_sums = grouped.sum()
        cell_counts = grouped.count()
        
        # Smoothed cell rate: (sum + 1 * global_prior) / (count + 1)
        for cell_id in cell_counts.index:
            s = cell_sums[cell_id]
            c = cell_counts[cell_id]
            self.cell_priors[cell_id] = float((s + self.global_prior) / (c + 1.0))
            
        # Calibrate decision threshold on training set to maximize F1
        train_scores = np.array([self.cell_priors.get(cid, self.global_prior) for cid in train_df["grid_cell_id"]])
        best_t = 0.5
        best_f1 = -1.0
        for cand_t in np.linspace(0.01, 0.90, 50):
            cand_p = (train_scores >= cand_t).astype(int)
            cand_f1 = f1_score(y_train, cand_p, zero_division=0)
            if cand_f1 > best_f1:
                best_f1 = cand_f1
                best_t = cand_t
        self.decision_threshold = float(best_t)
        
    def predict_scores(self, df: pd.DataFrame) -> np.ndarray:
        return np.array([self.cell_priors.get(cid, self.global_prior) for cid in df["grid_cell_id"]])
        
    def predict_binary(self, df: pd.DataFrame) -> np.ndarray:
        scores = self.predict_scores(df)
        return (scores >= self.decision_threshold).astype(int)
        
    def evaluate(self, df: pd.DataFrame) -> Dict[str, Any]:
        y_true = (df["target_fishing_hours"].values > self.threshold).astype(int)
        scores = self.predict_scores(df)
        preds = self.predict_binary(df)
        res = compute_classification_metrics(y_true, scores, preds)
        return res
