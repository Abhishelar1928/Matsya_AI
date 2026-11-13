"""
MatsyaAI Maharashtra — ML Pipeline Runner.

Orchestrates:
1. Historical dataset building (GFW + Open-Meteo alignment)
2. Model training with leakage-safe preprocessing
3. Artifact saving

Does NOT require a database connection.
Does NOT use current/2026 data for historical training.
"""
import asyncio
import logging
import sys

from backend.app.ml.dataset_builder import HistoricalDatasetBuilder
from backend.app.ml.trainer import MLTrainer

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(name)s %(levelname)s %(message)s',
)
logger = logging.getLogger(__name__)


def run(force_refresh: bool = False):
    """Run the complete training pipeline."""
    logger.info("=" * 60)
    logger.info("MatsyaAI ML Pipeline — October 2023 PoC")
    logger.info("=" * 60)

    # Step 1: Build dataset
    logger.info("\n--- PHASE 1: Building Historical Dataset ---")
    builder = HistoricalDatasetBuilder(force_refresh=force_refresh)
    df = builder.build()

    if df.empty:
        logger.error("Dataset is empty. Cannot proceed with training.")
        print("\nPIPELINE RESULT: FAILED — empty dataset")
        return

    # Print dataset summary
    print(f"\n{'='*50}")
    print(f"DATASET SUMMARY")
    print(f"{'='*50}")
    print(f"Total rows: {len(df)}")
    print(f"Grid cells: {df['grid_cell_id'].nunique()}")
    print(f"Date range: {df['observation_date'].min()} to {df['observation_date'].max()}")
    print(f"Days: {df['observation_date'].nunique()}")

    # Missing values per feature
    print(f"\nMissing values:")
    for col in df.columns:
        miss = df[col].isna().sum()
        if miss > 0:
            print(f"  {col}: {miss} ({miss/len(df)*100:.1f}%)")

    # Fishing hours distribution
    print(f"\nFishing hours:")
    print(f"  Non-zero rows: {(df['fishing_hours'] > 0).sum()}")
    print(f"  Zero rows: {(df['fishing_hours'] == 0).sum()}")
    if (df['fishing_hours'] > 0).any():
        print(f"  Non-zero mean: {df[df['fishing_hours']>0]['fishing_hours'].mean():.4f}")
        print(f"  Non-zero median: {df[df['fishing_hours']>0]['fishing_hours'].median():.4f}")
        print(f"  Non-zero max: {df['fishing_hours'].max():.4f}")

    # Step 2: Train models
    logger.info("\n--- PHASE 2: Training Models ---")
    trainer = MLTrainer(df)
    results = trainer.train_and_compare()

    if not results:
        logger.error("Training failed.")
        print("\nPIPELINE RESULT: FAILED — training error")
        return

    # Print results
    print(f"\n{'='*50}")
    print(f"TRAINING RESULTS")
    print(f"{'='*50}")
    print(f"Best model: {results['best_model']}")
    print(f"Threshold: {results['threshold']:.4f}")
    print(f"Features: {results['feature_columns']}")

    print(f"\nValidation Metrics:")
    for name, metrics in results['validation_metrics'].items():
        f1 = metrics.get('f1', 0)
        print(f"  {name}: F1={f1:.4f}")

    print(f"\nTest Metrics ({results['best_model']}):")
    tm = results['test_metrics']
    print(f"  F1={tm.get('f1',0):.4f} P={tm.get('precision',0):.4f} R={tm.get('recall',0):.4f}")
    if 'roc_auc' in tm:
        print(f"  ROC-AUC={tm['roc_auc']:.4f} PR-AUC={tm['pr_auc']:.4f}")

    if results['feature_importance']:
        print(f"\nFeature Importance:")
        for feat, imp in sorted(results['feature_importance'].items(), key=lambda x: -x[1]):
            print(f"  {feat}: {imp:.4f}")

    print(f"\nPIPELINE RESULT: SUCCESS")
    print(f"Model artifacts saved to: backend/app/ml/artifacts/")


if __name__ == "__main__":
    force = "--force" in sys.argv or "--force-refresh" in sys.argv
    run(force_refresh=force)
