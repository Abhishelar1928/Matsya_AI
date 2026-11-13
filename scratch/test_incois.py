import requests
from bs4 import BeautifulSoup
import urllib3
import io
urllib3.disable_warnings()

def test_incois():
    session = requests.Session()
    home_url = "https://incois.gov.in/MarineFisheries/TextDataHome?mfid=1&request_locale=en"
    session.get(home_url, verify=False)
    
    data_url = "https://incois.gov.in/MarineFisheries/TextData?secid=SEC002"
    res2 = session.get(data_url, verify=False)
    
    soup = BeautifulSoup(res2.text, 'html.parser')
    
    with io.open('scratch/incois_output.txt', 'w', encoding='utf-8') as f:
        f.write("--- PAGE TEXT ---\n")
        text_lines = [line.strip() for line in soup.get_text().split('\n') if line.strip()]
        for i, line in enumerate(text_lines):
            if i < 50:
                f.write(line + "\n")
            if "Valid" in line or "Date" in line or "advisory" in line.lower() or "forecast" in line.lower():
                f.write(f"MATCH: {line}\n")
                
        f.write("\n--- IMAGES ---\n")
        imgs = soup.find_all('img')
        for img in imgs:
            f.write(f"{img.get('src')}\n")

if __name__ == "__main__":
    test_incois()
