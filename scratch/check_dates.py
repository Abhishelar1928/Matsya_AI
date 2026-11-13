import requests
from bs4 import BeautifulSoup
import urllib3
import re
from datetime import datetime
urllib3.disable_warnings()

def check_dates():
    urls = [
        "https://incois.gov.in/MarineFisheries/MarineFisheryAdvisory",
        "https://incois.gov.in/portal/osf/osf.jsp"
    ]
    for url in urls:
        try:
            res = requests.get(url, verify=False, timeout=5)
            text = BeautifulSoup(res.text, 'html.parser').get_text()
            matches = re.findall(r'\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}\b', text, re.IGNORECASE)
            matches.extend(re.findall(r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4}\b', text, re.IGNORECASE))
            if matches:
                print(f"Dates in {url}: {set(matches)}")
            else:
                print(f"No dates in {url}")
        except Exception as e:
            print(f"Error fetching {url}: {e}")

check_dates()
