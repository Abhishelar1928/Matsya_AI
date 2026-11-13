import json

data = json.load(open('backend/app/ml/data/gfw_raw_response_sample.json'))
entries = data['entries'][0]['public-global-fishing-effort:v4.0']
total = len(entries)
mh = [r for r in entries if 15.5 <= r['lat'] <= 20.0 and 72.0 <= r['lon'] <= 74.0]
print(f'Total records: {total}')
print(f'Maharashtra records: {len(mh)}')
dates = sorted(set(r['date'] for r in mh))
print(f'Dates: {dates}')
print(f'Unique lats: {len(set(r["lat"] for r in mh))}')
print(f'Unique lons: {len(set(r["lon"] for r in mh))}')
if mh:
    print(f'Lat range: {min(r["lat"] for r in mh)} to {max(r["lat"] for r in mh)}')
    print(f'Lon range: {min(r["lon"] for r in mh)} to {max(r["lon"] for r in mh)}')
    print(f'Hours range: {min(r["hours"] for r in mh)} to {max(r["hours"] for r in mh)}')
    print(f'Gear types: {sorted(set(r.get("geartype","?") for r in mh))}')
