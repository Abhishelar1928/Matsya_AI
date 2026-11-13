"""Test GFW API and save raw response for inspection."""
import json
import urllib.request
import urllib.parse
import urllib.error
import os
import sys

# Load token from .env
token = None
env_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '.env')
env_path = os.path.abspath(env_path)
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            if line.startswith('GFW_API_TOKEN='):
                token = line.strip().split('=', 1)[1]
                break

if not token:
    print("ERROR: GFW_API_TOKEN not found in .env")
    sys.exit(1)

print(f"Token found (first 20 chars): {token[:20]}...")

# Small 3-day request to inspect structure
params = {
    'datasets[0]': 'public-global-fishing-effort:latest',
    'date-range': '2023-10-01,2023-10-03',
    'spatial-resolution': 'HIGH',
    'temporal-resolution': 'DAILY',
    'format': 'JSON',
    'region-dataset': 'public-eez-areas',
    'region-id': '8480'
}
query_string = urllib.parse.urlencode(params)
url = f"https://gateway.api.globalfishingwatch.org/v3/4wings/report?{query_string}"

req = urllib.request.Request(url, headers={
    'Authorization': f'Bearer {token}',
    'User-Agent': 'MatsyaAI-Backend/1.0',
    'Accept': 'application/json'
})

print(f"\nRequesting: {url}\n")

try:
    with urllib.request.urlopen(req, timeout=120) as res:
        raw = res.read().decode()
        data = json.loads(raw)

        # Save raw response
        out_dir = os.path.join(os.path.dirname(__file__), 'data')
        os.makedirs(out_dir, exist_ok=True)
        raw_path = os.path.join(out_dir, 'gfw_raw_response_sample.json')
        with open(raw_path, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"Raw response saved to: {raw_path}")

        # Inspect structure
        print(f"\nTop-level keys: {list(data.keys())}")
        print(f"Type of data: {type(data)}")

        if 'entries' in data:
            entries = data['entries']
            print(f"entries type: {type(entries)}")
            print(f"entries length: {len(entries)}")

            if entries:
                first_entry = entries[0]
                print(f"\nFirst entry type: {type(first_entry)}")
                if isinstance(first_entry, dict):
                    print(f"First entry keys: {list(first_entry.keys())}")
                    for k, v in first_entry.items():
                        if isinstance(v, list):
                            print(f"  '{k}' -> list of {len(v)} items")
                            if v:
                                print(f"    First item type: {type(v[0])}")
                                if isinstance(v[0], dict):
                                    print(f"    First item keys: {list(v[0].keys())}")
                                    print(f"    First item: {json.dumps(v[0], indent=2)}")
                                if len(v) > 1:
                                    print(f"    Second item: {json.dumps(v[1], indent=2)}")
                        else:
                            print(f"  '{k}' -> {type(v).__name__}: {v}")
                elif isinstance(first_entry, list):
                    print(f"First entry is a list of {len(first_entry)} items")
                    if first_entry:
                        print(f"  First sub-item type: {type(first_entry[0])}")
                        if isinstance(first_entry[0], dict):
                            print(f"  First sub-item keys: {list(first_entry[0].keys())}")
                            print(f"  First sub-item: {json.dumps(first_entry[0], indent=2)}")
        else:
            print(f"\nFull response (first 2000 chars): {raw[:2000]}")

except urllib.error.HTTPError as e:
    body = e.read().decode()
    print(f"HTTP Error {e.code}: {body}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
