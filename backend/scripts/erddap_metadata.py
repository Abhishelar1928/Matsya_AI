import urllib.request, json, ssl
from datetime import datetime, timezone

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

datasets = [
    'NOAA_AVHRR_AMSR_datasets',
    'incois_argo_sst_weekly',
    'incois_oceansat2_datasets',
    'IRS_chlorophyll_datasets',
    'ascat_daily_datasets'
]

def check_dataset(dataset_id):
    url = f'https://erddap.incois.gov.in/erddap/info/{dataset_id}/index.json'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        res = urllib.request.urlopen(req, context=ctx, timeout=10)
        data = json.loads(res.read().decode())
        
        metadata = {}
        for row in data['table']['rows']:
            # columns: Row Type, Variable Name, Attribute Name, Data Type, Value
            attr_name = row[2]
            value = row[4]
            if attr_name in ['time_coverage_start', 'time_coverage_end', 'spatialResolution', 'time_coverage_resolution']:
                metadata[attr_name] = value
                
        print(f"--- {dataset_id} ---")
        print(f"Start: {metadata.get('time_coverage_start')}")
        print(f"End: {metadata.get('time_coverage_end')}")
        print(f"Time Res: {metadata.get('time_coverage_resolution')}")
        print(f"Spatial Res: {metadata.get('spatialResolution')}")
        
    except Exception as e:
        print(f'{dataset_id}: Error - {e}')

if __name__ == '__main__':
    for ds in datasets:
        check_dataset(ds)
