"""
MatsyaAI Maharashtra — ML Trainer.

Trains classification models on historically-aligned data with:
- Chronological train/val/test split by observation_date
- Threshold calculated ONLY from training data
- Imputer/Scaler fitted ONLY on X_train
- Validation-based model selection
- All artifacts saved for inference
"""
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

import joblib
import numpy as np
import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    precision_score, recall_score, f1_score,
    roc_auc_score, average_precision_score, confusion_matrix,
)
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from backend.app.ml.config import (
    ALL_FEATURE_COLUMNS, FISHING_HOURS_COLUMN, TARGET_COLUMN,
    TARGET_THRESHOLD_PERCENTILE, TARGET_DESCRIPTION,
    TRAIN_FRACTION, VAL_FRACTION,
    MODEL_PATH, IMPUTER_PATH, SCALER_PATH,
    THRESHOLD_PATH, FEATURE_COLUMNS_PATH, METADATA_PATH,
    ARTIFACTS_DIR, MODEL_LABEL, MODEL_DISCLAIMER,
)

logger = logging.getLogger(__name__)


class MLTrainer:
    """
    Trains and evaluates ML models with leakage-safe preprocessing.

    All preprocessing objects are fitted ONLY on the training split.
    Model selection uses validation F1. Test metrics are reported once.
    All artifacts are saved for use by the inference pipeline.
    """

    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()
        self.threshold = None
        self.feature_columns = None
        self.imputer = None
        self.scaler = None

    def _prepare_data(self):
        """
        1. Sort chronologically by observation_date
        2. Split into train/val/test
        3. Compute threshold from training data only
        4. Create target
        5. Select features, fit imputer + scaler on train only
        """
        # 1. Sort chronologically
        self.df['observation_date'] = pd.to_datetime(self.df['observation_date'])
        self.df = self.df.sort_values('observation_date').reset_index(drop=True)

        unique_dates = sorted(self.df['observation_date'].dt.date.unique())
        n_dates = len(unique_dates)
        train_end_idx = int(n_dates * TRAIN_FRACTION)
        val_end_idx = int(n_dates * (TRAIN_FRACTION + VAL_FRACTION))

        train_dates_bound = unique_dates[:train_end_idx]
        val_dates_bound = unique_dates[train_end_idx:val_end_idx]
        test_dates_bound = unique_dates[val_end_idx:]

        train_df = self.df[self.df['observation_date'].dt.date.isin(train_dates_bound)].copy()
        val_df = self.df[self.df['observation_date'].dt.date.isin(val_dates_bound)].copy()
        test_df = self.df[self.df['observation_date'].dt.date.isin(test_dates_bound)].copy()
        
        train_dates_actual = set(train_df['observation_date'].dt.date.unique())
        val_dates_actual = set(val_df['observation_date'].dt.date.unique())
        test_dates_actual = set(test_df['observation_date'].dt.date.unique())

        assert len(train_dates_actual & val_dates_actual) == 0, "Train and Val dates overlap!"
        assert len(train_dates_actual & test_dates_actual) == 0, "Train and Test dates overlap!"
        assert len(val_dates_actual & test_dates_actual) == 0, "Val and Test dates overlap!"

        print("\nTRAIN:")
        print(f"first_date: {min(train_dates_actual)}")
        print(f"last_date: {max(train_dates_actual)}")
        print(f"number_of_dates: {len(train_dates_actual)}")
        print(f"number_of_rows: {len(train_df)}")

        print("\nVALIDATION:")
        print(f"first_date: {min(val_dates_actual)}")
        print(f"last_date: {max(val_dates_actual)}")
        print(f"number_of_dates: {len(val_dates_actual)}")
        print(f"number_of_rows: {len(val_df)}")

        print("\nTEST:")
        print(f"first_date: {min(test_dates_actual)}")
        print(f"last_date: {max(test_dates_actual)}")
        print(f"number_of_dates: {len(test_dates_actual)}")
        print(f"number_of_rows: {len(test_df)}\n")

        # Log exact date ranges
        self._train_date_range = (
            str(train_df['observation_date'].min().date()),
            str(train_df['observation_date'].max().date()),
        )
        self._val_date_range = (
            str(val_df['observation_date'].min().date()),
            str(val_df['observation_date'].max().date()),
        )
        self._test_date_range = (
            str(test_df['observation_date'].min().date()),
            str(test_df['observation_date'].max().date()),
        )

        logger.info(
            f"Chronological split: "
            f"Train [{self._train_date_range[0]} → {self._train_date_range[1]}] ({len(train_df)} rows), "
            f"Val [{self._val_date_range[0]} → {self._val_date_range[1]}] ({len(val_df)} rows), "
            f"Test [{self._test_date_range[0]} → {self._test_date_range[1]}] ({len(test_df)} rows)"
        )

        # 2. Compute threshold from TRAINING data only
        non_zero = train_df[train_df[FISHING_HOURS_COLUMN] > 0][FISHING_HOURS_COLUMN]
        if non_zero.empty:
            logger.error("No non-zero fishing effort in training split.")
            raise ValueError("No non-zero fishing effort in training split.")

        self.threshold = float(non_zero.quantile(TARGET_THRESHOLD_PERCENTILE))
        logger.info(f"Target threshold: {self.threshold:.4f} hours "
                     f"({TARGET_THRESHOLD_PERCENTILE*100:.0f}th percentile of non-zero training effort)")

        # 3. Create target for all splits using FROZEN training threshold
        self.y_train = (train_df[FISHING_HOURS_COLUMN] >= self.threshold).astype(int)
        self.y_val = (val_df[FISHING_HOURS_COLUMN] >= self.threshold).astype(int)
        self.y_test = (test_df[FISHING_HOURS_COLUMN] >= self.threshold).astype(int)

        logger.info(f"Train class dist: {dict(self.y_train.value_counts())}")
        logger.info(f"Val class dist: {dict(self.y_val.value_counts())}")
        logger.info(f"Test class dist: {dict(self.y_test.value_counts())}")

        # 4. Select features — drop any that are entirely NaN in training
        available_features = []
        for col in ALL_FEATURE_COLUMNS:
            if col in train_df.columns:
                if not train_df[col].isna().all():
                    available_features.append(col)
                else:
                    logger.warning(f"Feature '{col}' is entirely NaN in training. Dropping.")
            else:
                logger.warning(f"Feature '{col}' not in dataset columns. Skipping.")

        self.feature_columns = available_features
        logger.info(f"Selected features ({len(self.feature_columns)}): {self.feature_columns}")

        X_train = train_df[self.feature_columns].copy()
        X_val = val_df[self.feature_columns].copy()
        X_test = test_df[self.feature_columns].copy()

        # Log missing value rates
        for col in self.feature_columns:
            miss_train = X_train[col].isna().sum()
            miss_val = X_val[col].isna().sum()
            miss_test = X_test[col].isna().sum()
            if miss_train > 0 or miss_val > 0 or miss_test > 0:
                logger.info(f"  Missing '{col}': train={miss_train}, val={miss_val}, test={miss_test}")

        # 5. Fit imputer on TRAINING only (median is robust for skewed marine data)
        self.imputer = SimpleImputer(strategy='median')
        X_train_imp = pd.DataFrame(
            self.imputer.fit_transform(X_train),
            columns=self.feature_columns, index=X_train.index
        )
        X_val_imp = pd.DataFrame(
            self.imputer.transform(X_val),
            columns=self.feature_columns, index=X_val.index
        )
        X_test_imp = pd.DataFrame(
            self.imputer.transform(X_test),
            columns=self.feature_columns, index=X_test.index
        )

        # 6. Fit scaler on TRAINING only
        self.scaler = StandardScaler()
        self.X_train = pd.DataFrame(
            self.scaler.fit_transform(X_train_imp),
            columns=self.feature_columns, index=X_train.index
        )
        self.X_val = pd.DataFrame(
            self.scaler.transform(X_val_imp),
            columns=self.feature_columns, index=X_val.index
        )
        self.X_test = pd.DataFrame(
            self.scaler.transform(X_test_imp),
            columns=self.feature_columns, index=X_test.index
        )

    def _evaluate(self, model, X, y, label: str = "") -> Dict[str, Any]:
        """Evaluate a model on a given split."""
        if len(y) == 0 or len(y.unique()) < 1:
            return {}

        preds = model.predict(X)
        probs = (
            model.predict_proba(X)[:, 1]
            if hasattr(model, "predict_proba") else preds.astype(float)
        )

        metrics = {
            "precision": round(float(precision_score(y, preds, zero_division=0)), 4),
            "recall": round(float(recall_score(y, preds, zero_division=0)), 4),
            "f1": round(float(f1_score(y, preds, zero_division=0)), 4),
            "support": {str(k): int(v) for k, v in y.value_counts().to_dict().items()},
        }

        if len(y.unique()) > 1:
            metrics["roc_auc"] = round(float(roc_auc_score(y, probs)), 4)
            metrics["pr_auc"] = round(float(average_precision_score(y, probs)), 4)
            metrics["confusion_matrix"] = confusion_matrix(y, preds).tolist()

        if label:
            logger.info(f"  {label}: F1={metrics['f1']:.4f} P={metrics['precision']:.4f} R={metrics['recall']:.4f}")

        return metrics

    def train_and_compare(self) -> Dict[str, Any]:
        """
        Train multiple models, select best on validation F1,
        evaluate once on test, and save all artifacts.
        """
        if self.df.empty:
            logger.error("Dataset is empty. Cannot train.")
            return {}

        self._prepare_data()

        if len(self.y_train.unique()) < 2:
            logger.error("Training data has only one class. Cannot train.")
            return {}

        # Define models
        scale_pos_weight = (
            (len(self.y_train) - self.y_train.sum()) / max(self.y_train.sum(), 1)
        )

        models = {
            'Baseline': DummyClassifier(strategy='prior'),
            'LogisticRegression': LogisticRegression(
                class_weight='balanced', max_iter=1000, random_state=42
            ),
            'RandomForest': RandomForestClassifier(
                n_estimators=100, class_weight='balanced', random_state=42
            ),
            'XGBoost': XGBClassifier(
                eval_metric='logloss', random_state=42,
                scale_pos_weight=float(scale_pos_weight),
            ),
        }

        # Train and evaluate on validation
        val_results = {}
        for name, model in models.items():
            logger.info(f"Training {name}...")
            model.fit(self.X_train, self.y_train)
            val_results[name] = self._evaluate(model, self.X_val, self.y_val, f"{name} [val]")

        # Select best model by validation F1
        best_name = max(
            [n for n in val_results if n != 'Baseline'],
            key=lambda n: val_results[n].get('f1', 0)
        )
        best_model = models[best_name]
        logger.info(f"Best model: {best_name} (val F1={val_results[best_name].get('f1', 0):.4f})")

        # Evaluate best model on test (ONCE)
        test_metrics = self._evaluate(best_model, self.X_test, self.y_test, f"{best_name} [test]")

        # Feature importance (for tree models)
        feature_importance = {}
        if hasattr(best_model, 'feature_importances_'):
            feature_importance = {
                name: round(float(imp), 4)
                for name, imp in zip(self.feature_columns, best_model.feature_importances_)
            }

        # Save artifacts
        self._save_artifacts(best_model, best_name, val_results, test_metrics, feature_importance)

        return {
            'best_model': best_name,
            'validation_metrics': val_results,
            'test_metrics': test_metrics,
            'feature_importance': feature_importance,
            'threshold': self.threshold,
            'feature_columns': self.feature_columns,
            'dataset_size': len(self.df),
        }

    def _save_artifacts(
        self, model, model_name: str,
        val_results: Dict, test_metrics: Dict,
        feature_importance: Dict
    ):
        """Save all model artifacts for inference."""
        ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

        # Model
        joblib.dump(model, MODEL_PATH)
        logger.info(f"Model saved to {MODEL_PATH}")

        # Imputer
        joblib.dump(self.imputer, IMPUTER_PATH)
        logger.info(f"Imputer saved to {IMPUTER_PATH}")

        # Scaler
        joblib.dump(self.scaler, SCALER_PATH)
        logger.info(f"Scaler saved to {SCALER_PATH}")

        # Threshold
        threshold_data = {
            "value": self.threshold,
            "percentile": TARGET_THRESHOLD_PERCENTILE,
            "computed_from": "train_split_non_zero_fishing_hours",
        }
        with open(THRESHOLD_PATH, 'w') as f:
            json.dump(threshold_data, f, indent=2)
        logger.info(f"Threshold saved to {THRESHOLD_PATH}")

        # Feature columns
        with open(FEATURE_COLUMNS_PATH, 'w') as f:
            json.dump(self.feature_columns, f, indent=2)
        logger.info(f"Feature columns saved to {FEATURE_COLUMNS_PATH}")

        # Metadata
        metadata = {
            "model_label": MODEL_LABEL,
            "model_disclaimer": MODEL_DISCLAIMER,
            "model_type": model_name,
            "target_definition": TARGET_DESCRIPTION,
            "threshold": self.threshold,
            "training_date_range": self._train_date_range,
            "validation_date_range": self._val_date_range,
            "test_date_range": self._test_date_range,
            "feature_columns": self.feature_columns,
            "feature_importance": feature_importance,
            "dataset_size": len(self.df),
            "class_distribution": {
                "train": {str(k): int(v) for k, v in self.y_train.value_counts().items()},
                "val": {str(k): int(v) for k, v in self.y_val.value_counts().items()},
                "test": {str(k): int(v) for k, v in self.y_test.value_counts().items()},
            },
            "validation_metrics": val_results,
            "test_metrics": test_metrics,
            "data_sources": {
                "target": "GFW 4Wings Report API v4 (public-global-fishing-effort)",
                "environmental": "Open-Meteo Historical Marine + Weather API",
                "spatial": "0.25° grid, Maharashtra coast (15.5-20.0°N, 72.0-74.0°E)",
            },
            "training_timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with open(METADATA_PATH, 'w') as f:
            json.dump(metadata, f, indent=2)
        logger.info(f"Metadata saved to {METADATA_PATH}")
