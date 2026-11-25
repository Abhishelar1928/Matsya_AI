import requests
import re
import urllib3
urllib3.disable_warnings()

def check_webgis():
    url = "https://incois.gov.in/geoportal/MFASPFZ/"
    res = requests.get(url, verify=False)
    print(f"Status: {res.status_code}")
    if res.status_code == 200:
        lines = res.text.split('\n')
        for line in lines:
            if 'http' in line or '.json' in line or 'wms' in line.lower() or 'geojson' in line.lower() or 'api' in line.lower():
                print(line.strip())
                
check_webgis()
