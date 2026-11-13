"""
Test script for the predictions FastAPI endpoint.
"""
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)

def run_test():
    print("Testing /api/v1/predictions endpoint...")
    response = client.get("/api/v1/predictions")
    
    if response.status_code == 200:
        data = response.json()
        print(f"SUCCESS: Endpoint returned 200 OK.")
        print(f"Returned {len(data)} predictions.")
        if data:
            print("\nSample Prediction:")
            for k, v in data[0].items():
                print(f"  {k}: {v}")
    else:
        print(f"FAILED: Status {response.status_code}")
        print(response.text)

if __name__ == "__main__":
    run_test()
