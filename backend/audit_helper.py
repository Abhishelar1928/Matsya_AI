import os
import sys
import json
from datetime import datetime, timezone
import pandas as pd
import numpy as np

def run_audit():
    print("--- ML Audit Script ---")
    from backend.app.ml.inference import Phase4InferencePipeline
    pipeline = Phase4InferencePipeline(demo_mode=True)
    pipeline.load_artifacts()
    
    print("\n[METADATA]")
    print(json.dumps(pipeline._metadata, indent=2))
    
    print("\n[THRESHOLD]")
    print(pipeline._threshold_info)
    
    print("\n[FEATURES IN EXPECTED ORDER]")
    print(pipeline._feature_columns)
    
    now = datetime.now(timezone.utc)
    grid = pipeline._generate_grid()
    env_df, status = pipeline._fetch_current_env(grid)
    feature_df = pipeline._build_features(grid, env_df, now)
    
    X_raw = feature_df[pipeline._feature_columns]
    X_imputed = pipeline._imputer.transform(X_raw)
    X_scaled = pipeline._scaler.transform(X_imputed)
    probs = pipeline._model.predict_proba(X_scaled)[:, 1]
    
    decision_thresh = float(pipeline._threshold_info.get("decision_threshold", 0.47))
    classes = (probs >= decision_thresh).astype(int)
    
    print("\n[TRACE 5 PREDICTIONS]")
    indices = [0, len(grid)//4, len(grid)//2, 3*len(grid)//4, len(grid)-1]
    for i in indices:
        cell = grid[i]
        features = X_raw.iloc[i].to_dict()
        print(f"\nCell: {cell['grid_cell_id']} (Lat: {cell['latitude']}, Lon: {cell['longitude']})")
        print("Raw Input Features:")
        for k, v in features.items():
            print(f"  {k}: {v}")
        print(f"Model Output Prob: {probs[i]:.4f}")
        print(f"Final Category: {'HIGH' if classes[i] == 1 else 'LOW'}")
    
    print("\n[DISTRIBUTION STATISTICS]")
    print(f"Total Predictions: {len(probs)}")
    print(f"Min: {np.min(probs):.4f}")
    print(f"Max: {np.max(probs):.4f}")
    print(f"Mean: {np.mean(probs):.4f}")
    print(f"Median: {np.median(probs):.4f}")
    print(f"Std Dev: {np.std(probs):.4f}")
    print(f"Count High (1): {np.sum(classes == 1)}")
    print(f"Count Low (0): {np.sum(classes == 0)}")
    
    print("\n[SUSPICIOUS BEHAVIOR CHECK]")
    unique_probs = np.unique(probs)
    print(f"Unique Probabilities Count: {len(unique_probs)}")
    
    prob_counts = pd.Series(probs).value_counts().head(10)
    print("Most common probabilities:")
    print(prob_counts)
    
    print("Missing Env Values Count (should be imputed by pipeline):")
    print(X_raw.isna().sum())

if __name__ == "__main__":
    run_audit()
