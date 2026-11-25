"""
MatsyaAI Maharashtra — Phase 4 Artifact Serializer.

Executes `run_phase4_experiment(..., return_artifacts=True)` once and writes all
frozen Phase 4 models, transformers, calibrator, threshold, metadata, feature schema,
and benchmark results from that EXACT same winning run into backend/app/ml/artifacts/.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import json
import logging
from typing import Any, Dict

import joblib

from backend.app.ml.config import ARTIFACTS_DIR, PHASE4_SEASONAL_CALIBRATOR_PATH
from ml.training.experiment_phase4 import run_phase4_experiment

logger = logging.getLogger(__name__)


def serialize_phase4(source_parquet_paths=None, ocean_cache_dir=None) -> Dict[str, Any]:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger.info("Running Phase 4 experiment and capturing winning artifact bundle...")
    results, bundle = run_phase4_experiment(
        source_parquet_paths=source_parquet_paths,
        ocean_cache_dir=ocean_cache_dir,
        target_threshold=1.0,
        return_artifacts=True,
        save_results=False,
    )

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    s1_model_path = ARTIFACTS_DIR / "phase4_stage1_habitat_model.joblib"
    s1_imp_path = ARTIFACTS_DIR / "phase4_stage1_imputer.joblib"
    s1_scl_path = ARTIFACTS_DIR / "phase4_stage1_scaler.joblib"
    s2_model_path = ARTIFACTS_DIR / "phase4_stage2_model.joblib"
    s2_imp_path = ARTIFACTS_DIR / "phase4_stage2_imputer.joblib"
    s2_scl_path = ARTIFACTS_DIR / "phase4_stage2_scaler.joblib"
    cal_path = ARTIFACTS_DIR / "phase4_calibrator.joblib"

    features_path = ARTIFACTS_DIR / "phase4_feature_columns.json"
    thresh_path = ARTIFACTS_DIR / "phase4_threshold.json"
    meta_path = ARTIFACTS_DIR / "phase4_metadata.json"
    results_path = ARTIFACTS_DIR / "phase4_results.json"

    s1 = bundle["stage1_bundle"]
    joblib.dump(s1["model"], s1_model_path)
    joblib.dump(s1["imputer"], s1_imp_path)
    joblib.dump(s1["scaler"], s1_scl_path)
    joblib.dump(bundle["stage2_model"], s2_model_path)
    joblib.dump(bundle["stage2_imputer"], s2_imp_path)
    joblib.dump(bundle["stage2_scaler"], s2_scl_path)
    joblib.dump(bundle["calibrator"], cal_path)
    if bundle.get("seasonal_calibrator") is not None:
        joblib.dump(bundle["seasonal_calibrator"], PHASE4_SEASONAL_CALIBRATOR_PATH)

    feature_payload = {
        "run_id": bundle["run_id"],
        "stage1_features": bundle["stage1_features"],
        "stage2_features": bundle["stage2_features"],
        "all_features": bundle["stage2_features"],
    }
    with open(features_path, "w") as fp:
        json.dump(feature_payload, fp, indent=2)

    cal_method = bundle["calibrator"].method
    seasonal_cal = bundle.get("seasonal_calibrator")
    seasonal_cal_method = seasonal_cal.method if seasonal_cal is not None else None
    thresh_payload = {
        "run_id": bundle["run_id"],
        "target_threshold_hours": bundle["target_threshold"],
        "decision_threshold": bundle["decision_threshold"],
        "calibration_method": cal_method,
        "seasonal_decision_threshold": bundle.get("seasonal_decision_threshold", bundle["decision_threshold"]),
        "seasonal_calibration_method": seasonal_cal_method,
        "target_interpretation": results["target_interpretation"],
    }
    with open(thresh_path, "w") as fp:
        json.dump(thresh_payload, fp, indent=2)

    p4_comp = results["benchmark_comparison"]["Phase4_SpatioOcean_v1"]
    metadata_payload = {
        "model_version": "Phase4_SpatioOcean_v1",
        "run_id": bundle["run_id"],
        "architecture": "Two-Stage (Stage 1 Habitat Suitability + Stage 2 Operational XGBoost + Post-Hoc Calibration)",
        "stage1_algorithm": s1["algorithm"],
        "stage2_algorithm": "XGBClassifier",
        "calibration_method": cal_method,
        "seasonal_calibration_method": seasonal_cal_method,
        "seasonal_decision_threshold": bundle.get("seasonal_decision_threshold", bundle["decision_threshold"]),
        "split_mode": bundle["split_mode"],
        "train_date_range": results["metadata"]["train_dates"],
        "validation_date_range": results["metadata"]["val_dates"],
        "test_date_range": results["metadata"]["test_dates"],
        "training_samples": bundle["n_train_rows"],
        "dataset_total_samples": bundle["n_total_rows"],
        "unique_cells": bundle["unique_cells"],
        "target_threshold_hours": bundle["target_threshold"],
        "decision_threshold": bundle["decision_threshold"],
        "target_interpretation": results["target_interpretation"],
        "stage1_features": bundle["stage1_features"],
        "stage2_features": bundle["stage2_features"],
        "validation_metrics": p4_comp["val"],
        "test_metrics": p4_comp["test"],
        "ocean_coverage": results["ocean_coverage"],
        "persistence_shift_analysis": results["persistence_shift_analysis"],
        "serialization_timestamp": bundle["execution_timestamp"],
        "disclaimer": results["disclaimer"],
    }
    with open(meta_path, "w") as fp:
        json.dump(metadata_payload, fp, indent=2)

    with open(results_path, "w") as fp:
        json.dump(results, fp, indent=2)

    # Strict cross-file consistency verification
    reloaded_meta = json.loads(meta_path.read_text())
    reloaded_feats = json.loads(features_path.read_text())
    reloaded_thresh = json.loads(thresh_path.read_text())
    reloaded_res = json.loads(results_path.read_text())

    assert reloaded_meta["run_id"] == reloaded_feats["run_id"] == reloaded_thresh["run_id"] == reloaded_res["run_id"]
    assert reloaded_meta["decision_threshold"] == reloaded_thresh["decision_threshold"]
    assert reloaded_meta["decision_threshold"] == reloaded_res["benchmark_comparison"]["Phase4_SpatioOcean_v1"]["tuned_threshold"]
    assert reloaded_meta["stage2_features"] == reloaded_feats["stage2_features"]
    assert reloaded_meta["test_metrics"] == reloaded_res["benchmark_comparison"]["Phase4_SpatioOcean_v1"]["test"]

    logger.info("Successfully serialized & verified consistent Phase 4 artifacts:")
    logger.info(f" - Run ID: {bundle['run_id']}")
    logger.info(f" - Stage 1 ({s1['algorithm']}): {s1_model_path}")
    logger.info(f" - Stage 2 (XGBClassifier): {s2_model_path}")
    logger.info(f" - Calibrator ({cal_method}): {cal_path}")
    logger.info(f" - Metadata / Features / Results: {meta_path}, {features_path}, {results_path}")
    return {"metadata": reloaded_meta, "results": reloaded_res}


if __name__ == "__main__":
    out = serialize_phase4()
    comp = out["results"]["benchmark_comparison"]
    print("\n=== Phase 4 Serialization & Benchmark Complete ===")
    print(f"Run ID: {out['metadata']['run_id']} | Calibration: {out['metadata']['calibration_method']} | Threshold: {out['metadata']['decision_threshold']}")
    for name in ("Phase3_XGBoost_Baseline", "Phase4_Spatial_Only", "Phase4_Stage1_Habitat_Only", "Phase4_SpatioOcean_v1"):
        t = comp[name]["test"]
        print(
            f"  {name:28s} | PR-AUC={t['pr_auc']:.4f} | ROC-AUC={t['roc_auc']:.4f} | "
            f"F1={t['f1']:.4f} | Brier={t['brier_score']:.5f} | P@10={t['precision_at_k'].get('p@10', 0):.4f}"
        )
