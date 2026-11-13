"""
MatsyaAI Maharashtra — Comprehensive ML Pipeline Audit.

Verifies all aspects of the ML pipeline:
- GFW date range
- Environmental date range
- Temporal alignment between GFW and environmental data
- Spatial alignment
- Missing values
- Target distribution
- Chronological split integrity
- Threshold derivation source (training only)
- Preprocessing leakage prevention
- Model artifact existence and consistency
- Feature consistency between training and inference
"""
import json
import logging
import sys
from pathlib import Path
from typing import List, Tuple

import pandas as pd

from backend.app.ml.config import (
    HISTORICAL_CACHE_PATH, GFW_START_DATE, GFW_END_DATE,
    ALL_FEATURE_COLUMNS, FISHING_HOURS_COLUMN,
    TRAIN_FRACTION, VAL_FRACTION,
    MODEL_PATH, IMPUTER_PATH, SCALER_PATH,
    THRESHOLD_PATH, FEATURE_COLUMNS_PATH, METADATA_PATH,
)

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


class AuditResult:
    def __init__(self):
        self.checks: List[Tuple[str, bool, str]] = []

    def check(self, name: str, passed: bool, detail: str = ""):
        status = "✅ PASS" if passed else "❌ FAIL"
        self.checks.append((name, passed, detail))
        logger.info(f"  {status}: {name}" + (f" — {detail}" if detail else ""))

    @property
    def passed(self) -> bool:
        return all(ok for _, ok, _ in self.checks)

    @property
    def failures(self) -> List[str]:
        return [name for name, ok, _ in self.checks if not ok]


def audit_dataset(df: pd.DataFrame) -> AuditResult:
    """Audit a historical dataset for correctness."""
    result = AuditResult()

    logger.info("\n" + "=" * 50)
    logger.info("AUDIT: Historical Dataset")
    logger.info("=" * 50)

    # --- A. GFW date range ---
    logger.info("\n[A] GFW Date Range")
    dates = pd.to_datetime(df['observation_date'])
    min_date = str(dates.min().date())
    max_date = str(dates.max().date())
    result.check(
        "GFW date range matches config",
        min_date == GFW_START_DATE and max_date == GFW_END_DATE,
        f"Got {min_date} to {max_date}, expected {GFW_START_DATE} to {GFW_END_DATE}"
    )

    # --- B. Environmental date range ---
    logger.info("\n[B] Environmental Date Range")
    if 'env_matched_date' in df.columns:
        env_dates = df['env_matched_date'].dropna()
        if not env_dates.empty:
            env_min = env_dates.min()
            env_max = env_dates.max()
            result.check(
                "Env dates match GFW dates",
                env_min >= GFW_START_DATE and env_max <= GFW_END_DATE,
                f"Env range: {env_min} to {env_max}"
            )
        else:
            result.check("Env dates present", False, "env_matched_date is all NaN")
    else:
        result.check("env_matched_date column exists", False)

    # --- C. Temporal alignment ---
    logger.info("\n[C] Temporal Alignment")
    if 'env_matched_date' in df.columns and 'observation_date' in df.columns:
        aligned = df[df['env_matched_date'].notna()]
        if not aligned.empty:
            mismatches = aligned[aligned['observation_date'] != aligned['env_matched_date']]
            result.check(
                "Env date == observation date (no temporal mismatch)",
                len(mismatches) == 0,
                f"{len(mismatches)} rows have env date != observation date" if not mismatches.empty else ""
            )
        else:
            result.check("Temporal alignment data present", False, "No non-null env data")

    if 'env_temporal_offset_hours' in df.columns:
        offsets = df['env_temporal_offset_hours'].dropna()
        if not offsets.empty:
            result.check(
                "Temporal offset is 0 (exact date match)",
                (offsets == 0).all(),
                f"Max offset: {offsets.max()} hours"
            )

    # --- D. No current/2026 data leakage ---
    logger.info("\n[D] Leakage: No Current/2026 Data")
    if 'env_matched_date' in df.columns:
        env_dates = pd.to_datetime(df['env_matched_date'].dropna())
        if not env_dates.empty:
            any_2026 = (env_dates.dt.year >= 2026).any()
            result.check(
                "No 2026 environmental data in training",
                not any_2026,
                "CRITICAL: 2026 data found in historical dataset!" if any_2026 else ""
            )

    # --- E. Spatial alignment ---
    logger.info("\n[E] Spatial Alignment")
    result.check(
        "grid_cell_id column exists",
        'grid_cell_id' in df.columns,
    )
    n_cells = df['grid_cell_id'].nunique() if 'grid_cell_id' in df.columns else 0
    result.check(
        "Grid cells > 0",
        n_cells > 0,
        f"{n_cells} unique cells"
    )

    # --- F. Duplicate rows ---
    logger.info("\n[F] Duplicate Check")
    if 'grid_cell_id' in df.columns and 'observation_date' in df.columns:
        dupes = df.duplicated(subset=['grid_cell_id', 'observation_date']).sum()
        result.check(
            "No duplicate (cell, date) pairs",
            dupes == 0,
            f"{dupes} duplicates found" if dupes > 0 else ""
        )

    # --- G. Missing values ---
    logger.info("\n[G] Missing Values")
    for col in ALL_FEATURE_COLUMNS:
        if col in df.columns:
            miss = df[col].isna().sum()
            pct = miss / len(df) * 100
            result.check(
                f"Feature '{col}' not entirely NaN",
                miss < len(df),
                f"{miss}/{len(df)} missing ({pct:.1f}%)"
            )

    # Check no zeros used as fill for wave_height/wind_speed
    for col in ['wave_height', 'wind_speed', 'wave_direction']:
        if col in df.columns:
            env_rows = df[df['env_matched_date'].notna()] if 'env_matched_date' in df.columns else df
            if not env_rows.empty:
                zero_count = (env_rows[col] == 0).sum()
                result.check(
                    f"'{col}' not suspiciously zero-filled",
                    zero_count < len(env_rows) * 0.5,
                    f"{zero_count} zeros ({zero_count/len(env_rows)*100:.1f}%)"
                )

    # --- H. Target distribution ---
    logger.info("\n[H] Target Distribution")
    if FISHING_HOURS_COLUMN in df.columns:
        non_zero = (df[FISHING_HOURS_COLUMN] > 0).sum()
        result.check(
            "Non-zero fishing hours exist",
            non_zero > 0,
            f"{non_zero} non-zero out of {len(df)}"
        )

    # --- I. Chronological split ---
    logger.info("\n[I] Chronological Split")
    n = len(df)
    train_end = int(n * TRAIN_FRACTION)
    val_end = int(n * (TRAIN_FRACTION + VAL_FRACTION))

    sorted_df = df.sort_values('observation_date')
    train = sorted_df.iloc[:train_end]
    val = sorted_df.iloc[train_end:val_end]
    test = sorted_df.iloc[val_end:]

    if not train.empty and not val.empty:
        result.check(
            "Train dates < Val dates",
            pd.to_datetime(train['observation_date']).max() <= pd.to_datetime(val['observation_date']).min(),
        )
    if not val.empty and not test.empty:
        result.check(
            "Val dates < Test dates",
            pd.to_datetime(val['observation_date']).max() <= pd.to_datetime(test['observation_date']).min(),
        )

    return result


def audit_artifacts() -> AuditResult:
    """Audit saved model artifacts."""
    result = AuditResult()

    logger.info("\n" + "=" * 50)
    logger.info("AUDIT: Model Artifacts")
    logger.info("=" * 50)

    # Check existence
    for name, path in [
        ("model.joblib", MODEL_PATH),
        ("imputer.joblib", IMPUTER_PATH),
        ("scaler.joblib", SCALER_PATH),
        ("threshold.json", THRESHOLD_PATH),
        ("feature_columns.json", FEATURE_COLUMNS_PATH),
        ("metadata.json", METADATA_PATH),
    ]:
        result.check(f"Artifact exists: {name}", path.exists())

    # Check threshold derived from training only
    if THRESHOLD_PATH.exists():
        with open(THRESHOLD_PATH) as f:
            thresh = json.load(f)
        result.check(
            "Threshold computed from training split",
            thresh.get('computed_from') == 'train_split_non_zero_fishing_hours',
            f"Source: {thresh.get('computed_from')}"
        )

    # Check metadata
    if METADATA_PATH.exists():
        with open(METADATA_PATH) as f:
            meta = json.load(f)
        result.check(
            "Metadata has training_date_range",
            'training_date_range' in meta,
        )
        result.check(
            "Metadata has test_metrics",
            'test_metrics' in meta,
        )
        result.check(
            "Metadata has feature_columns",
            'feature_columns' in meta,
        )

    # Check feature consistency
    if FEATURE_COLUMNS_PATH.exists() and METADATA_PATH.exists():
        with open(FEATURE_COLUMNS_PATH) as f:
            feat_cols = json.load(f)
        with open(METADATA_PATH) as f:
            meta = json.load(f)
        meta_cols = meta.get('feature_columns', [])
        result.check(
            "Feature columns consistent between artifacts",
            feat_cols == meta_cols,
            f"feature_columns.json: {feat_cols}, metadata: {meta_cols}"
        )

    return result


def run_audit():
    """Run the complete audit suite."""
    all_passed = True

    # Dataset audit
    if HISTORICAL_CACHE_PATH.exists():
        df = pd.read_parquet(HISTORICAL_CACHE_PATH)
        ds_result = audit_dataset(df)
        if not ds_result.passed:
            all_passed = False
    else:
        logger.info("\n⚠️  No cached dataset found. Run training pipeline first.")
        all_passed = False

    # Artifact audit
    art_result = audit_artifacts()
    if not art_result.passed:
        all_passed = False

    # Summary
    logger.info("\n" + "=" * 50)
    if all_passed:
        logger.info("🟢 ALL AUDIT CHECKS PASSED")
    else:
        logger.info("🔴 AUDIT FAILED")
        if HISTORICAL_CACHE_PATH.exists():
            if ds_result.failures:
                logger.info(f"  Dataset failures: {ds_result.failures}")
        if art_result.failures:
            logger.info(f"  Artifact failures: {art_result.failures}")
    logger.info("=" * 50)

    return all_passed


if __name__ == "__main__":
    success = run_audit()
    sys.exit(0 if success else 1)
