import requests
from bs4 import BeautifulSoup
import urllib3
import re
urllib3.disable_warnings()

def test_incois():
    session = requests.Session()
    home_url = "https://incois.gov.in/MarineFisheries/TextDataHome?mfid=1&request_locale=en"
    res1 = session.get(home_url, verify=False)
    
    data_url = "https://incois.gov.in/MarineFisheries/TextData?secid=SEC002"
    res2 = session.get(data_url, verify=False)
    
    soup = BeautifulSoup(res2.text, 'html.parser')
    
    with open('scratch/incois_links.txt', 'w', encoding='utf-8') as f:
        f.write("--- LINKS ---\n")
        links = soup.find_all('a')
        for link in links:
            f.write(f"{link.text.strip()} : {link.get('href')}\n")
            
        f.write("\n--- DATES IN HOME PAGE ---\n")
        soup1 = BeautifulSoup(res1.text, 'html.parser')
        text1 = soup1.get_text()
        matches = re.findall(r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4}\b', text1)
        matches.extend(re.findall(r'\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}\b', text1))
        matches.extend(re.findall(r'\b\d{2}-\d{2}-\d{4}\b', text1))
        for m in set(matches):
            f.write(f"Date match in home: {m}\n")
            
        f.write("\n--- DATES IN DATA PAGE ---\n")
        text2 = soup.get_text()
        matches2 = re.findall(r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4}\b', text2)
        matches2.extend(re.findall(r'\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}\b', text2))
        matches2.extend(re.findall(r'\b\d{2}-\d{2}-\d{4}\b', text2))
        for m in set(matches2):
            f.write(f"Date match in data: {m}\n")

if __name__ == "__main__":
    test_incois()
