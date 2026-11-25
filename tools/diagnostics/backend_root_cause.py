import os
import sys
import json
from datetime import datetime, timezone
import pandas as pd
import numpy as np
import urllib.request
import urllib.error
import time

def run_investigation():
    print("=== MATSYAAI ROOT CAUSE INVESTIGATION ===\n")
    from backend.app.ml.inference import Phase4InferencePipeline
    from backend.app.ml.config import HISTORICAL_CACHE_PATH, DATA_DIR
    
    pipeline = Phase4InferencePipeline(demo_mode=True)
    pipeline.load_artifacts()
    
    # ---------------------------------------------------------
    # A. GFW ROOT-CAUSE TRACE
    # ---------------------------------------------------------
    print("--- A. GFW ROOT-CAUSE TRACE ---")
    print(f"Checking cache path: {HISTORICAL_CACHE_PATH}")
    print(f"Exists? {HISTORICAL_CACHE_PATH.exists()}")
    
    if HISTORICAL_CACHE_PATH.exists():
        df_hist = pd.read_parquet(HISTORICAL_CACHE_PATH)
        print(f"Row count: {len(df_hist)}")
        df_hist['observation_date'] = pd.to_datetime(df_hist['observation_date'])
        print(f"Date range: {df_hist['observation_date'].min()} to {df_hist['observation_date'].max()}")
        print(f"Unique grid cells in cache: {df_hist['grid_cell_id'].nunique()}")
        
        # Check spatial bounding
        if 'latitude' in df_hist.columns and 'longitude' in df_hist.columns:
            print(f"Lat range: {df_hist['latitude'].min()} to {df_hist['latitude'].max()}")
            print(f"Lon range: {df_hist['longitude'].min()} to {df_hist['longitude'].max()}")
            
        print("Sample rows:")
        print(df_hist[['grid_cell_id', 'observation_date', 'fishing_hours']].head())
    else:
        print("Parquet cache is completely missing!")
        # Is there any other data file?
        print("Files in DATA_DIR:")
        print(os.listdir(DATA_DIR))
        
    print("\nTracing how _build_features handles GFW...")
    # Read the logic in _build_features:
    # df["fishing_hours_recent"] = df["grid_cell_id"].map(recent_map).fillna(0.0)
    print("Missing GFW features are explicitly `.fillna(0.0)` in _build_features (Line 320-330).")

    # ---------------------------------------------------------
    # B & C. OPEN-METEO TRACE & GRID VALIDITY
    # ---------------------------------------------------------
    print("\n--- B & C. OPEN-METEO TRACE & GRID VALIDITY ---")
    grid = pipeline._generate_grid()
    print(f"Total grid cells generated: {len(grid)}")
    
    test_cells = [
        grid[0],                # 15.625, 72.125 (offshore)
        grid[10],               # 15.625, ... (might be coastal)
        grid[len(grid)//2],     # middle
        grid[-1],               # 20.125, 74.125 (inland)
        [c for c in grid if c['is_coastal'] == 1.0][0] # first coastal
    ]
    
    print("\nTesting Open-Meteo Marine API directly...")
    for cell in test_cells:
        lat = cell['latitude']
        lon = cell['longitude']
        url = f"https://marine-api.open-meteo.com/v1/marine?latitude={lat}&longitude={lon}&current=wave_height&timezone=UTC"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "AuditScript"})
            with urllib.request.urlopen(req, timeout=10) as res:
                data = json.loads(res.read().decode())
                val = data.get('current', {}).get('wave_height', 'Key Missing')
                print(f"Cell {lat},{lon} | dist_to_coast: {cell['distance_to_coast_km']} | is_coastal: {cell['is_coastal']} | Status: SUCCESS | wave_height: {val}")
        except urllib.error.HTTPError as e:
            msg = e.read().decode()
            print(f"Cell {lat},{lon} | dist_to_coast: {cell['distance_to_coast_km']} | is_coastal: {cell['is_coastal']} | Status: HTTP {e.code} | Msg: {msg}")
        except Exception as e:
            print(f"Cell {lat},{lon} | dist_to_coast: {cell['distance_to_coast_km']} | is_coastal: {cell['is_coastal']} | Status: ERROR {str(e)}")
        time.sleep(0.5)

    print("\nTesting Open-Meteo Weather API directly...")
    for cell in test_cells:
        lat = cell['latitude']
        lon = cell['longitude']
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=wind_speed_10m&timezone=UTC"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "AuditScript"})
            with urllib.request.urlopen(req, timeout=10) as res:
                data = json.loads(res.read().decode())
                val = data.get('current', {}).get('wind_speed_10m', 'Key Missing')
                print(f"Cell {lat},{lon} | Status: SUCCESS | wind_speed_10m: {val}")
        except Exception as e:
            print(f"Cell {lat},{lon} | Status: ERROR {str(e)}")
        time.sleep(0.5)
        
    print("\nGrid composition:")
    coastal_count = sum(1 for c in grid if c['is_coastal'] == 1.0)
    print(f"is_coastal == 1.0 count: {coastal_count}")
    print(f"is_coastal == 0.0 count: {len(grid) - coastal_count}")
    print(f"Note: is_coastal simply checks if distance_to_coast_km <= 50.0.")

    # ---------------------------------------------------------
    # E. PREDICTION CLUSTERING
    # ---------------------------------------------------------
    print("\n--- E. PREDICTION CLUSTERING ---")
    now = datetime.now(timezone.utc)
    env_df, status = pipeline._fetch_current_env(grid)
    feature_df = pipeline._build_features(grid, env_df, now)
    
    X_raw = feature_df[pipeline._feature_columns]
    X_imputed = pipeline._imputer.transform(X_raw)
    X_scaled = pipeline._scaler.transform(X_imputed)
    probs = pipeline._model.predict_proba(X_scaled)[:, 1]
    
    feature_df['prob'] = probs
    
    print("\nCheck grouped by probability (top 2 groups):")
    top_probs = pd.Series(probs).value_counts().head(2).index
    for p in top_probs:
        mask = np.isclose(probs, p)
        subset_raw = X_raw[mask]
        subset_imputed = pd.DataFrame(X_imputed[mask], columns=pipeline._feature_columns)
        
        print(f"\nProb = {p:.4f} (Count: {mask.sum()})")
        print("Number of unique post-imputation feature vectors (excluding lat/lon/dist):")
        
        cols_to_check = [c for c in pipeline._feature_columns if c not in ['latitude', 'longitude', 'distance_to_coast_km']]
        uniq_imputed = subset_imputed[cols_to_check].drop_duplicates()
        print(f"  {len(uniq_imputed)} unique core feature vectors.")
        
        # Are latitude/longitude influencing the model?
        # Let's see if the unique imputed core features are 1. If 1, then lat/lon are the ONLY varying things!
        if len(uniq_imputed) == 1:
            print("  -> Identical core features. The only differing features are lat/lon/distance!")
            # Are lat/lon used by XGBoost?
            if 'latitude' in pipeline._metadata.get('feature_importance', {}):
                print(f"  XGB importance for latitude: {pipeline._metadata['feature_importance']['latitude']}")
                print(f"  XGB importance for longitude: {pipeline._metadata['feature_importance']['longitude']}")

    # ---------------------------------------------------------
    # F. TRAINING MISSINGNESS COMPARISON
    # ---------------------------------------------------------
    print("\n--- F. TRAINING MISSINGNESS COMPARISON ---")
    # See if training data is saved or if we can extract it from phase3 metadata
    print("From phase3_metadata.json (dataset_size, etc.):")
    print(f"Training samples: {pipeline._metadata.get('training_samples')}")
    print("We cannot directly see missingness from metadata unless it's stored.")
    if os.path.exists(os.path.join(DATA_DIR, "causal_dataset.parquet")):
        df_train = pd.read_parquet(os.path.join(DATA_DIR, "causal_dataset.parquet"))
        print(f"Loaded training data (len={len(df_train)}). Missingness:")
        for col in ['wave_height', 'wind_speed', 'fishing_hours_recent']:
            if col in df_train.columns:
                n_miss = df_train[col].isna().sum()
                n_zero = (df_train[col] == 0).sum()
                print(f"  {col}: {n_miss} missing ({(n_miss/len(df_train))*100:.1f}%), {n_zero} zeros ({(n_zero/len(df_train))*100:.1f}%)")
    else:
        print("causal_dataset.parquet not found. Cannot determine exact training missingness.")

if __name__ == "__main__":
    run_investigation()
