import logging
from backend.app.ml.dataset_builder import HistoricalDatasetBuilder

def run():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')
    print("Building historical dataset...")
    builder = HistoricalDatasetBuilder()
    df = builder.build()
    print(f"Dataset built with {len(df)} rows.")

if __name__ == "__main__":
    run()
